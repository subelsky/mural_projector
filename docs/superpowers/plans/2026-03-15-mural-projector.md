# StoryField Mural Projector Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade info-beamer package that polls a URL for updated mural images and displays them fullscreen with dissolve crossfade transitions on a Raspberry Pi 5 laser projector.

**Architecture:** A `MuralPoller` class in `mural_poller.py` handles all core logic (redirect checking, image downloading, backoff, atomic file writes) with zero info-beamer dependencies. The `service` entry point is a thin wrapper that reads config via `hosted.py` and passes plain values to `MuralPoller`. `node.lua` handles display rendering with dissolve crossfade and cover scaling. All Python code must be Python 2/3 polyglot.

**Tech Stack:** Python 2/3 polyglot (urllib2/urllib.request), Lua (info-beamer OpenGL), pytest + pytest-cov, flake8, pylint

**Spec:** `docs/superpowers/specs/2026-03-15-mural-projector-design.md`
**Project Overview:** `PROJECT_OVERVIEW.md`

---

## Chunk 1: Scaffolding, check_redirect, download_image

### Task 1: Project Scaffolding

**Files:**
- Create: `requirements-dev.txt`
- Create: `.flake8`
- Create: `.pylintrc`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_mural_poller.py` (empty initially)
- Create: `mural_poller.py` (empty initially)

- [ ] **Step 1: Create `requirements-dev.txt`**

```
pytest==8.3.5
pytest-cov==6.1.1
flake8==7.1.2
pylint==3.3.6
```

- [ ] **Step 2: Create `.flake8`**

```ini
[flake8]
max-complexity = 10
max-line-length = 99
exclude = .venv,hosted.py
```

- [ ] **Step 3: Create `.pylintrc`**

```ini
[MASTER]
ignore=hosted.py,hosted.lua

[MESSAGES CONTROL]
# Allow the try/except import pattern for Python 2/3 polyglot
disable=ungrouped-imports,wrong-import-order,import-error,duplicate-code

[FORMAT]
max-line-length=99

[DESIGN]
max-args=5
```

- [ ] **Step 4: Create test scaffolding files**

Create `tests/__init__.py` (empty file).

Create `tests/conftest.py`:

```python
"""Shared test fixtures for mural_poller tests."""
import logging
import pytest


@pytest.fixture
def logger():
    """Provide a logger that captures output for assertions."""
    test_logger = logging.getLogger("test_mural_poller")
    test_logger.setLevel(logging.DEBUG)
    return test_logger
```

Create `tests/test_mural_poller.py` (empty for now — tests added in subsequent tasks):

```python
"""Tests for mural_poller module — strict red/green TDD."""
```

Create `mural_poller.py` (empty module stub):

```python
#!/usr/bin/python
"""Core polling logic for StoryField mural display."""
from __future__ import print_function
```

- [ ] **Step 5: Install dev dependencies**

Run: `pip install -r requirements-dev.txt`
Expected: All packages install successfully.

- [ ] **Step 6: Verify pytest runs with no errors**

Run: `python -m pytest tests/ -v`
Expected: "no tests ran" / 0 errors.

- [ ] **Step 7: Commit scaffolding**

```bash
git add requirements-dev.txt .flake8 .pylintrc tests/ mural_poller.py
git commit -m "chore: add project scaffolding — dev deps, lint config, test structure"
```

---

### Task 2: check_redirect — 307 Happy Path

**Files:**
- Modify: `tests/test_mural_poller.py`
- Modify: `mural_poller.py`

This task implements the primary happy path: `check_redirect()` sends a request, gets a 307, returns the `Location` header value.

**Context for implementer:** The `MuralPoller` class must be Python 2/3 polyglot. Use this import pattern at the top of `mural_poller.py`:

```python
try:
    from urllib.request import Request, build_opener, HTTPRedirectHandler
    from urllib.error import URLError, HTTPError
except ImportError:
    from urllib2 import Request, build_opener, HTTPRedirectHandler, URLError, HTTPError
```

The `check_redirect()` method uses `build_opener()` with a custom `HTTPRedirectHandler` subclass that overrides `http_error_307` to prevent following the redirect. It sends the request with a 10-second timeout, then reads the `Location` header from the response. Header lookup must be case-insensitive — use Python's `HTTPResponse` `.getheader()` or iterate response `.info()` headers.

- [ ] **Step 1: Write failing test for 307 happy path**

Add to `tests/test_mural_poller.py`:

```python
from unittest.mock import patch, MagicMock
import logging

from mural_poller import MuralPoller


class TestCheckRedirect:
    """Tests for MuralPoller.check_redirect()."""

    def _make_poller(self, url="http://example.com/api/mural/latest"):
        """Create a MuralPoller with test defaults."""
        logger = logging.getLogger("test")
        return MuralPoller(
            mural_url=url,
            poll_interval=15,
            image_path="current.jpg",
            logger=logger,
        )

    @patch("mural_poller.build_opener")
    def test_307_returns_location_header(self, mock_build_opener):
        """307 response with Location header returns the URL."""
        mock_response = MagicMock()
        mock_response.getcode.return_value = 307
        mock_response.info.return_value.get.return_value = (
            "https://cdn.example.com/mural-abc123.jpg"
        )
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_response
        mock_build_opener.return_value = mock_opener

        poller = self._make_poller()
        result = poller.check_redirect()

        assert result == "https://cdn.example.com/mural-abc123.jpg"
```

- [ ] **Step 2: Run test to verify it fails (RED)**

Run: `python -m pytest tests/test_mural_poller.py::TestCheckRedirect::test_307_returns_location_header -v`
Expected: FAIL — `MuralPoller` class doesn't exist yet or has no `check_redirect` method.

- [ ] **Step 3: Implement MuralPoller constructor and check_redirect (307 path)**

Write in `mural_poller.py`:

```python
#!/usr/bin/python
"""Core polling logic for StoryField mural display."""
from __future__ import print_function

import os
import hashlib
import time

try:
    from urllib.request import Request, build_opener, HTTPRedirectHandler
    from urllib.error import URLError, HTTPError
except ImportError:
    from urllib2 import Request, build_opener, HTTPRedirectHandler, URLError, HTTPError


BACKOFF_SCHEDULE = [5, 10, 20, 40, 80, 120]
REDIRECT_TIMEOUT = 10
DOWNLOAD_TIMEOUT = 30


