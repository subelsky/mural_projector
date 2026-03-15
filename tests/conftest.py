"""Shared test fixtures for mural_poller tests."""
import logging
import pytest


@pytest.fixture
def logger():
    """Provide a logger that captures output for assertions."""
    test_logger = logging.getLogger("test_mural_poller")
    test_logger.setLevel(logging.DEBUG)
    return test_logger
