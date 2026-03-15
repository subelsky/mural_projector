#!/usr/bin/python
"""Core polling logic for StoryField mural display."""
from __future__ import print_function

import os
import hashlib
import time

try:
    from urllib.request import Request, build_opener, HTTPRedirectHandler
    from urllib.error import URLError, HTTPError  # pylint: disable=unused-import
except ImportError:  # pragma: no cover
    from urllib2 import (Request, build_opener, HTTPRedirectHandler,  # noqa: F401
                         URLError, HTTPError)


BACKOFF_SCHEDULE = [5, 10, 20, 40, 80, 120]
REDIRECT_TIMEOUT = 10
DOWNLOAD_TIMEOUT = 30


class _NoRedirectHandler(HTTPRedirectHandler):
    """Prevent urllib from following redirects automatically."""

    # These methods must match the HTTPRedirectHandler signature.
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    # pylint: disable=unused-argument

    def http_error_307(self, req, fp, code, msg, headers):  # pragma: no cover
        """Return the response instead of following the redirect."""
        return fp

    def http_error_302(self, req, fp, code, msg, headers):  # pragma: no cover
        """Return the response instead of following the redirect."""
        return fp

    def http_error_301(self, req, fp, code, msg, headers):  # pragma: no cover
        """Return the response instead of following the redirect."""
        return fp


class MuralPoller:
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

            self.logger.info("New mural detected: %s", location)
            self.download_image(location)
            self.current_location = location
            return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.backoff_level += 1
            self.logger.error(
                "Poll error (backoff level %d): %s",
                self.backoff_level, e
            )
            return False

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