class _NoRedirectHandler(HTTPRedirectHandler):
    """Prevent urllib from following redirects automatically."""

    def http_error_307(self, req, fp, code, msg, headers):
        """Return the response instead of following the redirect."""
        return fp

    def http_error_302(self, req, fp, code, msg, headers):
        """Return the response instead of following the redirect."""
        return fp

    def http_error_301(self, req, fp, code, msg, headers):
        """Return the response instead of following the redirect."""
        return fp


class MuralPoller(object):
    """Polls a mural API endpoint and downloads new images.

    Args:
        mural_url: The API endpoint URL that returns a 307 redirect.
        poll_interval: Seconds between polling checks.
        image_path: Filesystem path to write the downloaded image.
        logger: A logging.Logger instance for status messages.
    """

    def __init__(self, mural_url, poll_interval, image_path, logger):
        """Initialize the poller with configuration values.

        Args:
            mural_url: The API endpoint URL.
            poll_interval: Seconds between polls.
            image_path: Path to write the current image.
            logger: Logger instance.
        """
        self.mural_url = mural_url
        self.poll_interval = poll_interval
        self.image_path = image_path
        self.logger = logger
        self.current_location = None
        self.backoff_level = 0

    def check_redirect(self):
        """Check the mural API for a new image URL.

        Sends a request to mural_url without following redirects.

        Returns:
            On 307: the Location header value (a URL string).
            On 200: the SHA-256 hex digest of the response body
                    (for content-hash change detection).

        Raises:
            HTTPError: On 5xx or other unexpected status codes.
            URLError: On network errors or timeouts.
            ValueError: On 307 with missing Location header.
        """
        opener = build_opener(_NoRedirectHandler)
        request = Request(self.mural_url)
        response = opener.open(request, timeout=REDIRECT_TIMEOUT)
        code = response.getcode()

        if code == 307:
            location = response.info().get("Location")
            if location is None:
                raise ValueError(
                    "307 response missing Location header"
                )
            return location

        if code == 200:
            body = response.read()
            return hashlib.sha256(body).hexdigest()

        raise HTTPError(
            self.mural_url, code, "Unexpected status", {}, None
        )
```

- [ ] **Step 4: Run test to verify it passes (GREEN)**

Run: `python -m pytest tests/test_mural_poller.py::TestCheckRedirect::test_307_returns_location_header -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_mural_poller.py mural_poller.py
git commit -m "feat: add MuralPoller with check_redirect 307 happy path (TDD red→green)"
```

---

### Task 3: check_redirect — Edge Cases

**Files:**
- Modify: `tests/test_mural_poller.py`
- Modify: `mural_poller.py` (only if tests fail — code from Task 2 should handle most cases)

This task adds tests for: case-insensitive headers, missing Location header, 200 response with content hashing, 5xx errors, network timeout, and general network errors.

- [ ] **Step 1: Write failing test for case-insensitive Location header**

Add to `TestCheckRedirect` class in `tests/test_mural_poller.py`:

```python
    @patch("mural_poller.build_opener")
    def test_307_case_insensitive_location_header(self, mock_build_opener):
        """307 with lowercase 'location' header still returns value."""
        mock_response = MagicMock()
        mock_response.getcode.return_value = 307
        # Simulate case-insensitive header access
        mock_response.info.return_value.get.return_value = (
            "https://cdn.example.com/mural-def456.jpg"
        )
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_response
        mock_build_opener.return_value = mock_opener

        poller = self._make_poller()
        result = poller.check_redirect()

        assert result == "https://cdn.example.com/mural-def456.jpg"
```

- [ ] **Step 2: Run test — should PASS (already handled by `.get("Location")`)**

Run: `python -m pytest tests/test_mural_poller.py::TestCheckRedirect::test_307_case_insensitive_location_header -v`
Expected: PASS — Python's `http.client.HTTPMessage.get()` is already case-insensitive.

Note: If this fails, update `check_redirect()` to do case-insensitive header lookup by iterating headers manually.

- [ ] **Step 3: Write failing test for missing Location header on 307**

```python
    @patch("mural_poller.build_opener")
    def test_307_missing_location_raises_value_error(self, mock_build_opener):
        """307 response without Location header raises ValueError."""
        mock_response = MagicMock()
        mock_response.getcode.return_value = 307
        mock_response.info.return_value.get.return_value = None
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_response
        mock_build_opener.return_value = mock_opener

        poller = self._make_poller()
        with pytest.raises(ValueError, match="missing Location"):
            poller.check_redirect()
```

- [ ] **Step 4: Run test — should PASS (already handled)**

Run: `python -m pytest tests/test_mural_poller.py::TestCheckRedirect::test_307_missing_location_raises_value_error -v`
Expected: PASS

- [ ] **Step 5: Write failing test for 200 response with content hashing**

```python
    @patch("mural_poller.build_opener")
    def test_200_returns_content_hash(self, mock_build_opener):
        """200 response returns SHA-256 hex digest of body."""
        import hashlib
        body = b"fake image data"
        expected_hash = hashlib.sha256(body).hexdigest()

        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.read.return_value = body
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_response
        mock_build_opener.return_value = mock_opener

        poller = self._make_poller()
        result = poller.check_redirect()

        assert result == expected_hash
```

- [ ] **Step 6: Run test — should PASS (already handled)**

Run: `python -m pytest tests/test_mural_poller.py::TestCheckRedirect::test_200_returns_content_hash -v`
Expected: PASS

- [ ] **Step 7: Write failing test for 5xx error**

```python
    @patch("mural_poller.build_opener")
    def test_5xx_raises_http_error(self, mock_build_opener):
        """5xx response raises HTTPError."""
        mock_opener = MagicMock()
        mock_opener.open.side_effect = HTTPError(
            "http://example.com", 500, "Server Error", {}, None
        )
        mock_build_opener.return_value = mock_opener

        poller = self._make_poller()
        with pytest.raises(HTTPError):
            poller.check_redirect()
```

Need to add import at top of test file:

```python
try:
    from urllib.error import HTTPError
except ImportError:
    from urllib2 import HTTPError
```

- [ ] **Step 8: Run test — should PASS (exception propagates)**

Run: `python -m pytest tests/test_mural_poller.py::TestCheckRedirect::test_5xx_raises_http_error -v`
Expected: PASS

- [ ] **Step 9: Write failing test for network timeout**

```python
    @patch("mural_poller.build_opener")
    def test_network_timeout_raises(self, mock_build_opener):
        """Network timeout raises URLError."""
        import socket
        mock_opener = MagicMock()
        mock_opener.open.side_effect = URLError(socket.timeout("timed out"))
        mock_build_opener.return_value = mock_opener

        poller = self._make_poller()
        with pytest.raises(URLError):
            poller.check_redirect()
