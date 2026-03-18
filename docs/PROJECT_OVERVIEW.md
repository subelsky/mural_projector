# StoryField Mural Display — info-beamer Package Implementation Brief

## Mission

Build a production-grade info-beamer hosted package that polls a URL for updated mural images and displays them fullscreen with a dissolve crossfade transition. This package will drive a live art installation (StoryField) projected in a gallery setting. **It is a can't-fail, high-visibility production deployment.** Reliability, correctness, and defensive coding are paramount.

---

## 1. What is info-beamer?

info-beamer is a digital signage platform for the Raspberry Pi. It runs a custom minimal Linux OS (~60MB) and renders content via a Lua-based OpenGL player. You manage devices through a web dashboard at info-beamer.com.

An info-beamer **package** is the unit of deployable software. It consists of:

- **`node.lua`** — Lua code executed by the info-beamer player. Controls what is rendered on screen each frame via a `node.render()` function called at display refresh rate. Has access to OpenGL, image/video loading, fonts, shaders, etc.
- **`service`** — An executable (typically a Python script) that runs as a background process alongside the Lua player. In the info-beamer docs this file is described as "optional" for packages in general, but **for this package the service is required and essential** — it is responsible for all network I/O (polling the mural API and downloading images). The Lua side and the service communicate through the filesystem: the service writes files, and the Lua side detects changes via inotify (`util.file_watch`). Without the service, the Lua player has no way to fetch images from the network.
- **`node.json`** — Declares the node name, configuration options (exposed in the web dashboard), and permissions.
- **`package.json`** — Package metadata (name, author, description).
- **`package.png`** — A 64×64 PNG icon for the dashboard.
- **`hosted.lua`** — Lua SDK file from [info-beamer/package-sdk](https://github.com/info-beamer/package-sdk). Enables `util.init_hosted()` which parses config.
- **`hosted.py`** — Python SDK file from the same repo. Provides `config`, `node`, `device`, and `api` objects for services.

### Key platform constraints

1. **Python version**: info-beamer OS ships **Python 2.7** as its native runtime — even on the latest OS 14 and OS 15. There is no built-in Python 3. (An experimental `overlay.squashfs` approach exists to bundle Python 3.7, but it's not worth the complexity for this project.) **However**, the development environment is a Python 3 devcontainer (for Claude Code compatibility, modern pytest, and full tooling support). The service code must therefore be written in the **Python 2/3 polyglot subset** — code that runs correctly under both Python 2.7 on the device and Python 3.x in the dev/test environment. The owner will perform early end-to-end validation on the actual Pi 5 device to confirm the polyglot code works under the real Python 2.7 runtime. See section 4 for the specific polyglot rules.
2. **Service sandboxing**: Services run as an unprivileged user in a sandbox. By default they have **no network access**. You must declare `"permissions": { "network": "true" }` in `node.json` to enable outbound HTTP/HTTPS.
3. **Filesystem**: The service's working directory is its node directory. Files written there are visible to the Lua player via inotify. `util.file_watch("filename", callback)` triggers whenever the file changes on disk. **Atomic writes are critical** — write to a `.tmp` file then `os.rename()` to the final name, so the Lua side never reads a half-written file.
4. **Image loading**: `resource.load_image{ file = "filename" }` loads images asynchronously. Supports JPEG, PNG, and (on OS 14+) WebP. The returned image object supports `:draw(x1, y1, x2, y2, alpha)` and `:size()` → `(width, height)`. Images must be explicitly disposed with `:dispose()` when no longer needed, or you will leak GPU memory.
5. **Render loop**: `node.render()` is called every frame. It must be fast. Do not do I/O or blocking work here. Use `gl.clear(r, g, b, a)` to clear, then draw images/text/etc.
6. **Config**: `util.init_hosted()` watches `hosted.lua`, `node.json`, and `config.json` and populates a global `CONFIG` table. When the user changes settings in the dashboard, `config.json` is updated on the device. You can listen for changes via `node.event("config_update", function(config) ... end)`. On the Python side, `from hosted import config` gives you a config object, and `config.restart_on_update()` will auto-restart the service when config changes.
7. **Service lifecycle**: info-beamer OS will auto-restart a crashed service. However, a tight crash loop is wasteful and can interfere with other device operations. Services should catch exceptions, log to stderr, and implement backoff.
8. **Available libraries (Python on-device)**: The info-beamer OS has `urllib2`, `httplib`, `json`, `os`, `sys`, `time`, `traceback`, `hashlib`, `struct`, `socket`, and other Python 2.7 standard library modules. It does NOT have `requests`, `urllib3`, or any pip-installed packages (unless you bundle them via an overlay). The `hosted.py` SDK provides config access and a node communication helper. In your polyglot code, use a try/except import pattern to handle the `urllib2` (Python 2) vs `urllib.request` (Python 3) difference — see section 4.3 for details.
9. **Available libraries (Lua)**: `json` (built-in), `sys` (system info, timing), `gl` (OpenGL), `resource` (asset loading), `util` (file watching, data mapping, etc.). The `math` standard library is available.

### SDK files you need

Download these from https://github.com/info-beamer/package-sdk and include them in the package root:

- `hosted.lua` — required for `util.init_hosted()` in node.lua
- `hosted.py` — required for `from hosted import config, node` in the service

---

## 2. The StoryField mural API

StoryField is a live collaborative art installation. A backend composes user contributions into a mural image and stores it as a Vercel blob.

### Endpoint

```
GET https://<hostname>/api/mural/latest
```

The hostname is configurable. In production it is `storyfield.net`. In development/testing it will be `storyfield.test` or another local hostname. The `mural_url` config option stores the full URL including the hostname, so changing environments is just a dashboard config change.

**Response**: HTTP **307 Temporary Redirect** with a `Location` header pointing to the current Vercel blob URL for the composite mural image. Example:

```
HTTP/1.1 307 Temporary Redirect
Location: https://abcdef123.public.blob.vercel-storage.com/mural-abc123.jpg
```

### Behavior

- The blob URL changes every time a new contribution is composited into the mural. Each new version gets a unique blob URL.
- The blob itself is **heavily CDN-cached** by Vercel. Downloading the same blob URL repeatedly is cheap but wasteful.
- The redirect endpoint itself is lightweight and fast.

### Optimal polling strategy

1. **GET** the `/api/mural/latest` endpoint, but **do not follow the redirect**. Capture the `Location` header from the 307 response.
2. **Compare** the `Location` URL to the previously seen URL (stored in memory).
3. **If unchanged** → the mural hasn't been updated. Sleep and loop. Zero image bytes downloaded.
4. **If changed** → download the image from the new blob URL. Write it atomically to disk. Update the stored URL.

This approach minimizes bandwidth: you only ever download the image when it has actually changed, and the change-detection request itself is a lightweight redirect (no body).

---

## 3. Package specification

### 3.1 File structure

```
storyfield-mural-display/
├── package.json          # Package metadata
├── package.png           # 64×64 PNG icon
├── node.json             # Config options + network permissions
├── node.lua              # Lua display code with dissolve transition
├── service               # Python polling service
├── hosted.lua            # info-beamer Lua SDK (from package-sdk repo)
├── hosted.py             # info-beamer Python SDK (from package-sdk repo)
├── default.webp          # Transparent/blank placeholder shown before first load
└── README.md             # Usage documentation
```

### 3.2 Configuration options (declared in `node.json`)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `mural_url` | string | `https://storyfield.net/api/mural/latest` | The full API endpoint URL that returns a 307 redirect to the current mural image. Change the hostname for dev/test environments (e.g. `https://storyfield.test/api/mural/latest`). |
| `poll_interval` | integer | `15` | Seconds between polling checks |
| `dissolve_duration` | float | `1.5` | Duration of the crossfade dissolve in seconds |

`node.json` must also declare `"permissions": { "network": "true" }`.

### 3.3 Service behavior (`service` file)

The service is a Python script that:

1. Calls `config.restart_on_update()` so it restarts when config changes in the dashboard.
2. Enters a polling loop:
   a. Reads `mural_url` and `poll_interval` from config.
   b. Issues an HTTP request to `mural_url` that captures the 307 redirect's `Location` header **without following the redirect** and **without downloading a response body**.
   c. Compares the `Location` to the last-known blob URL.
   d. If unchanged, sleeps `poll_interval` seconds and loops.
   e. If changed, downloads the full image from the new blob URL.
   f. Writes the image to `current.jpg` atomically (write to `current.jpg.tmp`, then `os.rename`).
   g. Updates the in-memory last-known URL.
   h. Logs meaningful status messages to stderr (new mural detected, bytes written, errors).
3. Wraps all network operations in try/except with **exponential backoff** on consecutive errors: 5s, 10s, 20s, 40s, ... capped at 120s. Resets to 0 on success.
4. Handles edge cases:
   - Server returns 200 instead of 307 (treat as a direct image response, hash to detect changes)
   - Server returns 5xx (retry with backoff)
   - Network timeout (30s timeout on image download, 10s on redirect check)
   - `Location` header missing (log warning, retry)

### 3.4 Display behavior (`node.lua`)

The Lua code:

1. Calls `gl.setup(NATIVE_WIDTH, NATIVE_HEIGHT)` to use the display's native resolution.
2. Calls `util.init_hosted()` to set up config parsing.
3. Loads a bundled `default.webp` as the initial placeholder image.
4. Listens for config changes via `node.event("config_update", ...)` to pick up `dissolve_duration`.
5. Uses `util.file_watch("current.jpg", ...)` to detect when the service writes a new image.
6. On file change:
   a. Loads the new image via `resource.load_image{ file = "current.jpg" }`.
   b. Disposes the previous "old" image if one exists (to free GPU memory).
   c. Promotes the current image to "old" (it will fade out).
   d. Sets the new image as "current" (it will fade in).
   e. Records the fade start time via `sys.now()`.
7. In `node.render()`:
   a. Clears to black.
   b. If no image loaded yet, draws the default placeholder.
   c. Calculates dissolve progress: `elapsed / dissolve_duration`, clamped to `[0, 1]`.
   d. Draws the old image at alpha `1.0 - progress` (fading out).
   e. Draws the current image at alpha `progress` (fading in).
   f. When dissolve completes, disposes the old image and clears the fade state.
8. Uses **"cover" scaling**: scales the image to fill the screen while maintaining aspect ratio, centered, cropping overflow. This ensures the mural always fills the projection surface regardless of aspect ratio mismatch.

### 3.5 GPU memory management

This is critical. The Pi has limited GPU memory. The code must:

- **Always** call `:dispose()` on images that are no longer needed.
- Never hold more than 3 images in memory simultaneously (default placeholder, outgoing old image, incoming current image).
- Dispose the outgoing image as soon as the dissolve completes.

---

## 4. Development environment & testing requirements

This is a **can't-fail production deployment** for a gallery installation. The code must be bulletproof. The following engineering standards are mandatory.

### 4.1 Development environment

The development environment is a **Python 3 devcontainer** (e.g. based on `mcr.microsoft.com/devcontainers/python:3` or similar). This is required because:

- **Claude Code** (the coding agent CLI) requires Node.js and runs best in a modern container.
- **pytest**, **flake8**, **pylint**, and **unittest.mock** all run natively under Python 3 with no compatibility hacks.
- Modern editor tooling (LSP, autocompletion, etc.) works properly.

All tests run under Python 3 in this devcontainer. The `service` file will be deployed to a device running Python 2.7. The owner will perform **early end-to-end validation on the actual Raspberry Pi 5** to confirm the polyglot code runs correctly under the real Python 2.7 runtime. Do not defer this — get the service running on-device as soon as the basic polling loop works.

### 4.2 Python 2/3 polyglot rules

The `service` file must run under both Python 2.7 (on-device) and Python 3.x (in the devcontainer for testing). This is a small, focused codebase (~100-150 lines) so the polyglot surface area is manageable. Follow these rules strictly:

**File header — every `.py` file must start with:**
```python
#!/usr/bin/python
from __future__ import print_function
```
The shebang `#!/usr/bin/python` is required by info-beamer OS. The `__future__` import makes `print()` work as a function in both versions.

**HTTP imports — use a try/except import pattern:**
```python
try:
    from urllib.request import urlopen, Request, build_opener, HTTPRedirectHandler
    from urllib.error import URLError, HTTPError
except ImportError:
    from urllib2 import urlopen, Request, build_opener, HTTPRedirectHandler, URLError, HTTPError
```
This is the one place where Python 2/3 genuinely diverge for this codebase. Isolate it at the top of the module.

**Rules that keep you in the polyglot safe zone:**
- Use `print()` function syntax everywhere (enabled by the `__future__` import).
- Use `except Exception as e:` syntax (works in both; `except Exception, e:` is Python 2 only).
- Use `str.format()` for string formatting. Do not use f-strings (Python 3.6+ only). `%` formatting is also acceptable — just be consistent.
- Do not use type annotations anywhere in the service code (syntax error in Python 2).
- Do not use `yield from`, `async`/`await`, `nonlocal`, or walrus operator `:=`.
- Use `os.rename()` not `pathlib` (not available in Python 2).
- `json.loads()` returns `unicode` in Python 2 and `str` in Python 3 — this is fine for URL comparison.
- Be aware that `urllib2.urlopen()` response objects differ slightly from `urllib.request.urlopen()` — test the actual response attribute access patterns.

**Things you do NOT need to worry about:**
- `dict.items()` vs `dict.iteritems()` — this codebase won't iterate large dicts.
- `bytes` vs `str` — image data is written in binary mode (`"wb"`) which works the same in both.
- `integer division` — not relevant to this codebase.

### 4.3 Red/Green TDD

All code must be developed using strict red/green test-driven development:

1. **Red**: Write a failing test that describes the desired behavior.
2. **Green**: Write the minimum code to make the test pass.
3. **Refactor**: Clean up while keeping tests green.

No production code should exist without a corresponding test that was written first. Every behavior described in sections 3.3 and 3.4 must have explicit test coverage.

### 4.4 100% test coverage

- **Line coverage**: 100% of all Python source lines must be exercised by tests.
- **Branch coverage**: 100% of all branches (if/else, try/except, loop conditions) must be exercised.
- Use `pytest` with `pytest-cov` and enforce `--cov-fail-under=100 --cov-branch`.
- Tests run under **Python 3** in the devcontainer.
- The Lua code (`node.lua`) does not require automated test coverage (info-beamer's Lua environment is not easily unit-testable outside the device), but should be reviewed carefully and tested on-device.

### 4.5 Code quality and linting

- **`flake8`**: enforce PEP 8 style and complexity. Use `--max-complexity=10` to keep functions simple and testable.
- **`pylint`**: catch unused imports, undefined variables, bad exception handling, and other defects. Configure to accept the polyglot import patterns (the try/except urllib import block).
- **Docstrings**: every public function must have a docstring that describes its arguments, return value, and raised exceptions. Use a consistent format (Google-style or reStructuredText).
- **No bare `except:`** — always catch specific exception types, or at minimum `except Exception:`. Never silently swallow errors.
- **Explicit imports**: no wildcard imports (`from module import *`). Every name used must be explicitly imported.
- **Clean separation of concerns**: redirect checking, image downloading, atomic file writing, and the polling loop should be separate, independently testable functions. No God functions.
- **No global mutable state** outside the main loop.
- **Defensive coding**: every external interaction (network, filesystem) must be wrapped in error handling.
- **Logging to stderr** with timestamps and context — not just bare `print` statements. Consider a simple `log(msg)` helper that prepends a timestamp.

### 4.6 Test strategy

The service code involves network I/O and filesystem operations that must be thoroughly mocked in tests. Use `unittest.mock` (available natively in Python 3's standard library). Here's what to test:

**Redirect detection:**
- 307 response with Location header → returns the URL
- 307 response where Location is in a different case (`location` vs `Location`) → still captured
- 200 response (no redirect) → handled gracefully (fallback to content hashing or re-download)
- Network timeout → raises, handled by caller
- 5xx error → raises, handled by caller
- Missing Location header on 3xx → returns None, caller logs and retries

**Image download:**
- Successful download → writes bytes to `.tmp` file, renames to `current.jpg`
- Atomic write guarantee → if download fails mid-stream, no `current.jpg` is written (`.tmp` may exist but is not renamed)
- Timeout on download → exception raised cleanly

**Polling loop:**
- URL unchanged → no download occurs, sleeps for poll_interval
- URL changed → triggers download and writes file
- First iteration (no previous URL) → always downloads
- Config change → service restarts (via `config.restart_on_update()`)

**Error handling and backoff:**
- Single error → 5s backoff
- Consecutive errors → exponential backoff (5, 10, 20, 40, 80, 120)
- Backoff caps at 120s
- Successful poll after errors → resets backoff to 0
- Exception in any network call → caught, logged to stderr, does not crash the process

**Edge cases:**
- Very large image (test that download completes and writes correctly)
- Empty response body → handled gracefully
- Redirect chain (307 → 307) → only the first Location matters (we don't follow redirects)

### 4.7 Mocking `hosted.py` in tests

The `hosted.py` SDK will not be importable in the test environment (it depends on info-beamer OS internals like `pyinotify` and local UDP sockets). The service code must be structured so that:

- The core logic (redirect checking, image downloading, atomic writes, backoff calculation) lives in **pure functions or a class** that can be imported and tested independently of `hosted.py`.
- The `hosted.py` dependency (`from hosted import config`) is isolated to the main entry point of the `service` file, or behind a thin wrapper that tests can mock.
- Tests mock the config object to provide `mural_url`, `poll_interval`, etc.

A clean pattern: put the core logic in a module like `mural_poller.py`, and have the `service` file be a thin entrypoint that imports from `mural_poller` and wires up the `hosted` config. Tests import and exercise `mural_poller` directly.

### 4.8 Test tooling summary

| Tool | Purpose | Configuration |
|------|---------|---------------|
| `pytest` | Test runner | Python 3, in devcontainer |
| `pytest-cov` | Coverage enforcement | `--cov-fail-under=100 --cov-branch` |
| `flake8` | PEP 8 + complexity | `--max-complexity=10` |
| `pylint` | Static analysis | Accept polyglot import patterns |
| `unittest.mock` | Test doubles | Standard library (Python 3) |

---

## 5. Reference: info-beamer Lua API cheat sheet

These are the Lua APIs relevant to this package:

```lua
-- Screen setup (use native resolution)
gl.setup(NATIVE_WIDTH, NATIVE_HEIGHT)

-- Clear screen
gl.clear(r, g, b, a)  -- floats 0.0-1.0

-- Load image from file (async, returns image object)
local img = resource.load_image{ file = "current.jpg" }
local img = resource.load_image("default.webp")

-- Get image dimensions
local w, h = img:size()

-- Draw image with alpha
img:draw(x1, y1, x2, y2, alpha)  -- alpha is 0.0-1.0

-- Free GPU memory
img:dispose()

-- Current time (monotonic, seconds as float)
sys.now()

-- Watch a file for changes (uses inotify)
util.file_watch("filename", function(content)
    -- called when file changes on disk
    -- content is the raw file bytes
end)

-- Initialize hosted config system
util.init_hosted()

-- Listen for config updates
node.event("config_update", function(config)
    -- config is the parsed CONFIG table
end)

-- The render function (called every frame)
function node.render()
    -- draw your frame here
end
```

---

## 6. Reference: info-beamer Python service patterns

```python
#!/usr/bin/python
from __future__ import print_function
import sys
import time
import traceback

from hosted import config, node

# Auto-restart when config.json changes on device
config.restart_on_update()

# Read config values
url = config.mural_url  # or config['mural_url']
interval = config.poll_interval

# Main loop pattern
while True:
    try:
        # do work
        pass
    except Exception:
        traceback.print_exc()
    time.sleep(interval)
```

**Note**: This runs under Python 2.7 on the device. The polyglot import pattern for HTTP is:
```python
try:
    from urllib.request import urlopen, Request, build_opener, HTTPRedirectHandler
    from urllib.error import URLError, HTTPError
except ImportError:
    from urllib2 import urlopen, Request, build_opener, HTTPRedirectHandler, URLError, HTTPError
```
In the dev/test environment (Python 3), the `try` branch runs. On the device (Python 2.7), the `except ImportError` branch runs. Both provide the same API surface.

The `hosted.py` SDK provides:
- `config` — reads `config.json` (written by info-beamer hosted when dashboard settings change)
- `config.restart_on_update()` — watches config file and exits (OS restarts the service)
- `node['/path'](data)` — send data to Lua via UDP (not needed for this package since we use file-based communication)
- `device` — device control (screen on/off, reboot)
- `api` — access info-beamer platform APIs

---

## 7. Deliverables checklist

- [ ] `package.json` — valid JSON with name, author, desc
- [ ] `package.png` — 64×64 PNG, under 8KB
- [ ] `node.json` — config options for mural_url, poll_interval, dissolve_duration; network permission declared
- [ ] `node.lua` — display code with dissolve crossfade, cover scaling, GPU memory management
- [ ] `service` — Python 2/3 polyglot polling script with redirect detection, atomic writes, exponential backoff
- [ ] `mural_poller.py` — Core logic module (testable independently of `hosted.py`)
- [ ] `default.webp` — transparent/blank placeholder image
- [ ] `README.md` — setup and usage documentation
- [ ] `hosted.lua` and `hosted.py` — copied from info-beamer package-sdk repo
- [ ] Full pytest test suite with 100% line+branch coverage (runs under Python 3 in devcontainer)
- [ ] All Python code passes `flake8 --max-complexity=10` with zero warnings
- [ ] All Python code passes `pylint` with no errors
- [ ] Tests demonstrate red/green TDD methodology (commit history should show test-first development)
- [ ] Early on-device validation performed under real Python 2.7 runtime

---

## 8. Deployment notes

- The target device is a **Raspberry Pi 5** running **info-beamer OS 14+** (required for Pi 5 support and WebP image loading).
- Display output will be via HDMI to a projector. Resolution will likely be 1920×1080 but the code must adapt to whatever `NATIVE_WIDTH`/`NATIVE_HEIGHT` reports.
- The Pi will be on a WiFi network with outbound HTTPS access to `storyfield.net` (production hostname; configurable to `storyfield.test` or other hostnames for dev/test) and Vercel's blob CDN (`*.public.blob.vercel-storage.com`).
- Once deployed, the device will run unattended. There is no local keyboard/mouse access. All configuration changes happen through the info-beamer web dashboard.
- The installation may run continuously for days or weeks. Memory leaks, file descriptor leaks, or unbounded growth of any kind are unacceptable.

### Critical: early on-device validation

The service code is developed and tested under Python 3 in the devcontainer, but runs under Python 2.7 on the actual device. The polyglot subset described in section 4.2 covers the known differences, but **the owner will deploy to the real Pi 5 early in development** (as soon as the basic polling loop and image display are working) to catch any Python 2.7 runtime surprises. Structure the work so that a minimal working vertical slice (poll → download → display) is achievable early, before building out error handling, backoff, and dissolve transitions.
