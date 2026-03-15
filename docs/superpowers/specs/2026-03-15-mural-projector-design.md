# StoryField Mural Projector — Implementation Design

## Overview

An info-beamer hosted package for Raspberry Pi 5 that polls a URL for updated mural images and displays them fullscreen with dissolve crossfade transitions. Drives a laser projector in a gallery setting for the StoryField live art installation.

Authoritative spec: `PROJECT_OVERVIEW.md`

## File Structure

```
mural_projector/
├── node.lua              # Display: crossfade rendering, file watching
├── node.json             # Config schema + network permission
├── service               # Thin entry point: reads config, runs poller
├── mural_poller.py       # Core logic: poll, compare, download, write
├── hosted.lua            # Vendored info-beamer Lua SDK
├── hosted.py             # Vendored info-beamer Python SDK
├── package.json          # Package metadata
├── package.png           # 64x64 icon
├── default.webp          # Transparent placeholder image
├── README.md             # Usage documentation
├── PROJECT_OVERVIEW.md   # Authoritative spec
├── tests/
│   ├── __init__.py
│   ├── test_mural_poller.py   # Unit tests for core logic
│   └── conftest.py            # Shared fixtures
├── .flake8               # flake8 config
├── .pylintrc             # pylint config
└── requirements-dev.txt  # pytest, pytest-cov, flake8, pylint
```

## Core Logic: `mural_poller.py`

A single `MuralPoller` class with zero info-beamer awareness. Receives config as plain values.

### Constructor

```
MuralPoller(mural_url, poll_interval, image_path, logger)
```

### State

- `current_location` — last-seen `Location` header URL (starts `None`)
- `backoff_level` — current error backoff multiplier (resets on success)

### Methods

**`check_redirect()`** — Sends a request to `mural_url` with `allow_redirects=False` and a 10s timeout. Returns the `Location` header value on HTTP 307 (case-insensitive header lookup). On a 200 response, returns the response body for content-hash comparison. Raises on 5xx, network errors, or missing `Location` header on 307.

**`download_image(url)`** — Downloads image from CDN URL with a 30s timeout. Writes to `<image_path>.tmp`, then `os.rename()` to `image_path`. Cleans up `.tmp` on failure. Returns `True` on success.

**`poll_once()`** — One poll cycle: calls `check_redirect()`, compares to `current_location`, calls `download_image()` if changed, updates state. Returns `True` if a new image was downloaded. Catches errors, logs them, increments backoff.

**`get_sleep_duration()`** — Returns `poll_interval` on success. On error: exponential backoff at 5s, 10s, 20s, 40s, 80s, 120s cap. Resets after any successful `check_redirect()`.

**`run(shutdown_event=None)`** — Main loop: calls `poll_once()`, sleeps for `get_sleep_duration()`, exits when `shutdown_event` is set. The `shutdown_event` is a `threading.Event` for graceful shutdown and testability.

### Error Handling

- Network errors in `check_redirect()` or `download_image()` are caught in `poll_once()`, logged, and increment `backoff_level`
- Any successful `check_redirect()` (whether or not the image changed) resets `backoff_level` to 0
- `download_image()` cleans up `.tmp` file on failure

### Python 2/3 Compatibility

- `from __future__ import print_function`
- `try: from urllib.request import ... except ImportError: from urllib2 import ...`
- `.format()` strings only — no f-strings, no type annotations
- `os.rename()` for atomic writes, not pathlib

## Entry Point: `service`

A thin script (~15-20 lines) with shebang `#!/usr/bin/python`.

The `service` file must be executable (`chmod +x`) with shebang `#!/usr/bin/python`.

Responsibilities:
1. Import `hosted.py`, call `config.restart_on_update()` to auto-restart on dashboard config changes
2. Extract `mural_url`, `poll_interval` from config
3. Set up a logger writing to stderr with timestamps
4. Construct `MuralPoller(mural_url, poll_interval, image_path="current.jpg", logger=logger)`
5. Call `poller.run()`

No business logic. If `hosted.py` or config fails, it crashes — info-beamer restarts the service automatically.

## Display: `node.lua`

### Startup

- Call `gl.setup(NATIVE_WIDTH, NATIVE_HEIGHT)` to use the display's native resolution
- Call `util.init_hosted()` to initialize the config system
- Load `default.webp` as initial texture via `resource.load_image("default.webp")` (transparent — renders as blank on laser projector)
- `current_image` = this texture, `next_image` = `nil`, `transition_start` = `nil`
- Initialize `dissolve_duration` from config default (1.5s)

