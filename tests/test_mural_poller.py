"""Tests for mural_poller module — strict red/green TDD."""
from unittest.mock import patch, MagicMock
import logging
import pytest
import socket
try:
    from urllib.error import HTTPError, URLError
except ImportError:
    from urllib2 import HTTPError, URLError

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

    @patch("mural_poller.build_opener")
    def test_307_case_insensitive_location_header(self, mock_build_opener):
        """307 with lowercase 'location' header still returns value."""
        mock_response = MagicMock()
        mock_response.getcode.return_value = 307
        mock_response.info.return_value.get.return_value = (
            "https://cdn.example.com/mural-def456.jpg"
        )
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_response
        mock_build_opener.return_value = mock_opener

        poller = self._make_poller()
        result = poller.check_redirect()

        assert result == "https://cdn.example.com/mural-def456.jpg"

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

    @patch("mural_poller.build_opener")
    def test_network_timeout_raises(self, mock_build_opener):
        """Network timeout raises URLError."""
        mock_opener = MagicMock()
        mock_opener.open.side_effect = URLError(socket.timeout("timed out"))
        mock_build_opener.return_value = mock_opener

        poller = self._make_poller()
        with pytest.raises(URLError):
            poller.check_redirect()

    @patch("mural_poller.build_opener")
    def test_network_error_raises(self, mock_build_opener):
        """General network error raises URLError."""
        mock_opener = MagicMock()
        mock_opener.open.side_effect = URLError("Name or service not known")
        mock_build_opener.return_value = mock_opener

        poller = self._make_poller()
        with pytest.raises(URLError):
            poller.check_redirect()


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
        mock_open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        poller = self._make_poller()
        result = poller.download_image("https://cdn.example.com/mural-abc123.jpg")

        assert result is True
        mock_open.assert_called_once_with("/tmp/test_current.jpg.tmp", "wb")
        mock_file.write.assert_called_once_with(b"fake image bytes")
        mock_rename.assert_called_once_with(
            "/tmp/test_current.jpg.tmp", "/tmp/test_current.jpg"
        )

    @patch("mural_poller.os.remove")
    @patch("mural_poller.build_opener")
    def test_network_error_cleans_up_tmp(self, mock_build_opener, mock_remove):
        """Network error during download cleans up .tmp file."""
        mock_opener = MagicMock()
        mock_opener.open.side_effect = URLError("Connection refused")
        mock_build_opener.return_value = mock_opener

        poller = self._make_poller()
        with pytest.raises(URLError):
            poller.download_image("https://cdn.example.com/mural-abc123.jpg")

        mock_remove.assert_called_once_with("/tmp/test_current.jpg.tmp")

    @patch("mural_poller.os.remove")
    @patch("mural_poller.build_opener")
    def test_download_timeout_cleans_up_tmp(self, mock_build_opener, mock_remove):
        """Download timeout cleans up .tmp file."""
        mock_opener = MagicMock()
        mock_opener.open.side_effect = URLError(socket.timeout("timed out"))
        mock_build_opener.return_value = mock_opener

        poller = self._make_poller()
        with pytest.raises(URLError):
            poller.download_image("https://cdn.example.com/mural-abc123.jpg")

        mock_remove.assert_called_once_with("/tmp/test_current.jpg.tmp")

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
        mock_open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        poller = self._make_poller()
        with pytest.raises(OSError):
            poller.download_image("https://cdn.example.com/mural-abc123.jpg")

        mock_remove.assert_called_once_with("/tmp/test_current.jpg.tmp")


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