```

Need to add URLError import at top:

```python
try:
    from urllib.error import HTTPError, URLError
except ImportError:
    from urllib2 import HTTPError, URLError
```

- [ ] **Step 10: Run test — should PASS (exception propagates)**

Run: `python -m pytest tests/test_mural_poller.py::TestCheckRedirect::test_network_timeout_raises -v`
Expected: PASS

- [ ] **Step 11: Write failing test for general network error**

```python
    @patch("mural_poller.build_opener")
    def test_network_error_raises(self, mock_build_opener):
        """General network error raises URLError."""
        mock_opener = MagicMock()
        mock_opener.open.side_effect = URLError("Name or service not known")
        mock_build_opener.return_value = mock_opener

        poller = self._make_poller()
        with pytest.raises(URLError):
            poller.check_redirect()
```

- [ ] **Step 12: Run test — should PASS (exception propagates)**

Run: `python -m pytest tests/test_mural_poller.py::TestCheckRedirect::test_network_error_raises -v`
Expected: PASS

- [ ] **Step 13: Run all check_redirect tests together**

Run: `python -m pytest tests/test_mural_poller.py::TestCheckRedirect -v`
Expected: All 7 tests PASS.

- [ ] **Step 14: Commit**

```bash
git add tests/test_mural_poller.py mural_poller.py
git commit -m "test: add check_redirect edge case tests — headers, 200, 5xx, timeouts"
```

---

### Task 4: download_image — Atomic File Writes

**Files:**
- Modify: `tests/test_mural_poller.py`
- Modify: `mural_poller.py`

This task implements `download_image(url)` which downloads an image from a CDN URL and writes it atomically (`.tmp` then `os.rename()`). On any failure, the `.tmp` file is cleaned up.

- [ ] **Step 1: Write failing test for successful download**

Add to `tests/test_mural_poller.py`:

```python
class TestDownloadImage:
    """Tests for MuralPoller.download_image()."""

    def _make_poller(self, image_path="/tmp/test_current.jpg"):
        """Create a MuralPoller with test defaults."""
        logger = logging.getLogger("test")
        return MuralPoller(
            mural_url="http://example.com/api/mural/latest",
            poll_interval=15,
            image_path=image_path,
            logger=logger,
        )

    @patch("mural_poller.os.rename")
    @patch("mural_poller.build_opener")
    @patch("builtins.open", create=True)
    def test_successful_download_writes_atomically(
        self, mock_open, mock_build_opener, mock_rename
    ):
        """Successful download writes to .tmp then renames."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"fake image bytes"
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_response
        mock_build_opener.return_value = mock_opener

        mock_file = MagicMock()
        mock_open.return_value.__enter__ = MagicMock(
            return_value=mock_file
        )
        mock_open.return_value.__exit__ = MagicMock(
            return_value=False
        )

        poller = self._make_poller()
        result = poller.download_image(
            "https://cdn.example.com/mural-abc123.jpg"
        )

        assert result is True
        mock_open.assert_called_once_with(
            "/tmp/test_current.jpg.tmp", "wb"
        )
        mock_file.write.assert_called_once_with(b"fake image bytes")
        mock_rename.assert_called_once_with(
            "/tmp/test_current.jpg.tmp", "/tmp/test_current.jpg"
        )
```

- [ ] **Step 2: Run test to verify it fails (RED)**

Run: `python -m pytest tests/test_mural_poller.py::TestDownloadImage::test_successful_download_writes_atomically -v`
Expected: FAIL — `download_image` method doesn't exist.

- [ ] **Step 3: Implement download_image**

Add to `MuralPoller` class in `mural_poller.py`:

```python
    def download_image(self, url):
        """Download an image and write it atomically to disk.

        Downloads from url, writes to image_path.tmp, then renames
        to image_path. Cleans up .tmp file on any failure.

        Args:
            url: The CDN URL to download the image from.

        Returns:
            True on success.

        Raises:
            URLError: On network errors or timeouts.
            IOError: On filesystem write errors.
        """
        tmp_path = self.image_path + ".tmp"
        try:
            opener = build_opener()
            request = Request(url)
            response = opener.open(request, timeout=DOWNLOAD_TIMEOUT)
            data = response.read()
            with open(tmp_path, "wb") as f:
                f.write(data)
            os.rename(tmp_path, self.image_path)
            self.logger.info(
                "Downloaded %d bytes to %s",
                len(data), self.image_path
            )
            return True
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise
```

- [ ] **Step 4: Run test to verify it passes (GREEN)**

Run: `python -m pytest tests/test_mural_poller.py::TestDownloadImage::test_successful_download_writes_atomically -v`
Expected: PASS

- [ ] **Step 5: Write failing test for network error cleanup**

```python
    @patch("mural_poller.os.remove")
    @patch("mural_poller.build_opener")
    def test_network_error_cleans_up_tmp(
        self, mock_build_opener, mock_remove
    ):
        """Network error during download cleans up .tmp file."""
        mock_opener = MagicMock()
        mock_opener.open.side_effect = URLError("Connection refused")
        mock_build_opener.return_value = mock_opener

        poller = self._make_poller()
        with pytest.raises(URLError):
            poller.download_image(
                "https://cdn.example.com/mural-abc123.jpg"
            )

        mock_remove.assert_called_once_with(
            "/tmp/test_current.jpg.tmp"
        )
```

Add `URLError` import at top of test file if not already present.

- [ ] **Step 6: Run test — should PASS (already handled by except block)**

Run: `python -m pytest tests/test_mural_poller.py::TestDownloadImage::test_network_error_cleans_up_tmp -v`
Expected: PASS

- [ ] **Step 7: Write failing test for download timeout cleanup**

```python
    @patch("mural_poller.os.remove")
    @patch("mural_poller.build_opener")
    def test_download_timeout_cleans_up_tmp(
        self, mock_build_opener, mock_remove
    ):
        """Download timeout cleans up .tmp file."""
        import socket
        mock_opener = MagicMock()
        mock_opener.open.side_effect = URLError(
            socket.timeout("timed out")
        )
        mock_build_opener.return_value = mock_opener

        poller = self._make_poller()
        with pytest.raises(URLError):
            poller.download_image(
                "https://cdn.example.com/mural-abc123.jpg"
            )

        mock_remove.assert_called_once_with(
            "/tmp/test_current.jpg.tmp"
        )
```

- [ ] **Step 8: Run test — should PASS**

Run: `python -m pytest tests/test_mural_poller.py::TestDownloadImage::test_download_timeout_cleans_up_tmp -v`
Expected: PASS

- [ ] **Step 9: Write failing test for write error cleanup**

```python
    @patch("mural_poller.os.remove")
    @patch("mural_poller.os.rename", side_effect=OSError("disk full"))
    @patch("mural_poller.build_opener")
    @patch("builtins.open", create=True)
    def test_write_error_cleans_up_tmp(
        self, mock_open, mock_build_opener, mock_rename, mock_remove
    ):
        """Write/rename error cleans up .tmp file."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"fake image bytes"
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_response
        mock_build_opener.return_value = mock_opener

        mock_file = MagicMock()
        mock_open.return_value.__enter__ = MagicMock(
            return_value=mock_file
        )
        mock_open.return_value.__exit__ = MagicMock(
            return_value=False
        )

        poller = self._make_poller()
        with pytest.raises(OSError):
            poller.download_image(
                "https://cdn.example.com/mural-abc123.jpg"
            )

        mock_remove.assert_called_once_with(
            "/tmp/test_current.jpg.tmp"
        )
