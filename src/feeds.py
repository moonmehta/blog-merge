from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import final
from urllib.parse import quote, urlparse, urlsplit

import feedparser
import requests
from dateutil import parser as date_parser
from feedgen.feed import FeedGenerator

from src import config
from src.utils import SessionManager

logger = logging.getLogger(__name__)


@dataclass
class FeedInfo:
    """Represents feed information."""

    title: str
    xml_url: str
    # Public home page URL. Only meaningful for the generated mixed feed; for
    # source feeds parsed from OPML this is left empty.
    html_url: str = ""


class FailureReason(Enum):
    """Enum for feed failure reasons."""

    ERROR = "error"  # Network/parsing errors
    NO_ENTRIES = "no_entries"  # Feed has no entries
    ALL_FILTERED = "all_filtered"  # Entries exist but all filtered out


@dataclass
class FailedFeedInfo:
    """Represents a feed that failed with reason."""

    feed_info: FeedInfo
    reason: FailureReason


@dataclass
class Body:
    """A piece of entry text with its Atom content type ('text', 'html', or 'xhtml')."""

    value: str
    type: str  # "text" | "html" | "xhtml"

    def __bool__(self) -> bool:
        return bool(self.value)


def _atom_type(mime_or_type: str | None) -> str:
    """Map a feedparser type (often a MIME type) to an Atom shorthand type."""
    if not mime_or_type:
        return "html"
    t = mime_or_type.lower()
    if t in ("text", "html", "xhtml"):
        return t
    if t == "text/plain":
        return "text"
    if t == "application/xhtml+xml":
        return "xhtml"
    # text/html and any other html-ish type default to html
    return "html"


session_manager = SessionManager(
    {
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
    }
)


@final
class FeedEntry:
    """Represents a single feed entry with normalized fields."""

    def __init__(
        self,
        title: str,
        link: str,
        published: datetime,
        feed_title: str,
        feed_url: str,
        tags: list[str],
        summary: Body,
        content: Body,
    ):
        self.title = title
        self.link = link
        self.published = published
        self.feed_title = feed_title
        self.feed_url = feed_url
        self.tags = tags
        self.summary = summary
        self.content = content

    def __repr__(self) -> str:
        return f"""FeedEntry(title={self.title!r},
          link={self.link!r},
          published={self.published!r},
          feed_title={self.feed_title!r},
          summary={self.summary!r},
          content={self.content!r})"""


def parse_opml_file(opml_path: Path) -> list[FeedInfo]:
    """
    Parse OPML file and extract feed URLs with their titles and home page URLs.

    Args:
        opml_path: Path to the OPML file.

    Returns:
        List of FeedInfo objects.

    Raises:
        FileNotFoundError: If OPML file doesn't exist.
        ET.ParseError: If OPML file is malformed.
    """
    logger.info(f"Parsing OPML file: {opml_path}")

    try:
        tree = ET.parse(opml_path)
        root = tree.getroot()

        feeds: list[FeedInfo] = []

        # Look for outline elements with xmlUrl attribute
        for outline in root.iter("outline"):
            xml_url = outline.get("xmlUrl")
            if xml_url:
                title = outline.get("title") or outline.get("text")
                if title is None:
                    logger.error(f"OPML feed {xml_url} does not have title or text")
                    raise ValueError(
                        f"OPML feed {xml_url} has no 'title' or 'text' attribute"
                    )
                feeds.append(FeedInfo(title=title, xml_url=xml_url))
                logger.debug(f"Found feed: {title} -> {xml_url}")

        logger.info(f"Found {len(feeds)} feeds in OPML file")
        return feeds

    except FileNotFoundError:
        logger.error(f"OPML file not found: {opml_path}")
        raise
    except ET.ParseError as e:
        logger.error(f"Failed to parse OPML file: {e}")
        raise


