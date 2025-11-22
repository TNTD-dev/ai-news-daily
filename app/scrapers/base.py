"""
Base scraper class providing common functionality for all scrapers.

This module defines an abstract base class that all specific scrapers inherit from,
providing common methods for time filtering, date parsing, logging, and error handling.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, List

from app.config import AppConfig, ScrapingConfig
from sqlalchemy.orm import Session


class BaseScraper(ABC):
    """
    Abstract base class for all scrapers.
    
    Provides common functionality including:
    - Configuration access
    - Time-based filtering
    - Date parsing
    - Logging helpers
    - Error handling patterns
    
    Subclasses must implement the `scrape()` method.
    """

    def __init__(self, session: Session, config: AppConfig) -> None:
        """
        Initialize base scraper with database session and configuration.
        
        Args:
            session: SQLAlchemy database session
            config: Application configuration containing scraping settings
        """
        self.session = session
        self.config: ScrapingConfig = config.scraping
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def scrape(self) -> dict[str, Any]:
        """
        Main scraping method to be implemented by subclasses.
        
        Returns:
            Dictionary with scraping results including:
            - 'success': Boolean indicating if scraping succeeded
            - 'count': Number of items scraped
            - 'errors': List of error messages (if any)
        """
        pass

    def _filter_by_time(
        self, items: List[Any], published_attr: str = "published_at"
    ) -> List[Any]:
        """
        Filter items by publication time based on hours_lookback config.
        
        Args:
            items: List of items to filter (must have published_attr attribute)
            published_attr: Name of the attribute containing publication datetime
            
        Returns:
            Filtered list of items within the time window
        """
        if not items:
            return []

        cutoff_time = datetime.now(timezone.utc) - timedelta(
            hours=self.config.hours_lookback
        )

        filtered = []
        for item in items:
            published = getattr(item, published_attr, None)
            if published:
                # Handle both timezone-aware and naive datetimes
                if published.tzinfo is None:
                    # Assume UTC if naive
                    published = published.replace(tzinfo=timezone.utc)
                elif published.tzinfo != timezone.utc:
                    # Convert to UTC
                    published = published.astimezone(timezone.utc)

                if published >= cutoff_time:
                    filtered.append(item)

        return filtered

    def _parse_datetime(self, date_string: str) -> datetime | None:
        """
        Parse various date string formats to datetime.
        
        Handles common RSS feed date formats including:
        - RFC 822 (e.g., "Mon, 01 Jan 2024 12:00:00 +0000")
        - ISO 8601 (e.g., "2024-01-01T12:00:00Z")
        - Other common formats
        
        Args:
            date_string: Date string to parse
            
        Returns:
            Datetime object with UTC timezone, or None if parsing fails
        """
        if not date_string:
            return None

        # Try feedparser's date parsing (handles most RSS formats)
        try:
            import feedparser

            parsed = feedparser._parse_date(date_string)
            if parsed:
                # feedparser returns time.struct_time, convert to datetime
                return datetime(*parsed[:6], tzinfo=timezone.utc)
        except (ValueError, AttributeError, TypeError):
            pass

        # Try standard datetime parsing
        formats = [
            "%Y-%m-%dT%H:%M:%SZ",  # ISO 8601 UTC
            "%Y-%m-%dT%H:%M:%S%z",  # ISO 8601 with timezone
            "%Y-%m-%d %H:%M:%S",  # Simple format
            "%a, %d %b %Y %H:%M:%S %z",  # RFC 822
            "%a, %d %b %Y %H:%M:%S %Z",  # RFC 822 with timezone name
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_string, fmt)
                # Ensure timezone-aware
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue

        self._log_error(f"Failed to parse date string: {date_string}")
        return None

    def _log_info(self, message: str, **kwargs: Any) -> None:
        """
        Log an informational message with optional context.
        
        Args:
            message: Log message
            **kwargs: Additional context to include in log
        """
        if kwargs:
            context = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            self.logger.info(f"{message} | {context}")
        else:
            self.logger.info(message)

    def _log_error(
        self, message: str, exception: Exception | None = None, **kwargs: Any
    ) -> None:
        """
        Log an error message with optional exception and context.
        
        Args:
            message: Error message
            exception: Optional exception object
            **kwargs: Additional context to include in log
        """
        if kwargs:
            context = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            full_message = f"{message} | {context}"
        else:
            full_message = message

        if exception:
            self.logger.error(f"{full_message} | Exception: {exception}", exc_info=True)
        else:
            self.logger.error(full_message)

    def _limit_items(self, items: List[Any], limit: int | None = None) -> List[Any]:
        """
        Limit the number of items returned.
        
        Args:
            items: List of items to limit
            limit: Maximum number of items (uses config.max_articles if None)
            
        Returns:
            Limited list of items
        """
        if limit is None:
            limit = self.config.max_articles

        if limit and limit > 0:
            return items[:limit]
        return items

