from pathlib import Path

# === Mixed feed metadata (edit these for your fork) ==========================

# Title of the generated mixed feed.
FEED_TITLE = "Jatan blogs"

# Subtitle of the generated mixed feed.
FEED_SUBTITLE = "Single feed for my blogs"

# Author name attributed to the mixed feed.
FEED_AUTHOR = "Jatan Mehta"

# Public URL where the generated Atom file will be served.
FEED_URL = "https://notes.jatan.space/blog-merge/feed.atom"

# Public home page URL associated with the mixed feed.
FEED_HOME_URL = "https://jatan.space/blogs"

# Path to the OPML file listing source feeds.
OPML_FILE = Path("feeds.opml")

# Path of the generated Atom file. The GitHub Action publishes everything under
# `_site/` to the `gh-pages` branch, so keep the output inside that directory.
OUTPUT_FILE = Path("_site/feed.atom")

# === Fetch tunables ==========================================================

# Timeout for network requests in seconds.
REQUEST_TIMEOUT = 60

# Number of concurrent workers to fetch feeds.
MAX_WORKERS = 12

# User-Agent string for feed fetching.
UA = "feed-mixer"

# Maximum content length for fetched feeds in bytes.
MAX_CONTENT_LENGTH = 10 * 1024 * 1024

# Minimum age in hours of recent entries to fetch from each feed.
MIN_FEED_ENTRY_AGE_HOURS = 1

# Maximum age in days of recent entries to fetch from each feed.
MAX_FEED_ENTRY_AGE_DAYS = 370

# Maximum number of recent entries to fetch from each feed.
MAX_FEED_ENTRIES = 25

# Directory for caching fetched data.
CACHE_DIR = Path(".cache")

# Log format for the application.
LOG_FORMAT = "%(asctime)s [%(levelname)-7s] (%(threadName)-10s) %(message)s"