def generate_feed(
    feed_info: FeedInfo,
    author_name: str | None,
    feed_subtitle: str | None,
    entries: list[FeedEntry],
    output_path: Path,
):
    """
    Creates an Atom feed from a list of FeedEntry objects.

    Args:
        feed_info: FeedInfo object containing feed title, URL, and home URL.
        author_name: Author name (optional).
        feed_subtitle: Feed subtitle (optional).
        entries: A list of FeedEntry objects to include in the feed.
        output_path: Path where Atom file should be written.
    """
    fg = FeedGenerator()

    fg.id(feed_info.xml_url)
    fg.title(feed_info.title)
    if author_name is not None:
        fg.author(name=author_name)
    fg.link(href=feed_info.xml_url, rel="self")
    if feed_info.html_url:
        fg.link(href=feed_info.html_url, rel="alternate")
    if feed_subtitle is not None:
        fg.subtitle(feed_subtitle)

    feed_updated = None
    for entry in sorted(
        entries, key=lambda entry: (entry.published, entry.link), reverse=True
    ):
        if entry.link.startswith("http"):
            fe = fg.add_entry(order="append")

            fe.id(entry.link)
            fe.title(entry.title)
            fe.link(href=entry.link, rel="alternate")
            fe.published(entry.published)
            fe.updated(entry.published)
            fe.author(name=entry.feed_title, uri=entry.feed_url)
            if entry.summary:
                fe.summary(summary=entry.summary.value, type=entry.summary.type)
            if entry.content:
                fe.content(content=entry.content.value, type=entry.content.type)

            for tag in entry.tags:
                fe.category(term=tag)

            if feed_updated is None or feed_updated < entry.published:
                feed_updated = entry.published

    fg.updated(feed_updated or datetime.now(timezone.utc))
    fg.atom_file(output_path, pretty=True)


def fetch_feed_content(url: str) -> str | None:
    """
    Fetch feed content from URL with proper error handling and limits.

    Args:
        url: Feed URL to fetch.

    Returns:
        Feed content as string, or None if fetch failed.
    """
    try:
        logger.info(f"Fetching feed: {url}")

        # Validate URL
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            logger.warning(f"Invalid URL format: {url}")
            return None

        response = session_manager.get().get(
            url, timeout=config.REQUEST_TIMEOUT, stream=True
        )
        response.raise_for_status()

        # Check content length
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > config.MAX_CONTENT_LENGTH:
            logger.warning(f"Feed too large ({content_length} bytes): {url}")
            return None

        # Read content with size limit
        content = b""
        for chunk in response.iter_content(chunk_size=8192):
            content += chunk
            if len(content) > config.MAX_CONTENT_LENGTH:
                logger.warning(f"Feed content exceeded size limit: {url}")
                return None

        return content.decode("utf-8", errors="ignore")
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout fetching feed: {url}")
    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTP error fetching feed {url}: {e}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Request error fetching feed {url}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error fetching feed {url}: {e}")


def normalize_link(link: str, feed_url: str) -> str:
    """
    Convert relative URLs to absolute URLs using the feed's domain as base.
    Properly encodes spaces and special characters in the URL.

    Args:
        link: The link to normalize (can be absolute or relative).
        feed_url: The feed URL to extract the domain from.

    Returns:
        Absolute URL with properly percent-encoded characters.
    """
    if not link:
        return link

    if (
        link.startswith("http://") or link.startswith("https://")
    ) and not link.startswith("http://localhost:"):
        return quote(link, safe=":/?#[]@!$&'()*+,;=")

    parsed = urlparse(feed_url)
    link_parts = urlsplit(link)
    absolute_url = link_parts._replace(
        scheme=parsed.scheme,
        netloc=parsed.netloc,
        path=link_parts.path.removeprefix(parsed.netloc),
    ).geturl()
    return quote(absolute_url, safe=":/?#[]@!$&'()*+,;=").strip()


def parse_feed_date(date_string: str) -> datetime | None:
    """
    Parse various date formats commonly found in feeds.

    Args:
        date_string: Date string to parse.

    Returns:
        Parsed datetime object in UTC, or None if parsing failed.
    """
    if not date_string:
        return None

    try:
        # Try parsing with dateutil (handles most formats)
        dt = date_parser.parse(date_string)

        # Ensure timezone info
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        return dt

    except (ValueError, TypeError) as e:
        logger.debug(f"Failed to parse date '{date_string}': {e}")
        return None


