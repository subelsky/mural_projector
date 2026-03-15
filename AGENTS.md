# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

StoryField Mural Display — an info-beamer package for Raspberry Pi 5 that polls a mural API for updated images and displays them fullscreen with crossfade transitions. This is a **production gallery installation** driving a live art projector.

## Commands

```bash
# Run tests (100% line+branch coverage enforced)
python -m pytest tests/ -v --cov=mural_poller --cov-branch --cov-fail-under=100

# Lint
python -m flake8 mural_poller.py service
python -m pylint mural_poller.py

# Build deployable zip (downloads SDK, validates files, creates zip)
make build

# Local test run (no info-beamer required)
python test_harness.py --interval 10 --url https://storyfield.net/api/mural/latest
```

## Architecture

Three components communicate via the filesystem:

1. **`mural_poller.py`** — Pure Python module containing `MuralPoller` class. All business logic: redirect-based change detection, image downloading with atomic writes, exponential backoff. Zero info-beamer dependencies — fully testable in isolation.

2. **`service`** — Thin entry point (~30 lines). Imports `hosted.py` SDK for config, constructs `MuralPoller`, runs it. This is the only file that touches the info-beamer SDK.

3. **`node.lua`** — Lua rendering. Watches `current.webp` via inotify (`util.file_watch`), loads new images, renders with crossfade dissolve. Manages GPU memory (max 3 textures).

**Data flow:** `service` polls API → detects URL change → downloads image → atomic write to `current.webp` → `node.lua` detects file change → crossfade transition.

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
- Image output filename is `current.webp` (atomic write via `.tmp` + `os.rename`)
- `default.webp` is the startup placeholder

## Spec Reference
`PROJECT_OVERVIEW.md` is the authoritative specification covering platform constraints, API contract, polling strategy, and all requirements.
