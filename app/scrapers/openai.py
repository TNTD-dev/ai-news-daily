"""
OpenAI blog scraper for collecting article content and metadata.

This module implements scraping of OpenAI blog articles from RSS feeds,
extracting full content, converting HTML to markdown using a lightweight
HTML-to-Markdown library, and storing articles using OpenAIArticleRepository.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import feedparser
import requests
from html_to_markdown import convert
from sqlalchemy.orm import Session

from app.config import AppConfig
from app.database.models import OpenAIArticle, ProcessingStatus
from app.database.repositories import OpenAIArticleRepository
from app.scrapers.base import BaseScraper


class OpenAIScraper(BaseScraper):
    """
    Scraper for OpenAI blog articles from RSS feeds.
    
    Features:
    - Parses OpenAI blog RSS feed
    - Extracts article metadata (title, author, publish date, etc.)
    - Fetches full article content from URLs
    - Converts HTML to markdown using docling
    - Stores articles using OpenAIArticleRepository
    """

    # OpenAI blog RSS feed URL
    RSS_FEED_URL = "https://openai.com/blog/rss.xml"

    def __init__(self, session: Session, config: AppConfig) -> None:
        """
        Initialize OpenAI scraper.
        
        Args:
            session: SQLAlchemy database session
            config: Application configuration
        """
        super().__init__(session, config)
        self.repository = OpenAIArticleRepository(session)
        self.session_requests = requests.Session()
        self.session_requests.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def scrape(self) -> dict[str, Any]:
        """
        Main scraping method for OpenAI articles.
        
        Scrapes the OpenAI blog RSS feed, extracts metadata,
        fetches full content, converts to markdown, and stores articles.
        
        Returns:
            Dictionary with scraping results:
            - 'success': Boolean indicating overall success
            - 'count': Number of articles scraped
            - 'markdown_converted': Number of articles successfully converted to markdown
            - 'errors': List of error messages
        """
        self._log_info("Starting OpenAI blog scraping")

        results = {
            "success": True,
            "count": 0,
            "markdown_converted": 0,
            "errors": [],
        }

        # Parse RSS feed
        feed = self._parse_rss_feed(self.RSS_FEED_URL)
        if not feed:
            error_msg = f"Failed to parse RSS feed: {self.RSS_FEED_URL}"
            self._log_error(error_msg)
            return {
                "success": False,
                "count": 0,
                "markdown_converted": 0,
                "errors": [error_msg],
            }

        # Process entries
        for entry in feed.entries:
            try:
                article = self._process_article_entry(entry)
                if article:
                    results["count"] += 1
                    # Convert HTML to markdown
                    if self._convert_to_markdown(article):
                        results["markdown_converted"] += 1
            except Exception as e:
                error_msg = f"Error processing article entry: {str(e)}"
                self._log_error(error_msg, exception=e, entry_title=entry.get("title"))
                results["errors"].append(error_msg)
                results["success"] = False

        self._log_info(
            f"Scraping complete: {results['count']} articles, "
            f"{results['markdown_converted']} markdown conversions"
        )

        return results

    def _parse_rss_feed(self, rss_url: str) -> feedparser.FeedParserDict | None:
        """
        Parse RSS feed using feedparser.
        
        Args:
            rss_url: URL of the RSS feed
            
        Returns:
            Parsed feed object or None if parsing fails
        """
        try:
            feed = feedparser.parse(rss_url)
            if feed.bozo and feed.bozo_exception:
                self._log_error(
                    f"RSS feed parsing error: {feed.bozo_exception}",
                    rss_url=rss_url,
                )
                return None
            return feed
        except Exception as e:
            self._log_error(f"Failed to fetch RSS feed: {rss_url}", exception=e)
            return None

    def _extract_article_id(self, url: str) -> str:
        """
        Extract unique article ID from URL.
        
        Uses the URL path as the article ID, removing query parameters
        and fragments.
        
        Args:
            url: Article URL
            
        Returns:
            Article ID (normalized URL path)
        """
        parsed = urlparse(url)
        # Use path as ID, removing leading/trailing slashes
        article_id = parsed.path.strip("/")
        if not article_id:
            # Fallback to full URL if path is empty
            article_id = url
        return article_id

    def _fetch_article_content(self, url: str) -> str | None:
        """
        Fetch full article content from URL.
        
        Args:
            url: Article URL
            
        Returns:
            HTML content as string, or None if fetch fails
        """
        try:
            response = self.session_requests.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            self._log_error(f"Failed to fetch article content: {url}", exception=e)
            return None

    def _html_to_markdown(self, html_content: str) -> str | None:
        """
        Convert HTML content to markdown using a lightweight HTML-to-Markdown library.

        Args:
            html_content: HTML content as string

        Returns:
            Markdown content as string, or None if conversion fails
        """
        try:
            markdown = convert(html_content)
            if not markdown:
                # Normalize falsy values (empty string) to None so callers can
                # treat conversion failure consistently.
                return None
            return markdown
        except Exception as e:
            self._log_error("Failed to convert HTML to markdown", exception=e)
            return None

    def _process_article_entry(
        self, entry: feedparser.FeedParserDict
    ) -> OpenAIArticle | None:
        """
        Process a single RSS feed entry and create/update article record.
        
        Args:
            entry: RSS feed entry
            
        Returns:
            OpenAIArticle instance if successful, None otherwise
        """
        # Extract article ID from URL
        url = entry.get("link", "")
        if not url:
            self._log_error("Entry missing link URL", entry_title=entry.get("title"))
            return None

        article_id = self._extract_article_id(url)

        # Extract metadata
        title = entry.get("title", "Untitled")
        author = None
        if hasattr(entry, "author"):
            author = entry.author
        elif hasattr(entry, "authors") and entry.authors:
            author = entry.authors[0].get("name", "")

        published_str = entry.get("published", "")
        published_at = self._parse_datetime(published_str)
        if not published_at:
            self._log_error(
                "Could not parse published date, skipping article",
                article_id=article_id,
                published_str=published_str,
            )
            return None

        # Filter by time
        cutoff_time = datetime.now(timezone.utc) - timedelta(
            hours=self.config.hours_lookback
        )
        if published_at < cutoff_time:
            self._log_info(
                f"Article published outside time window, skipping",
                article_id=article_id,
                published_at=published_at,
            )
            return None

        # Get summary/description from RSS feed
        summary = entry.get("summary", "")
        
        # Fetch full article content
        content = self._fetch_article_content(url)
        if not content:
            # Use summary as fallback content
            content = summary or title

        # Get or create article
        article, created = self.repository.get_or_create_by_article_id(
            article_id,
            defaults={
                "title": title,
                "url": url,
                "author": author,
                "published_at": published_at,
                "content": content,
                "processing_status": ProcessingStatus.PENDING,
            },
        )

        if created:
            self._log_info(f"Created new article", article_id=article_id, title=title[:50])
        else:
            # Update metadata if article already exists
            article.title = title
            article.url = url
            article.author = author
            article.published_at = published_at
            article.content = content
            article.processing_status = ProcessingStatus.PENDING
            self.repository.update(article)
            self._log_info(f"Updated existing article", article_id=article_id)

        return article

    def _convert_to_markdown(self, article: OpenAIArticle) -> bool:
        """
        Convert article HTML content to markdown and update article.
        
        Args:
            article: OpenAIArticle instance
            
        Returns:
            True if conversion was successful, False otherwise
        """
        if article.processing_status == ProcessingStatus.COMPLETED:
            # Already converted
            return True

        try:
            # Update status to processing
            article.processing_status = ProcessingStatus.PROCESSING
            self.repository.update(article)

            # Convert HTML to markdown
            markdown = self._html_to_markdown(article.content)
            if markdown:
                # Update article with markdown
                self.repository.update_processing_status(
                    article_id=article.article_id,
                    status=ProcessingStatus.COMPLETED,
                    markdown=markdown,
                )
                self._log_info(
                    f"Successfully converted to markdown", article_id=article.article_id
                )
                return True
            else:
                # Conversion failed
                self.repository.update_processing_status(
                    article_id=article.article_id,
                    status=ProcessingStatus.FAILED,
                )
                self._log_error(
                    f"Failed to convert to markdown", article_id=article.article_id
                )
                return False

        except Exception as e:
            error_msg = f"Error converting to markdown: {str(e)}"
            self._log_error(error_msg, exception=e, article_id=article.article_id)
            self.repository.update_processing_status(
                article_id=article.article_id,
                status=ProcessingStatus.FAILED,
            )
            return False

