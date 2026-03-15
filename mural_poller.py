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