def extract_summary(entry) -> Body:
    """Copy entry summary as-is, with no extraction or stripping."""
    if hasattr(entry, "summary") and entry.summary:
        detail = getattr(entry, "summary_detail", None)
        mime = getattr(detail, "type", None) if detail is not None else None
        return Body(value=entry.summary, type=_atom_type(mime))
    return Body(value="", type="text")


def extract_content(entry) -> Body:
    """Copy entry content as-is, with no extraction or stripping."""
    if hasattr(entry, "content") and entry.content:
        content = entry.content[0]
        if hasattr(content, "value") and content.value:
            mime = getattr(content, "type", None)
            return Body(value=content.value, type=_atom_type(mime))
    return Body(value="", type="text")


def parse_feed(
    feed_title: str, feed_url: str, feed_content: str
) -> tuple[list[FeedEntry], bool | None]:
    """
    Parse feed content and extract recent entries.

    Args:
        feed_title: Title of the feed.
        feed_content: Raw feed content.

    Returns:
        List of FeedEntry objects, and if the feed had any entries originally.
    """
    try:
        logger.debug(f"Parsing feed: {feed_title}")

        # Parse with feedparser
        parsed_feed = feedparser.parse(feed_content)

        if parsed_feed.bozo and hasattr(parsed_feed, "bozo_exception"):
            logger.debug(
                f"Feed parser warning for {feed_title}: {parsed_feed.bozo_exception}"
            )

        # Calculate cutoff date
        now = datetime.now(timezone.utc)
        early_cutoff_time = now - timedelta(hours=config.MIN_FEED_ENTRY_AGE_HOURS)
        late_cutoff_time = now - timedelta(days=config.MAX_FEED_ENTRY_AGE_DAYS)

        entries: list[FeedEntry] = []

        has_entries = False
        for entry in parsed_feed.entries:
            has_entries = True
            # Extract and normalize entry data
            title = getattr(entry, "title", None)
            link = getattr(entry, "link", None)
            if title:
                title = title.strip()

            # Validate title
            if not title:
                logger.warning(
                    f"Feed '{feed_title}': Skipping entry with empty title (link: {link})"
                )
                continue

            link = normalize_link(link, feed_url)
            # Validate link
            if not link:
                logger.warning(
                    f"Feed '{feed_title}': Skipping entry '{title}' with empty link"
                )
                continue

            # Parse publication date
            published = None
            for date_field in ["published", "updated", "created"]:
                date_value = getattr(entry, date_field, None)
                if date_value:
                    published = parse_feed_date(date_value)
                    if published:
                        break

            if not published:
                logger.warning(
                    f"Feed '{feed_title}': Entry '{title}' has no valid date"
                )

            # Skip entries without valid dates or too old
            if (
                not published
                or published < late_cutoff_time
                or published > early_cutoff_time
            ):
                continue

            tags = [
                tag.get("label") or tag.get("term")
                for tag in getattr(entry, "tags", [])
            ]

            summary = extract_summary(entry)
            content = extract_content(entry)
            # Many feeds populate both <summary> and <content> with the same
            # text. Keep only the content in that case; if only summary is set,
            # leave it alone.
            if summary and content and summary.value.strip() == content.value.strip():
                summary = Body(value="", type="text")

            entries.append(
                FeedEntry(
                    title=title,
                    link=link,
                    published=published,
                    feed_title=feed_title,
                    feed_url=feed_url,
                    tags=[tag for tag in tags if tag is not None],
                    summary=summary,
                    content=content,
                )
            )

        # Sort by publication date (newest first) and take top N. Tie-break by
        # link so output is stable when entries share a timestamp.
        entries.sort(key=lambda x: (x.published, x.link), reverse=True)
        entries = entries[: config.MAX_FEED_ENTRIES]

        logger.debug(f"Extracted {len(entries)} recent entries from {feed_title}")
        return entries, has_entries

    except Exception as e:
        logger.warning(f"Failed to parse feed {feed_title}: {e}")
        return [], None