```

- [ ] **Step 10: Run test — should PASS**

Run: `python -m pytest tests/test_mural_poller.py::TestDownloadImage::test_write_error_cleans_up_tmp -v`
Expected: PASS

- [ ] **Step 11: Run all download_image tests together**

Run: `python -m pytest tests/test_mural_poller.py::TestDownloadImage -v`
Expected: All 4 tests PASS.

- [ ] **Step 12: Commit**

```bash
git add tests/test_mural_poller.py mural_poller.py
git commit -m "feat: add download_image with atomic writes and cleanup (TDD red→green)"
```

---

## Chunk 2: Backoff, poll_once, run loop

### Task 5: get_sleep_duration — Exponential Backoff

**Files:**
- Modify: `tests/test_mural_poller.py`
- Modify: `mural_poller.py`

- [ ] **Step 1: Write failing test for normal sleep duration**

Add to `tests/test_mural_poller.py`:

```python
class TestGetSleepDuration:
    """Tests for MuralPoller.get_sleep_duration()."""

    def _make_poller(self, poll_interval=15):
        """Create a MuralPoller with test defaults."""
        logger = logging.getLogger("test")
        return MuralPoller(
            mural_url="http://example.com/api/mural/latest",
            poll_interval=poll_interval,
            image_path="current.jpg",
            logger=logger,
        )

    def test_returns_poll_interval_when_no_errors(self):
        """Returns poll_interval when backoff_level is 0."""
        poller = self._make_poller(poll_interval=15)
        assert poller.get_sleep_duration() == 15
```

- [ ] **Step 2: Run test to verify it fails (RED)**

Run: `python -m pytest tests/test_mural_poller.py::TestGetSleepDuration::test_returns_poll_interval_when_no_errors -v`
Expected: FAIL — `get_sleep_duration` doesn't exist.

- [ ] **Step 3: Implement get_sleep_duration**

Add to `MuralPoller` class in `mural_poller.py`:

```python
    def get_sleep_duration(self):
        """Calculate the sleep duration based on current backoff state.

        Returns:
            poll_interval when no errors, otherwise the backoff
            duration from BACKOFF_SCHEDULE (capped at 120s).
        """
        if self.backoff_level == 0:
            return self.poll_interval
        index = min(self.backoff_level - 1, len(BACKOFF_SCHEDULE) - 1)
        return BACKOFF_SCHEDULE[index]
```

- [ ] **Step 4: Run test to verify it passes (GREEN)**

Run: `python -m pytest tests/test_mural_poller.py::TestGetSleepDuration::test_returns_poll_interval_when_no_errors -v`
Expected: PASS

- [ ] **Step 5: Write tests for backoff schedule**

```python
    def test_returns_backoff_values_on_errors(self):
        """Returns correct backoff for each error level."""
        poller = self._make_poller()
        expected = [5, 10, 20, 40, 80, 120]
        for i, expected_duration in enumerate(expected):
            poller.backoff_level = i + 1
            assert poller.get_sleep_duration() == expected_duration

    def test_backoff_caps_at_120(self):
        """Backoff never exceeds 120 seconds."""
        poller = self._make_poller()
        poller.backoff_level = 100
        assert poller.get_sleep_duration() == 120

    def test_backoff_resets_to_poll_interval(self):
        """After reset, returns poll_interval again."""
        poller = self._make_poller(poll_interval=10)
        poller.backoff_level = 3
        assert poller.get_sleep_duration() == 20
        poller.backoff_level = 0
        assert poller.get_sleep_duration() == 10
```

- [ ] **Step 6: Run tests — should all PASS**

Run: `python -m pytest tests/test_mural_poller.py::TestGetSleepDuration -v`
Expected: All 4 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/test_mural_poller.py mural_poller.py
git commit -m "feat: add get_sleep_duration with exponential backoff (TDD red→green)"
```

---

### Task 6: poll_once — Single Poll Cycle

**Files:**
- Modify: `tests/test_mural_poller.py`
- Modify: `mural_poller.py`

`poll_once()` orchestrates one cycle: check redirect, compare, download if changed. It catches all errors, logs them, and manages backoff state.

- [ ] **Step 1: Write failing test for new location triggers download**

Add to `tests/test_mural_poller.py`:

```python
class TestPollOnce:
    """Tests for MuralPoller.poll_once()."""

    def _make_poller(self):
        """Create a MuralPoller with test defaults."""
        logger = logging.getLogger("test")
        return MuralPoller(
            mural_url="http://example.com/api/mural/latest",
            poll_interval=15,
            image_path="current.jpg",
            logger=logger,
        )

    @patch.object(MuralPoller, "download_image", return_value=True)
    @patch.object(
        MuralPoller,
        "check_redirect",
        return_value="https://cdn.example.com/new.jpg",
    )
    def test_new_location_triggers_download(
        self, mock_check, mock_download
    ):
        """New Location URL triggers image download."""
        poller = self._make_poller()
        poller.current_location = "https://cdn.example.com/old.jpg"

        result = poller.poll_once()

        assert result is True
        mock_download.assert_called_once_with(
            "https://cdn.example.com/new.jpg"
        )
        assert poller.current_location == (
            "https://cdn.example.com/new.jpg"
        )
```