### Config Updates

- Listen for config changes via `node.event("config_update", function(config) ... end)`
- Update `dissolve_duration` from the config table when it changes

### File Watching

- `util.file_watch("current.jpg", callback)` triggers whenever the file changes on disk (info-beamer inotify)
- In the callback: load the new image via `resource.load_image{ file = "current.jpg" }`, assign to `next_image`, set `transition_start` to current time
- Immediate — no debounce. Atomic rename guarantees file integrity.

### Rendering (`node.render()`)

Called every frame by info-beamer.

- **No transition:** Draw `current_image` with cover scaling
- **Transition in progress:**
  - `progress` = `(now - transition_start) / dissolve_duration`, clamped 0-1
  - Draw `current_image` at alpha `1 - progress`
  - Draw `next_image` at alpha `progress`
  - On completion: dispose `current_image`, promote `next_image` to `current_image`, clear transition state

### Cover Scaling

- Scale factor: `max(screen_w / img_w, screen_h / img_h)`
- Center the scaled image — overflow cropped equally on both sides

### GPU Memory

- Max 3 textures at any time (default placeholder, outgoing old image, incoming current image)
- Dispose the outgoing image immediately when the dissolve completes
- Mid-transition new file: dispose the outgoing `current_image`, promote `next_image` to `current_image`, load the new file as the new `next_image`, restart transition

## Configuration: `node.json`

```json
{
    "name": "StoryField Mural Projector",
    "permissions": {
        "network": true
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

## API Contract

- Endpoint: `GET https://<hostname>/api/mural/latest`
- Expected response: HTTP 307 with `Location` header pointing to Vercel blob CDN
- Compare `Location` URL to detect changes; only download if changed
- `Location` header lookup must be case-insensitive (handle `Location`, `location`, etc.)
- Timeouts: 10s on redirect check, 30s on image download

### Edge Cases

- **307 with Location** — primary happy path, compare URL to detect changes
- **200 response** — treat as direct image response, hash content to detect changes
- **5xx error** — retry with backoff
- **Missing Location header on 307** — log warning, retry with backoff
- **Network timeout** — retry with backoff

## Testing Strategy

### Methodology: Strict Red/Green TDD

1. Write a test for a specific behavior — see it fail (red)
2. Write the minimum code to make it pass (green)
3. Refactor if needed, tests stay green
4. Repeat for next behavior

Tests, once written in the red phase, must not be modified in the green phase.

### Framework

pytest + pytest-cov, Python 3 only. Coverage: 100% line + branch (`--cov-fail-under=100 --cov-branch`).

### Test Coverage (`test_mural_poller.py`)

**`check_redirect()`:**
- 307 returns Location header value
- 307 with case-variant header (`location`, `LOCATION`) still returns value
- 307 with missing Location header raises
- 200 response returns body for content-hash comparison
- 5xx status codes raise
- Network timeout (10s) raises
- Network errors raise

**`download_image()`:**
- Successful download writes atomically (verify `.tmp` then rename)
- Network error during download cleans up `.tmp`
- Download timeout (30s) cleans up `.tmp`
- Write error cleans up `.tmp`

**`poll_once()`:**
- New Location triggers download
- Same Location skips download
- First iteration (no previous URL) always downloads
- Error increments backoff
- Success resets backoff

**`get_sleep_duration()`:**
- Returns `poll_interval` when no errors
- Returns correct backoff values (5, 10, 20, 40, 80, 120 cap)
- Resets after success

**`run()`:**
- Loops until `shutdown_event` is set
- Handles errors gracefully without crashing
- Sleeps correct duration between polls

### Mocking

- Mock `urllib2`/`urllib.request` at module level for all network I/O
- Mock `os.rename` and file writes for filesystem operations
- `threading.Event` for `shutdown_event` to control run loop in tests
- No mocking of `hosted.py` — it is not imported by `mural_poller.py`

### Not Tested in pytest

- `service` — thin wrapper, testing would require mocking `hosted.py` internals for little value
- `node.lua` — Lua rendering validated on-device
- SDK files — vendored, not our code

### Linting

- flake8 with `--max-complexity=10`
- pylint for static analysis
- Run on `mural_poller.py` and `service`

## SDK Files

`hosted.lua` and `hosted.py` vendored from https://github.com/info-beamer/package-sdk and committed to the repo. Updated manually when needed.