def process_single_feed(
    feed_info: FeedInfo, cache_fallback: bool
) -> tuple[list[FeedEntry], FailureReason | None]:
    """
    Process a single feed: fetch and parse it.

    Args:
        feed_info: FeedInfo object containing feed metadata.
        cache_fallback: Whether to fall back to cached content on fetch failure
            and update the cache on success.

    Returns:
        Tuple of (entries list, failure_reason). failure_reason is None if successful.
    """
    feed_title = feed_info.title
    feed_url = feed_info.xml_url

    cache_key = hashlib.sha256(feed_url.encode()).hexdigest()
    cache_file = config.CACHE_DIR / cache_key

    # Fetch feed content
    content = fetch_feed_content(feed_url)
    if content and cache_fallback:
        cache_file.write_text(content, encoding="utf-8")
    if not content:
        if cache_fallback and cache_file.exists():
            logger.info(f"Using cached content as fallback for: {feed_url}")
            content = cache_file.read_text(encoding="utf-8")
        else:
            return [], FailureReason.ERROR

    # Parse feed content
    (entries, has_entries) = parse_feed(feed_title, feed_url, content)

    if len(entries) == 0:
        logger.info(f"Processed {feed_title}: 0 entries")
        if has_entries is None:
            return [], FailureReason.ERROR
        elif has_entries:
            return [], FailureReason.ALL_FILTERED
        else:
            return [], FailureReason.NO_ENTRIES

    logger.info(f"Processed {feed_title}: {len(entries)} entries")
    return entries, None


def fetch_all_feeds(
    feeds: list[FeedInfo], cache_fallback: bool
) -> tuple[list[FeedEntry], list[FailedFeedInfo]]:
    """
    Fetch and parse all feeds concurrently.

    Args:
        feeds: List of FeedInfo objects.
        cache_fallback: Whether to fall back to cached content on fetch failure.

    Returns:
        A tuple containing:
        - Combined list of all feed entries.
        - List of feeds that failed to be fetched.
    """
    if len(feeds) == 0:
        return [], []

    logger.info(f"Processing {len(feeds)} feeds with {config.MAX_WORKERS} workers")

    all_entries: list[FeedEntry] = []
    failed_feeds: list[FailedFeedInfo] = []

    with ThreadPoolExecutor(
        max_workers=config.MAX_WORKERS, thread_name_prefix="Fetcher"
    ) as executor:
        # Submit all feed processing tasks
        future_to_feed = {
            executor.submit(process_single_feed, feed_info, cache_fallback): feed_info
            for feed_info in feeds
        }

        # Collect results as they complete
        for future in as_completed(future_to_feed):
            feed_info = future_to_feed[future]

            try:
                entries, failure_reason = future.result()
                if failure_reason is not None:
                    failed_feeds.append(
                        FailedFeedInfo(feed_info=feed_info, reason=failure_reason)
                    )
                else:
                    all_entries.extend(entries)

            except Exception as e:
                logger.error(f"Failed to process {feed_info.title}: {e}")
                failed_feeds.append(
                    FailedFeedInfo(feed_info=feed_info, reason=FailureReason.ERROR)
                )

    session_manager.close_all()
    return all_entries, failed_feeds


def generate_mixed_feed(entries: list[FeedEntry], output_path: Path):
    """
    Creates the mixed Atom feed from all collected entries.

    Args:
        entries: A list of FeedEntry objects to include in the feed.
        output_path: The path of the Atom file to be written.
    """
    logger.info(f"Generating mixed feed with {len(entries)} entries")

    feed_info = FeedInfo(
        title=config.FEED_TITLE,
        xml_url=config.FEED_URL,
        html_url=config.FEED_HOME_URL,
    )

    generate_feed(
        feed_info=feed_info,
        author_name=config.FEED_AUTHOR,
        feed_subtitle=config.FEED_SUBTITLE,
        entries=entries,
        output_path=output_path,
    )

    logger.info(f"Mixed feed written to: {output_path}")
