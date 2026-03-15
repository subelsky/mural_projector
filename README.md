# StoryField Mural Display

An info-beamer package that polls the StoryField API for updated mural images and displays them fullscreen on a Raspberry Pi 5 with dissolve crossfade transitions.

## Requirements

- Raspberry Pi 5 with info-beamer OS 14+
- Network access to storyfield.net and Vercel blob CDN

## Configuration

Configure via the info-beamer dashboard:

| Option | Default | Description |
|--------|---------|-------------|
| Mural API URL | `https://storyfield.net/api/mural/latest` | API endpoint returning a 307 redirect to the current mural image |
| Poll Interval | 15 seconds | How often to check for new images |
| Dissolve Duration | 1.5 seconds | Duration of the crossfade transition |

## Development Setup

```bash
pip install -r requirements-dev.txt
```

Run tests, linting, and local testing:

```bash
python -m pytest tests/ -v --cov=mural_poller --cov-branch --cov-fail-under=100
python -m flake8 mural_poller.py service
python -m pylint mural_poller.py
python test_harness.py --interval 10   # run poller locally without info-beamer
```

## Releasing

Push a version tag to trigger a GitHub Actions workflow that builds the package zip and creates a GitHub Release:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The info-beamer dashboard is pointed at the `latest` release download URL, so clicking **Check for updates** pulls the newest build.

### Building locally

```bash
make build   # downloads SDK, validates files, creates storyfield-mural-display.zip
make clean   # remove build artifacts
```

Upload the zip to info-beamer via **Packages > Add Package > Create from ZIP upload**.

## License

Proprietary — StoryField project.
