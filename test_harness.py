#!/usr/bin/env python3
"""Local test harness — runs the poller against the real StoryField API.

Usage:
    python test_harness.py [--url URL] [--interval SECONDS]

This bypasses hosted.py and runs MuralPoller directly. Watch for
current.webp appearing and updating in the working directory.
"""
import sys
import os
import logging
import argparse
import signal
import threading

# Ensure we can import from the project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mural_poller import MuralPoller


def main():
    parser = argparse.ArgumentParser(
        description="Test the mural poller against a live API"
    )
    parser.add_argument(
        "--url",
        default="https://storyfield.net/api/mural/latest",
        help="Mural API URL (default: storyfield.net)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Poll interval in seconds (default: 10)",
    )
    parser.add_argument(
        "--image-path",
        default="current.webp",
        help="Path to write the downloaded image (default: current.webp)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("test_harness")

    poller = MuralPoller(
        mural_url=args.url,
        poll_interval=args.interval,
        image_path=args.image_path,
        logger=logger,
    )

    # Graceful shutdown on Ctrl+C
    shutdown = threading.Event()

    def handle_signal(signum, frame):
        logger.info("Caught signal %d, shutting down...", signum)
        shutdown.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logger.info("Starting test harness")
    logger.info("  URL: %s", args.url)
    logger.info("  Interval: %ds", args.interval)
    logger.info("  Image: %s", os.path.abspath(args.image_path))
    logger.info("Press Ctrl+C to stop")
    logger.info("")

    poller.run(shutdown_event=shutdown)
    logger.info("Stopped.")


if __name__ == "__main__":
    main()
