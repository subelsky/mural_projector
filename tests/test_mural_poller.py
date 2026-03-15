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