- [ ] **Step 2: Run test to verify it fails (RED)**

Run: `python -m pytest tests/test_mural_poller.py::TestPollOnce::test_new_location_triggers_download -v`
Expected: FAIL — `poll_once` doesn't exist.

- [ ] **Step 3: Implement poll_once**

Add to `MuralPoller` class in `mural_poller.py`:

```python
    def poll_once(self):
        """Execute one poll cycle.

        Checks the API for a new image URL. If the URL has changed
        (or this is the first poll), downloads the new image.

        Returns:
            True if a new image was downloaded, False otherwise.
        """
        try:
            location = self.check_redirect()
            self.backoff_level = 0

            if location == self.current_location:
                self.logger.debug("No change detected")
                return False

            self.logger.info(
                "New mural detected: %s", location
            )
            self.download_image(location)
            self.current_location = location
            return True
        except Exception as e:
            self.backoff_level += 1
            self.logger.error(
                "Poll error (backoff level %d): %s",
                self.backoff_level, e
            )
            return False
```

- [ ] **Step 4: Run test to verify it passes (GREEN)**

Run: `python -m pytest tests/test_mural_poller.py::TestPollOnce::test_new_location_triggers_download -v`
Expected: PASS

- [ ] **Step 5: Write test for same location skips download**

```python
    @patch.object(MuralPoller, "download_image")
    @patch.object(
        MuralPoller,
        "check_redirect",
        return_value="https://cdn.example.com/same.jpg",
    )
    def test_same_location_skips_download(
        self, mock_check, mock_download
    ):
        """Same Location URL does not trigger download."""
        poller = self._make_poller()
        poller.current_location = "https://cdn.example.com/same.jpg"

        result = poller.poll_once()

        assert result is False
        mock_download.assert_not_called()
```

- [ ] **Step 6: Run test — should PASS**

Run: `python -m pytest tests/test_mural_poller.py::TestPollOnce::test_same_location_skips_download -v`
Expected: PASS

- [ ] **Step 7: Write test for first iteration always downloads**

```python
    @patch.object(MuralPoller, "download_image", return_value=True)
    @patch.object(
        MuralPoller,
        "check_redirect",
        return_value="https://cdn.example.com/first.jpg",
    )
    def test_first_iteration_always_downloads(
        self, mock_check, mock_download
    ):
        """First poll (current_location is None) always downloads."""
        poller = self._make_poller()
        assert poller.current_location is None

        result = poller.poll_once()

        assert result is True
        mock_download.assert_called_once_with(
            "https://cdn.example.com/first.jpg"
        )
        assert poller.current_location == (
            "https://cdn.example.com/first.jpg"
        )
```

- [ ] **Step 8: Run test — should PASS**

Run: `python -m pytest tests/test_mural_poller.py::TestPollOnce::test_first_iteration_always_downloads -v`
Expected: PASS

- [ ] **Step 9: Write test for error increments backoff**

```python
    @patch.object(
        MuralPoller,
        "check_redirect",
        side_effect=URLError("Connection refused"),
    )
    def test_error_increments_backoff(self, mock_check):
        """Network error increments backoff_level."""
        poller = self._make_poller()
        assert poller.backoff_level == 0

        poller.poll_once()
        assert poller.backoff_level == 1

        poller.poll_once()
        assert poller.backoff_level == 2
```

- [ ] **Step 10: Run test — should PASS**

Run: `python -m pytest tests/test_mural_poller.py::TestPollOnce::test_error_increments_backoff -v`
Expected: PASS

- [ ] **Step 11: Write test for success resets backoff**

```python
    @patch.object(MuralPoller, "download_image", return_value=True)
    @patch.object(
        MuralPoller,
        "check_redirect",
        return_value="https://cdn.example.com/new.jpg",
    )
    def test_success_resets_backoff(self, mock_check, mock_download):
        """Successful poll resets backoff_level to 0."""
        poller = self._make_poller()
        poller.backoff_level = 3

        poller.poll_once()

        assert poller.backoff_level == 0
```

- [ ] **Step 12: Run test — should PASS**

Run: `python -m pytest tests/test_mural_poller.py::TestPollOnce::test_success_resets_backoff -v`
Expected: PASS

- [ ] **Step 13: Run all poll_once tests together**

Run: `python -m pytest tests/test_mural_poller.py::TestPollOnce -v`
Expected: All 5 tests PASS.

- [ ] **Step 14: Commit**

```bash
git add tests/test_mural_poller.py mural_poller.py
git commit -m "feat: add poll_once — orchestrates check, compare, download (TDD red→green)"
```

---

### Task 7: run — Main Loop

**Files:**
- Modify: `tests/test_mural_poller.py`
- Modify: `mural_poller.py`

`run()` loops: calls `poll_once()`, sleeps for `get_sleep_duration()`, exits when `shutdown_event` is set.

- [ ] **Step 1: Write failing test for loop exits on shutdown_event**

Add to `tests/test_mural_poller.py`:

```python
import threading


class TestRun:
    """Tests for MuralPoller.run()."""

    def _make_poller(self):
        """Create a MuralPoller with test defaults."""
        logger = logging.getLogger("test")
        return MuralPoller(
            mural_url="http://example.com/api/mural/latest",
            poll_interval=15,
            image_path="current.jpg",
            logger=logger,
        )

    @patch.object(MuralPoller, "get_sleep_duration", return_value=0)
    @patch.object(MuralPoller, "poll_once", return_value=False)
    def test_exits_when_shutdown_event_set(
        self, mock_poll, mock_sleep_dur
    ):
        """Run loop exits when shutdown_event is set."""
        poller = self._make_poller()
        event = threading.Event()

        # Set event after first poll_once call
        def stop_after_first_call():
            event.set()
            return False

        mock_poll.side_effect = stop_after_first_call

        poller.run(shutdown_event=event)

        mock_poll.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails (RED)**

Run: `python -m pytest tests/test_mural_poller.py::TestRun::test_exits_when_shutdown_event_set -v`
Expected: FAIL — `run` method doesn't exist.

- [ ] **Step 3: Implement run**

Add to `MuralPoller` class in `mural_poller.py`:

```python
    def run(self, shutdown_event=None):
        """Main polling loop.

        Continuously polls for new images and sleeps between polls.
        Exits gracefully when shutdown_event is set.

        Args:
            shutdown_event: A threading.Event that signals the loop
                to exit. If None, loops forever.
        """
        self.logger.info(
            "Starting poller: url=%s interval=%ds",
            self.mural_url, self.poll_interval
        )
        while True:
            self.poll_once()
            sleep_duration = self.get_sleep_duration()
            if shutdown_event is not None:
                if shutdown_event.wait(sleep_duration):
                    self.logger.info("Shutdown event received")
                    break
            else:
                time.sleep(sleep_duration)
