"""Tests for mural_poller module — strict red/green TDD."""
from unittest.mock import patch, MagicMock
import logging
import pytest

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
