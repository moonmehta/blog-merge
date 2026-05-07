#!/usr/bin/env python3
"""
feed-mixer entry point.

Reads a list of feeds from an OPML file, fetches them, and writes a single
mixed Atom feed. All site-specific settings live in src/config.py.

Usage:
    python src/mixer.py [--cache-fallback] [--verbose]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path so we can import src modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from src import config
from src.feeds import fetch_all_feeds, generate_mixed_feed, parse_opml_file

logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO, format=config.LOG_FORMAT)

    parser = argparse.ArgumentParser(
        description="Fetch feeds listed in an OPML file and write a mixed Atom feed."
    )
    _ = parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )
    _ = parser.add_argument(
        "--cache-fallback",
        action="store_true",
        help="Fall back to cached feeds on fetch failure and update cache on success",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    opml_path = config.OPML_FILE
    output_path = config.OUTPUT_FILE

    if not opml_path.exists():
        logger.error(f"OPML file does not exist: {opml_path}")
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    config.CACHE_DIR.mkdir(exist_ok=True)

    if args.cache_fallback:
        logger.info("Cache fallback enabled")

    try:
        feeds = parse_opml_file(opml_path)
        entries, failed_feeds = fetch_all_feeds(
            feeds, cache_fallback=args.cache_fallback
        )
        generate_mixed_feed(entries, output_path)

        if failed_feeds:
            logger.warning(f"{len(failed_feeds)} feed(s) failed:")
            for failed in sorted(failed_feeds, key=lambda f: f.feed_info.title.lower()):
                logger.warning(
                    f"  [{failed.reason.value}] {failed.feed_info.title} "
                    f"({failed.feed_info.xml_url})"
                )
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
