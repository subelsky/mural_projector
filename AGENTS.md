# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

StoryField Mural Display — an info-beamer package for Raspberry Pi 5 that polls a mural API for updated images and displays them fullscreen with crossfade transitions. This is a **production gallery installation** driving a live art projector.

## Commands

```bash
# Run tests (100% line+branch coverage enforced)
python -m pytest tests/ -v --cov=mural_poller --cov-branch --cov-fail-under=100

# Python lint
python -m flake8 mural_poller.py service
python -m pylint mural_poller.py

# Lua lint and format check
luacheck node.lua
stylua --check node.lua

# Build deployable zip (downloads SDK, validates files, creates zip)
make build

# Local test run (no info-beamer required)
python test_harness.py --interval 10 --url https://storyfield.net/api/mural/latest
```

## Required Checks

**You MUST run the relevant checks below before considering any task complete.** Do not commit, create PRs, or report success without passing results.

### After changing any `.py` file:
1. `python -m pytest tests/ -v --cov=mural_poller --cov-branch --cov-fail-under=100`
2. `python -m flake8 mural_poller.py service`
3. `python -m pylint mural_poller.py`

### After changing any `.lua` file:
1. `luacheck node.lua` — must report 0 warnings / 0 errors
2. `stylua --check node.lua` — must exit 0 (no formatting diff)

If `stylua --check` fails, run `stylua node.lua` to auto-fix, then verify with `luacheck` again.

### Configuration
- `.luacheckrc` — declares info-beamer globals and project lint settings
- `.stylua.toml` — formatting rules (4-space indent, 99 col width)

## Architecture

Three components communicate via the filesystem:

1. **`mural_poller.py`** — Pure Python module containing `MuralPoller` class. All business logic: redirect-based change detection, image downloading with atomic writes, exponential backoff. Zero info-beamer dependencies — fully testable in isolation.

2. **`service`** — Thin entry point (~30 lines). Imports `hosted.py` SDK for config, constructs `MuralPoller`, runs it. This is the only file that touches the info-beamer SDK.

3. **`node.lua`** — Lua rendering. Watches `current.png` via inotify (`util.file_watch`), loads new images, renders with crossfade dissolve. Manages GPU memory (max 3 textures).

**Data flow:** `service` polls API → detects URL change → downloads image → atomic write to `current.png` → `node.lua` detects file change → crossfade transition.

## Critical Constraints

### Python 2/3 Polyglot
The device runs **Python 2.7**; dev/test runs Python 3. All Python code must work under both:
- No type annotations, f-strings, walrus operator, `async`/`await`, `pathlib`
- Use `str.format()` for string formatting
- Use `except Exception as e:` syntax
- Use try/except import pattern for urllib2 vs urllib.request (already at top of `mural_poller.py`)
- Every `.py` file starts with `#!/usr/bin/python` and `from __future__ import print_function`

### Testing
- **Strict red/green TDD** — write failing test first, then implementation
- **100% line + branch coverage** enforced via pytest-cov (`--cov-fail-under=100`)
- Mock network and filesystem; core logic is decoupled from `hosted.py`
- Max complexity 10 (flake8), max line length 99

### File Conventions
- `hosted.lua` and `hosted.py` are **vendored SDK files** — do not edit
- Image output filename is `current.png` (atomic write via `.tmp` + `os.rename`)
- `default.png` is the startup placeholder

## Spec Reference
`PROJECT_OVERVIEW.md` is the authoritative specification covering platform constraints, API contract, polling strategy, and all requirements.

## info-beamer Documentation
The info-beamer platform docs are at `https://info-beamer.com/doc/`. Key pages:
- **Package reference** (`/doc/package-reference`) — `package.json` and `node.json` schema, service permissions, node.lua API
- **Device configuration** (`/doc/device-configuration`) — networking, WiFi, device-level setup
- **Lua API** (`/doc/info-beamer`) — gl, resource, util, node, sys globals
- **Debugging** (`/doc/debugging`) — `logread -f` for live logs, `/space/root/` for deployed files

Use `WebFetch` to read these when working on platform integration, service configuration, or `node.json`/`package.json` changes.

### info-beamer Lua API Gotchas
- **Config watching:** Use `util.json_watch("config.json", handler)` — NOT `node.event("config_update", ...)`. Valid node events are: child_add, child_remove, content_update, content_remove, data, osc, input, connect, disconnect.
- **`util.file_watch` calls handler immediately** at registration. If the file doesn't exist, handler may receive nil — always guard with `if not raw or #raw == 0 then return end`.
- **Package files are read-only** — services cannot overwrite files included in the zip. `current.png` must NOT be in the zip since the service writes it at runtime.
- **No output before `gl.setup()`** — any `print()` call before `gl.setup()` causes a silent black screen.
- **info-beamer only supports JPEG and PNG** — no WebP, GIF, etc.