```

- [ ] **Step 4: Run test to verify it passes (GREEN)**

Run: `python -m pytest tests/test_mural_poller.py::TestRun::test_exits_when_shutdown_event_set -v`
Expected: PASS

- [ ] **Step 5: Write test for run handles errors gracefully**

```python
    @patch.object(MuralPoller, "get_sleep_duration", return_value=0)
    @patch.object(
        MuralPoller,
        "poll_once",
        side_effect=[False, False],
    )
    def test_continues_after_errors(
        self, mock_poll, mock_sleep_dur
    ):
        """Run loop continues polling after errors."""
        poller = self._make_poller()
        event = threading.Event()

        call_count = [0]

        def count_and_stop(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 2:
                event.set()
            return False

        mock_poll.side_effect = count_and_stop

        poller.run(shutdown_event=event)

        assert mock_poll.call_count == 2
```

- [ ] **Step 6: Run test — should PASS**

Run: `python -m pytest tests/test_mural_poller.py::TestRun::test_continues_after_errors -v`
Expected: PASS

- [ ] **Step 7: Write test for correct sleep duration between polls**

```python
    @patch.object(MuralPoller, "poll_once", return_value=False)
    def test_sleeps_correct_duration(self, mock_poll):
        """Run loop uses get_sleep_duration for wait time."""
        poller = self._make_poller()
        poller.backoff_level = 1  # Should sleep 5s
        event = threading.Event()

        def stop_immediately(*args, **kwargs):
            event.set()
            return False

        mock_poll.side_effect = stop_immediately

        with patch.object(event, "wait", return_value=True) as mock_wait:
            poller.run(shutdown_event=event)
            mock_wait.assert_called_once_with(5)
```

- [ ] **Step 8: Run test — should PASS**

Run: `python -m pytest tests/test_mural_poller.py::TestRun::test_sleeps_correct_duration -v`
Expected: PASS

- [ ] **Step 9: Run all run tests together**

Run: `python -m pytest tests/test_mural_poller.py::TestRun -v`
Expected: All 3 tests PASS.

- [ ] **Step 10: Run full test suite with coverage**

Run: `python -m pytest tests/ -v --cov=mural_poller --cov-branch --cov-report=term-missing`
Expected: All tests PASS. Check coverage report for any uncovered lines/branches. If coverage is not 100%, note which lines are uncovered — they will be addressed in Task 8 (coverage gap cleanup).

- [ ] **Step 11: Commit**

```bash
git add tests/test_mural_poller.py mural_poller.py
git commit -m "feat: add run loop with shutdown event support (TDD red→green)"
```

---

## Chunk 3: Coverage Gaps, Service, node.lua, Package Files, Linting

### Task 8: Coverage Gap Cleanup

**Files:**
- Modify: `tests/test_mural_poller.py`
- Modify: `mural_poller.py` (only if needed for refactoring)

After all core logic is implemented, run coverage and add tests for any uncovered lines or branches.

- [ ] **Step 1: Run full coverage report**

Run: `python -m pytest tests/ -v --cov=mural_poller --cov-branch --cov-report=term-missing`

Examine the output. Common uncovered lines may include:
- The `except ImportError` branch of the urllib import (only one branch runs under Python 3)
- The `else: time.sleep()` branch in `run()` (tests always use `shutdown_event`)
- The `_NoRedirectHandler` methods for 301/302 (only 307 is tested)
- The logging `.info()` call in `download_image()`
- The `os.remove` failure branch in `download_image()` cleanup

- [ ] **Step 2: Write tests for any uncovered branches**

For each uncovered branch, write a targeted test. Examples:

For the `run()` without shutdown_event (the `else: time.sleep()` branch), add:

```python
    @patch("mural_poller.time.sleep")
    @patch.object(MuralPoller, "poll_once")
    def test_run_without_shutdown_event_uses_time_sleep(
        self, mock_poll, mock_sleep
    ):
        """Run without shutdown_event uses time.sleep."""
        poller = self._make_poller()
        call_count = [0]

        def stop_after_one(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 1:
                raise KeyboardInterrupt
            return False

        mock_poll.side_effect = stop_after_one

        try:
            poller.run()
        except KeyboardInterrupt:
            pass

        mock_sleep.assert_called()
```

For the `os.remove` OSError branch in `download_image()`:

```python
    @patch("mural_poller.os.remove", side_effect=OSError("not found"))
    @patch("mural_poller.build_opener")
    def test_network_error_ignores_missing_tmp(
        self, mock_build_opener, mock_remove
    ):
        """Cleanup silently ignores missing .tmp file."""
        mock_opener = MagicMock()
        mock_opener.open.side_effect = URLError("Connection refused")
        mock_build_opener.return_value = mock_opener

        poller = self._make_poller()
        with pytest.raises(URLError):
            poller.download_image(
                "https://cdn.example.com/mural.jpg"
            )
        # No additional error raised from os.remove failure
```

- [ ] **Step 3: Run full test suite and verify 100% coverage**

Run: `python -m pytest tests/ -v --cov=mural_poller --cov-branch --cov-report=term-missing --cov-fail-under=100`
Expected: PASS with 100% line + branch coverage.

If the `except ImportError` branch of the urllib import block cannot be covered (it's Python 2 only), exclude it with a `# pragma: no cover` comment on the `except ImportError:` line only — this is the standard approach for polyglot import blocks.

- [ ] **Step 4: Commit**

```bash
git add tests/test_mural_poller.py mural_poller.py
git commit -m "test: close coverage gaps — 100% line + branch coverage"
```

---

### Task 9: service — Entry Point

**Files:**
- Create: `service`

This is a thin wrapper, not tested in pytest. Write it, make it executable, verify it parses correctly.

- [ ] **Step 1: Write the `service` file**

Create `service`:

```python
#!/usr/bin/python
"""StoryField mural display service — polls API for new images."""
from __future__ import print_function

import sys
import logging

from hosted import config
from mural_poller import MuralPoller

# Auto-restart when config changes in the dashboard
config.restart_on_update()

# Set up logging to stderr with timestamps
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("mural_service")

# Read config
mural_url = config.mural_url
poll_interval = config.poll_interval

# Run the poller
poller = MuralPoller(
    mural_url=mural_url,
    poll_interval=poll_interval,
    image_path="current.jpg",
    logger=logger,
)
poller.run()
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x service`

- [ ] **Step 3: Verify syntax is valid Python 3**

Run: `python -c "import py_compile; py_compile.compile('service', doraise=True)"`
Expected: No errors (note: the `from hosted import config` will fail at runtime without the real SDK, but the syntax is valid).

- [ ] **Step 4: Commit**

```bash
git add service
git commit -m "feat: add service entry point — thin wrapper around MuralPoller"
```

---

### Task 10: node.lua — Display with Crossfade

**Files:**
- Create: `node.lua`

This file is not tested in pytest — it runs in the info-beamer Lua environment and will be validated on-device.

- [ ] **Step 1: Write `node.lua`**

Create `node.lua`:

```lua
-- StoryField Mural Display
-- Displays mural images with dissolve crossfade transitions

gl.setup(NATIVE_WIDTH, NATIVE_HEIGHT)
util.init_hosted()

-- Config
local dissolve_duration = 1.5

-- Image state
local current_image = resource.load_image("default.webp")
local old_image = nil
local transition_start = nil

-- Update config when changed in dashboard
node.event("config_update", function(config)
    dissolve_duration = config.dissolve_duration or 1.5
end)

-- Watch for new mural images written by the service
util.file_watch("current.jpg", function(raw)
    -- Dispose the outgoing old image if mid-transition
    if old_image then
        old_image:dispose()
    end
    -- Current becomes old (will fade out)
    old_image = current_image
    -- Load new image (will fade in)
    current_image = resource.load_image{ file = "current.jpg" }
    -- Start transition
    transition_start = sys.now()
end)

-- Cover scaling: fill screen, maintain aspect ratio, center crop
local function draw_cover(image, alpha)
    if not image then
        return
    end
    local img_w, img_h = image:size()
    if img_w == 0 or img_h == 0 then
        return
    end
    local screen_w = NATIVE_WIDTH
    local screen_h = NATIVE_HEIGHT
    local scale = math.max(screen_w / img_w, screen_h / img_h)
    local draw_w = img_w * scale
    local draw_h = img_h * scale
    local x = (screen_w - draw_w) / 2
    local y = (screen_h - draw_h) / 2
    image:draw(x, y, x + draw_w, y + draw_h, alpha)
end

function node.render()
    gl.clear(0, 0, 0, 1)

    if transition_start then
        local elapsed = sys.now() - transition_start
        local progress = elapsed / dissolve_duration
        if progress >= 1.0 then
            -- Transition complete
            if old_image then
                old_image:dispose()
                old_image = nil
            end
            transition_start = nil
            draw_cover(current_image, 1.0)
        else
            -- Mid-transition: crossfade
            draw_cover(old_image, 1.0 - progress)
            draw_cover(current_image, progress)
        end
    else
        -- No transition in progress
        draw_cover(current_image, 1.0)
    end
end
```

- [ ] **Step 2: Review the code against the spec**

Verify:
- `gl.setup(NATIVE_WIDTH, NATIVE_HEIGHT)` — present
- `util.init_hosted()` — present
- `node.event("config_update", ...)` — present
- `util.file_watch("current.jpg", ...)` — present
- Cover scaling — present
- GPU disposal — present (dispose old_image on transition complete and on mid-transition new file)
- Max 3 textures — ensured (default/current_image + old_image + new current_image)

- [ ] **Step 3: Commit**

```bash
git add node.lua
git commit -m "feat: add node.lua — crossfade display with cover scaling"
```

---

### Task 11: Package Metadata and Assets

**Files:**
- Create: `node.json`
- Create: `package.json`
- Create: `default.webp`
- Create: `package.png`

- [ ] **Step 1: Create `node.json`**

```json
{
    "name": "StoryField Mural Projector",
    "permissions": {
        "network": "true"
    },
    "options": [
        {
            "title": "Mural API URL",
            "name": "mural_url",
            "type": "string",
            "default": "https://storyfield.net/api/mural/latest"
        },
        {
            "title": "Poll Interval (seconds)",
            "name": "poll_interval",
            "type": "integer",
            "default": 15
        },
        {
            "title": "Dissolve Duration (seconds)",
            "name": "dissolve_duration",
            "type": "float",
            "default": 1.5
        }
    ]
}
```

Note: Using `"network": "true"` (string) per `PROJECT_OVERVIEW.md` section 1.2. The design spec shows boolean `true` — this is a known deviation; the authoritative `PROJECT_OVERVIEW.md` takes precedence. Verify on-device which form info-beamer requires.

- [ ] **Step 2: Create `package.json`**

```json
{
    "name": "StoryField Mural Display",
    "author": "Mike Subelsky",
    "desc": "Polls a URL for updated mural images and displays them with dissolve crossfade transitions. Built for the StoryField live art installation."
}
```

- [ ] **Step 3: Create `default.webp` — transparent 1x1 WebP placeholder**

Run: `python3 -c "
import struct, io
# Minimal 1x1 transparent WebP (RIFF container with VP8L lossless)
# VP8L signature + 1x1 ARGB with alpha=0
data = bytes([
    0x52, 0x49, 0x46, 0x46,  # RIFF
    0x1a, 0x00, 0x00, 0x00,  # file size - 8
    0x57, 0x45, 0x42, 0x50,  # WEBP
    0x56, 0x50, 0x38, 0x4c,  # VP8L
    0x0d, 0x00, 0x00, 0x00,  # chunk size
    0x2f, 0x00, 0x00, 0x00,  # signature
    0x00, 0x00, 0x00, 0x00,  # 1x1
    0x00, 0x00, 0x00, 0x00,  # transparent
    0x00,
])
with open('default.webp', 'wb') as f:
    f.write(data)
print('Created default.webp')
"
`

If the above doesn't produce a valid WebP, use an alternative approach:

Run: `python3 -c "
# Create minimal valid transparent WebP using Pillow if available
try:
    from PIL import Image
    img = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
    img.save('default.webp', 'WEBP', lossless=True)
    print('Created default.webp via Pillow')
except ImportError:
    # Fallback: create a 1x1 transparent PNG instead
    import struct, zlib
    def create_png():
        sig = b'\x89PNG\r\n\x1a\n'
        ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0)
        ihdr = b'IHDR' + ihdr_data
        ihdr_chunk = struct.pack('>I', 13) + ihdr + struct.pack('>I', zlib.crc32(ihdr) & 0xffffffff)
        raw = b'\x00\x00\x00\x00\x00'
        compressed = zlib.compress(raw)
        idat = b'IDAT' + compressed
        idat_chunk = struct.pack('>I', len(compressed)) + idat + struct.pack('>I', zlib.crc32(idat) & 0xffffffff)
        iend = b'IEND'
        iend_chunk = struct.pack('>I', 0) + iend + struct.pack('>I', zlib.crc32(iend) & 0xffffffff)
        return sig + ihdr_chunk + idat_chunk + iend_chunk
    with open('default.webp', 'wb') as f:
        f.write(create_png())
    print('WARNING: Created PNG, rename to .webp — may need conversion')
"
`

Verify: `python3 -c "import os; print(os.path.getsize('default.webp'), 'bytes')"`
Expected: Small file (<1KB).

- [ ] **Step 4: Create `package.png` — 64x64 placeholder icon**

Run: `python3 -c "
import struct, zlib

def create_png_64x64():
    \"\"\"Create a 64x64 dark gray PNG as placeholder icon.\"\"\"
    sig = b'\x89PNG\r\n\x1a\n'
    width, height = 64, 64
    bit_depth, color_type = 8, 2  # 8-bit RGB

    # IHDR
    ihdr_data = struct.pack('>IIBBBBB', width, height, bit_depth, color_type, 0, 0, 0)
    ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
    ihdr_chunk = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)

    # IDAT - dark gray pixels
    raw_data = b''
    for y in range(height):
        raw_data += b'\x00'  # filter byte
        raw_data += b'\x33\x33\x33' * width  # dark gray RGB

    compressed = zlib.compress(raw_data)
    idat_crc = zlib.crc32(b'IDAT' + compressed) & 0xffffffff
    idat_chunk = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc)

    # IEND
    iend_crc = zlib.crc32(b'IEND') & 0xffffffff
    iend_chunk = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)

    with open('package.png', 'wb') as f:
        f.write(sig + ihdr_chunk + idat_chunk + iend_chunk)
    print('Created package.png (64x64)')

create_png_64x64()
"
`

Verify: `python3 -c "import os; print(os.path.getsize('package.png'), 'bytes')"`
Expected: Small file (<8KB).

- [ ] **Step 5: Commit**

```bash
git add node.json package.json default.webp package.png
git commit -m "feat: add package metadata — node.json, package.json, assets"
```

---

### Task 12: Vendor SDK Files

**Files:**
- Create: `hosted.lua`
- Create: `hosted.py`

Download from the info-beamer package-sdk repository.

- [ ] **Step 1: Download hosted.lua**

Run: `curl -fsSL https://raw.githubusercontent.com/info-beamer/package-sdk/master/hosted.lua -o hosted.lua`
Expected: File downloaded successfully.

If curl fails (network restrictions), create a placeholder with a comment:

```lua
-- Placeholder: download from https://github.com/info-beamer/package-sdk
-- This file must be replaced with the real hosted.lua before deployment
```

- [ ] **Step 2: Download hosted.py**

Run: `curl -fsSL https://raw.githubusercontent.com/info-beamer/package-sdk/master/hosted.py -o hosted.py`
Expected: File downloaded successfully.

If curl fails, create a placeholder with a comment:

```python
# Placeholder: download from https://github.com/info-beamer/package-sdk
# This file must be replaced with the real hosted.py before deployment
```

- [ ] **Step 3: Verify files exist**

Run: `ls -la hosted.lua hosted.py`
Expected: Both files present.

- [ ] **Step 4: Commit**

```bash
git add hosted.lua hosted.py
git commit -m "chore: vendor info-beamer SDK files (hosted.lua, hosted.py)"
```

---

### Task 13: Linting and Final Validation

**Files:**
- Possibly modify: `mural_poller.py`, `service` (to fix lint issues)

- [ ] **Step 1: Run flake8**

Run: `python -m flake8 mural_poller.py service`
Expected: Zero warnings. If there are warnings, fix them.

- [ ] **Step 2: Run pylint on mural_poller.py**

Run: `python -m pylint mural_poller.py`
Expected: Score 10.00/10 or close. Fix any errors (warnings/conventions are OK to suppress if justified).

- [ ] **Step 3: Run pylint on service**

Run: `python -m pylint service --disable=import-error`
Expected: No errors. The `--disable=import-error` is needed because `hosted` is not installable in the dev environment.

- [ ] **Step 4: Run full test suite with strict coverage**

Run: `python -m pytest tests/ -v --cov=mural_poller --cov-branch --cov-report=term-missing --cov-fail-under=100`
Expected: All tests PASS, 100% coverage.

- [ ] **Step 5: Fix any issues found in steps 1-4**

If any lint or coverage issues, fix them and re-run.

- [ ] **Step 6: Commit any fixes**

```bash
git add mural_poller.py service
git commit -m "chore: fix lint issues and finalize code quality"
```

---

### Task 14: README Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README.md**

```markdown
# StoryField Mural Display

An info-beamer hosted package that displays mural images from the StoryField live art installation with dissolve crossfade transitions.

## Overview

This package polls the StoryField API for updated mural images and displays them fullscreen on a Raspberry Pi 5 connected to a projector. When a new mural is detected, the display crossfades from the old image to the new one.

## Configuration

Configure via the info-beamer dashboard:

| Option | Default | Description |
|--------|---------|-------------|
| Mural API URL | `https://storyfield.net/api/mural/latest` | API endpoint returning a 307 redirect to the current mural image |
| Poll Interval | 15 seconds | How often to check for new images |
| Dissolve Duration | 1.5 seconds | Duration of the crossfade transition |

## Requirements

- Raspberry Pi 5
- info-beamer OS 14+
- Network access to storyfield.net and Vercel blob CDN

## Development

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
python -m pytest tests/ -v --cov=mural_poller --cov-branch

# Run linting
python -m flake8 mural_poller.py service
python -m pylint mural_poller.py
```

## Architecture

- `mural_poller.py` — Core logic: polling, redirect detection, image download, exponential backoff
- `service` — Entry point that reads info-beamer config and runs the poller
- `node.lua` — Display rendering with dissolve crossfade and cover scaling

## License

Proprietary — StoryField project.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README with usage, config, and development instructions"
```
