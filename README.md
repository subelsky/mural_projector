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
