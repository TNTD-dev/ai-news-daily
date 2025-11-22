"""
YouTube scraper for collecting video metadata and transcripts.

This module implements scraping of YouTube videos from RSS feeds,
extracting metadata and transcripts using the youtube-transcript-api library.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
from sqlalchemy.orm import Session
from youtube_transcript_api import (
    TranscriptsDisabled,
    NoTranscriptFound,
    YouTubeTranscriptApi,
)

from app.config import AppConfig
from app.database.models import TranscriptStatus, YouTubeVideo
from app.database.repositories import YouTubeVideoRepository
from app.scrapers.base import BaseScraper


class YouTubeScraper(BaseScraper):
    """
    Scraper for YouTube videos from RSS feeds.
    
    Features:
    - Parses YouTube channel RSS feeds
    - Extracts video metadata (title, description, publish date, etc.)
    - Fetches video transcripts using youtube-transcript-api
    - Handles cases where transcripts aren't available
    - Stores videos using YouTubeVideoRepository
    """

    def __init__(self, session: Session, config: AppConfig) -> None:
        """
        Initialize YouTube scraper.
        
        Args:
            session: SQLAlchemy database session
            config: Application configuration
        """
        super().__init__(session, config)
        self.repository = YouTubeVideoRepository(session)

    def scrape(self) -> dict[str, Any]:
        """
        Main scraping method for YouTube videos.
        
        Scrapes all configured YouTube channels, extracts metadata,
        and attempts to fetch transcripts for each video.
        
        Returns:
            Dictionary with scraping results:
            - 'success': Boolean indicating overall success
            - 'count': Number of videos scraped
            - 'transcripts_fetched': Number of transcripts successfully fetched
            - 'errors': List of error messages
        """
        if not self.config.youtube_channels:
            self._log_info("No YouTube channels configured, skipping scraping")
            return {
                "success": True,
                "count": 0,
                "transcripts_fetched": 0,
                "errors": [],
            }

        results = {
            "success": True,
            "count": 0,
            "transcripts_fetched": 0,
            "errors": [],
        }

        for channel_id in self.config.youtube_channels:
            try:
                channel_result = self._scrape_channel(channel_id)
                results["count"] += channel_result["count"]
                results["transcripts_fetched"] += channel_result["transcripts_fetched"]
                results["errors"].extend(channel_result["errors"])
            except Exception as e:
                error_msg = f"Error scraping channel {channel_id}: {str(e)}"
                self._log_error(error_msg, exception=e, channel_id=channel_id)
                results["errors"].append(error_msg)
                results["success"] = False

        self._log_info(
            f"Scraping complete: {results['count']} videos, "
            f"{results['transcripts_fetched']} transcripts fetched"
        )

        return results

    def _scrape_channel(self, channel_identifier: str) -> dict[str, Any]:
        """
        Scrape videos from a single YouTube channel.
        
        Args:
            channel_identifier: Channel ID, URL, or handle
            
        Returns:
            Dictionary with channel scraping results
        """
        self._log_info(f"Scraping YouTube channel: {channel_identifier}")

        # Get RSS URL for the channel
        rss_url = self._get_channel_rss_url(channel_identifier)
        if not rss_url:
            error_msg = f"Could not determine RSS URL for channel: {channel_identifier}"
            self._log_error(error_msg)
            return {"count": 0, "transcripts_fetched": 0, "errors": [error_msg]}

        # Parse RSS feed
        feed = self._parse_rss_feed(rss_url)
        if not feed:
            error_msg = f"Failed to parse RSS feed: {rss_url}"
            self._log_error(error_msg)
            return {"count": 0, "transcripts_fetched": 0, "errors": [error_msg]}

        # Extract channel info
        channel_info = self._extract_channel_info(feed)

        # Process entries
        results = {"count": 0, "transcripts_fetched": 0, "errors": []}

        for entry in feed.entries:
            try:
                video = self._process_video_entry(entry, channel_info)
                if video:
                    results["count"] += 1
                    # Attempt to fetch transcript
                    if self._fetch_transcript(video.video_id):
                        results["transcripts_fetched"] += 1
            except Exception as e:
                error_msg = f"Error processing video entry: {str(e)}"
                self._log_error(error_msg, exception=e, entry_title=entry.get("title"))
                results["errors"].append(error_msg)

        return results

    def _get_channel_rss_url(self, channel_identifier: str) -> str | None:
        """
        Convert channel identifier to RSS feed URL.
        
        Handles various formats:
        - Channel ID: UC_x5XG1OV2P6uZZ5FSM9Ttw
        - Channel URL: https://www.youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw
        - Channel handle: @channelname
        
        Args:
            channel_identifier: Channel ID, URL, or handle
            
        Returns:
            RSS feed URL or None if invalid
        """
        # Extract channel ID from various formats
        channel_id = None

        # Check if it's a URL
        if "youtube.com" in channel_identifier or "youtu.be" in channel_identifier:
            # Extract from URL
            if "/channel/" in channel_identifier:
                channel_id = channel_identifier.split("/channel/")[-1].split("/")[0]
            elif "/@" in channel_identifier:
                # Handle format: https://www.youtube.com/@channelname
                handle = channel_identifier.split("/@")[-1].split("/")[0]
                # For handles, we need to get the channel ID first
                # For now, return None (would need additional API call)
                self._log_error(
                    f"Channel handles (@{handle}) require additional API call, not yet supported"
                )
                return None
            elif "?channel_id=" in channel_identifier:
                channel_id = channel_identifier.split("channel_id=")[-1].split("&")[0]
        elif channel_identifier.startswith("UC"):
            # Looks like a channel ID
            channel_id = channel_identifier
        elif channel_identifier.startswith("@"):
            # Handle format: @channelname
            handle = channel_identifier[1:]
            self._log_error(
                f"Channel handles (@{handle}) require additional API call, not yet supported"
            )
            return None

        if not channel_id:
            return None

        # YouTube RSS feed format
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

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

    def _extract_channel_info(
        self, feed: feedparser.FeedParserDict
    ) -> dict[str, str]:
        """
        Extract channel information from RSS feed.
        
        Args:
            feed: Parsed RSS feed
            
        Returns:
            Dictionary with channel_id and channel_name
        """
        channel_id = ""
        channel_name = "Unknown Channel"

        # Try to extract from feed
        if hasattr(feed, "feed"):
            channel_name = feed.feed.get("title", channel_name)
            # Channel ID might be in various places
            if hasattr(feed.feed, "yt_channelid"):
                channel_id = feed.feed.yt_channelid
            elif hasattr(feed.feed, "link"):
                # Extract from link
                link = feed.feed.link
                if "/channel/" in link:
                    channel_id = link.split("/channel/")[-1].split("/")[0]

        return {"channel_id": channel_id, "channel_name": channel_name}

    def _extract_video_id(self, url: str) -> str | None:
        """
        Extract YouTube video ID from URL.
        
        Handles various YouTube URL formats:
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/embed/VIDEO_ID
        
        Args:
            url: YouTube video URL
            
        Returns:
            Video ID or None if extraction fails
        """
        patterns = [
            r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",  # Standard watch URL
            r"youtu\.be\/([0-9A-Za-z_-]{11})",  # Short URL
            r"embed\/([0-9A-Za-z_-]{11})",  # Embed URL
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    def _process_video_entry(
        self, entry: feedparser.FeedParserDict, channel_info: dict[str, str]
    ) -> YouTubeVideo | None:
        """
        Process a single RSS feed entry and create/update video record.
        
        Args:
            entry: RSS feed entry
            channel_info: Dictionary with channel_id and channel_name
            
        Returns:
            YouTubeVideo instance if successful, None otherwise
        """
        # Extract video ID from link
        video_id = self._extract_video_id(entry.get("link", ""))
        if not video_id:
            self._log_error("Could not extract video ID from entry", entry_link=entry.get("link"))
            return None

        # Extract metadata
        title = entry.get("title", "Untitled")
        description = entry.get("summary", "")
        url = entry.get("link", "")
        published_str = entry.get("published", "")

        # Parse published date
        published_at = self._parse_datetime(published_str)
        if not published_at:
            self._log_error(
                "Could not parse published date, skipping video",
                video_id=video_id,
                published_str=published_str,
            )
            return None

        # Filter by time
        cutoff_time = datetime.now(timezone.utc) - timedelta(
            hours=self.config.hours_lookback
        )
        if published_at < cutoff_time:
            self._log_info(
                f"Video published outside time window, skipping",
                video_id=video_id,
                published_at=published_at,
            )
            return None

        # Extract thumbnail URL
        thumbnail_url = None
        if hasattr(entry, "media_thumbnail"):
            thumbnails = entry.media_thumbnail
            if thumbnails:
                thumbnail_url = thumbnails[0].get("url") if isinstance(thumbnails, list) else thumbnails.get("url")

        # Get or create video
        video, created = self.repository.get_or_create_by_video_id(
            video_id,
            defaults={
                "title": title,
                "description": description,
                "channel_id": channel_info["channel_id"],
                "channel_name": channel_info["channel_name"],
                "published_at": published_at,
                "url": url,
                "thumbnail_url": thumbnail_url,
                "transcript_status": TranscriptStatus.PENDING,
            },
        )

        if created:
            self._log_info(f"Created new video", video_id=video_id, title=title[:50])
        else:
            # Update metadata if video already exists
            video.title = title
            video.description = description
            video.channel_name = channel_info["channel_name"]
            video.published_at = published_at
            video.url = url
            if thumbnail_url:
                video.thumbnail_url = thumbnail_url
            self.repository.update(video)
            self._log_info(f"Updated existing video", video_id=video_id)

        return video

    def _fetch_transcript(self, video_id: str) -> bool:
        """
        Fetch transcript for a video using youtube-transcript-api.
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            True if transcript was successfully fetched, False otherwise
        """
        try:
            # Update status to processing
            video = self.repository.get_by_video_id(video_id)
            if not video:
                return False

            if video.transcript_status == TranscriptStatus.COMPLETED:
                # Already has transcript
                return True

            video.transcript_status = TranscriptStatus.PROCESSING
            self.repository.update(video)

            # Fetch transcript
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            
            # Combine transcript segments into full text
            transcript_text = " ".join(
                segment["text"] for segment in transcript_list
            )

            # Update video with transcript
            self.repository.update_transcript(
                video_id=video_id,
                transcript=transcript_text,
                status=TranscriptStatus.COMPLETED,
            )

            self._log_info(f"Successfully fetched transcript", video_id=video_id)
            return True

        except TranscriptsDisabled:
            error_msg = "Transcripts are disabled for this video"
            self._log_error(error_msg, video_id=video_id)
            self.repository.update_transcript(
                video_id=video_id,
                transcript=None,
                status=TranscriptStatus.FAILED,
                error=error_msg,
            )
            return False

        except NoTranscriptFound:
            error_msg = "No transcript found for this video"
            self._log_error(error_msg, video_id=video_id)
            self.repository.update_transcript(
                video_id=video_id,
                transcript=None,
                status=TranscriptStatus.FAILED,
                error=error_msg,
            )
            return False

        except Exception as e:
            error_msg = f"Error fetching transcript: {str(e)}"
            self._log_error(error_msg, exception=e, video_id=video_id)
            self.repository.update_transcript(
                video_id=video_id,
                transcript=None,
                status=TranscriptStatus.FAILED,
                error=error_msg,
            )
            return False


