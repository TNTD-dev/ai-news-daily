"""
Repository pattern implementation for database operations.

This module provides repository classes that abstract database operations,
offering clean interfaces for data access with common CRUD operations and
domain-specific query methods.

The repository pattern provides:
- Separation of concerns: Business logic doesn't need to know SQL
- Testability: Easy to mock repositories for testing
- Reusability: Common operations in base class
- Type safety: Full type hints for IDE support
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, Generic, List, Optional, TypeVar

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.database.models import (
    AnthropicArticle,
    Digest,
    OpenAIArticle,
    ProcessingStatus,
    TranscriptStatus,
    YouTubeVideo,
)

# Type variable for generic repository
T = TypeVar("T")


class BaseRepository(Generic[T]):
    """
    Base repository class providing common CRUD operations.
    
    This is a generic repository that works with any SQLAlchemy model.
    All specific repositories inherit from this class to get common operations.
    
    Type Parameters:
        T: The SQLAlchemy model type this repository works with
    
    Attributes:
        session: SQLAlchemy session for database operations
        model: The model class this repository manages
    """

    def __init__(self, session: Session, model: type[T]) -> None:
        """
        Initialize repository with database session and model.
        
        Args:
            session: SQLAlchemy session for database operations
            model: The model class this repository manages
        """
        self.session = session
        self.model = model

    def create(self, instance: T) -> T:
        """
        Create a new record in the database.
        
        Args:
            instance: Model instance to create
            
        Returns:
            The created instance (with ID populated)
            
        Note:
            Does not commit - caller must commit the session
        """
        self.session.add(instance)
        self.session.flush()  # Get ID without committing
        return instance

    def get_by_id(self, id: int) -> Optional[T]:
        """
        Get a record by its primary key ID.
        
        Args:
            id: Primary key ID
            
        Returns:
            Model instance if found, None otherwise
        """
        return self.session.get(self.model, id)

    def get_all(self, limit: Optional[int] = None, offset: int = 0) -> List[T]:
        """
        Get all records, optionally with pagination.
        
        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip
            
        Returns:
            List of model instances
        """
        query = self.session.query(self.model)
        if limit:
            query = query.limit(limit).offset(offset)
        return query.all()

    def update(self, instance: T) -> T:
        """
        Update an existing record.
        
        Args:
            instance: Model instance with updated values
            
        Returns:
            The updated instance
            
        Note:
            Does not commit - caller must commit the session
        """
        self.session.merge(instance)
        self.session.flush()
        return instance

    def delete(self, id: int) -> bool:
        """
        Delete a record by its primary key ID.
        
        Args:
            id: Primary key ID
            
        Returns:
            True if deleted, False if not found
            
        Note:
            Does not commit - caller must commit the session
        """
        instance = self.get_by_id(id)
        if instance:
            self.session.delete(instance)
            self.session.flush()
            return True
        return False

    def delete_instance(self, instance: T) -> None:
        """
        Delete a record instance.
        
        Args:
            instance: Model instance to delete
            
        Note:
            Does not commit - caller must commit the session
        """
        self.session.delete(instance)
        self.session.flush()

    def exists(self, id: int) -> bool:
        """
        Check if a record exists by its primary key ID.
        
        Args:
            id: Primary key ID
            
        Returns:
            True if exists, False otherwise
        """
        return self.get_by_id(id) is not None

    def count(self) -> int:
        """
        Count total number of records.
        
        Returns:
            Total count of records
        """
        return self.session.query(self.model).count()

    def query(self) -> Any:
        """
        Get base query object for custom queries.
        
        Returns:
            SQLAlchemy query object for the model
            
        Example:
            ```python
            query = repo.query().filter(Model.field == value)
            results = query.all()
            ```
        """
        return self.session.query(self.model)


class YouTubeVideoRepository(BaseRepository[YouTubeVideo]):
    """
    Repository for YouTube video operations.
    
    Provides methods for managing YouTube videos including transcript
    extraction status tracking and video metadata operations.
    """

    def __init__(self, session: Session) -> None:
        """Initialize YouTube video repository."""
        super().__init__(session, YouTubeVideo)

    def get_by_video_id(self, video_id: str) -> Optional[YouTubeVideo]:
        """
        Get a video by its YouTube video ID.
        
        Args:
            video_id: YouTube video ID (e.g., from URL parameter)
            
        Returns:
            YouTubeVideo instance if found, None otherwise
        """
        return self.query().filter(YouTubeVideo.video_id == video_id).first()

    def get_or_create_by_video_id(
        self, video_id: str, defaults: Optional[Dict[str, Any]] = None
    ) -> tuple[YouTubeVideo, bool]:
        """
        Get existing video or create a new one if it doesn't exist.
        
        Args:
            video_id: YouTube video ID
            defaults: Dictionary of default values for new video creation
            
        Returns:
            Tuple of (video_instance, created) where created is True if new
            
        Example:
            ```python
            video, created = repo.get_or_create_by_video_id(
                "abc123",
                defaults={"title": "New Video", "url": "https://..."}
            )
            ```
        """
        video = self.get_by_video_id(video_id)
        if video:
            return video, False

        defaults = defaults or {}
        defaults["video_id"] = video_id
        video = YouTubeVideo(**defaults)
        return self.create(video), True

    def get_unprocessed_videos(self) -> List[YouTubeVideo]:
        """
        Get videos that need transcript processing (PENDING or FAILED status).
        
        Returns:
            List of videos with transcript_status in [PENDING, FAILED]
        """
        return (
            self.query()
            .filter(
                or_(
                    YouTubeVideo.transcript_status == TranscriptStatus.PENDING,
                    YouTubeVideo.transcript_status == TranscriptStatus.FAILED,
                )
            )
            .all()
        )

    def get_pending_transcripts(self) -> List[YouTubeVideo]:
        """
        Get videos with PENDING transcript status.
        
        Returns:
            List of videos with transcript_status = PENDING
        """
        return (
            self.query()
            .filter(YouTubeVideo.transcript_status == TranscriptStatus.PENDING)
            .all()
        )

    def get_failed_transcripts(self) -> List[YouTubeVideo]:
        """
        Get videos with FAILED transcript status.
        
        Returns:
            List of videos with transcript_status = FAILED
        """
        return (
            self.query()
            .filter(YouTubeVideo.transcript_status == TranscriptStatus.FAILED)
            .all()
        )

    def get_recent_videos(
        self, hours: int = 24, limit: Optional[int] = None
    ) -> List[YouTubeVideo]:
        """
        Get videos published within the last N hours.
        
        Args:
            hours: Number of hours to look back (default: 24)
            limit: Maximum number of videos to return
            
        Returns:
            List of videos sorted by published_at (newest first)
        """
        cutoff_time = datetime.now().replace(tzinfo=None) - timedelta(hours=hours)
        query = (
            self.query()
            .filter(YouTubeVideo.published_at >= cutoff_time)
            .order_by(YouTubeVideo.published_at.desc())
        )
        if limit:
            query = query.limit(limit)
        return query.all()

    def get_by_channel(
        self, channel_id: str, limit: Optional[int] = None
    ) -> List[YouTubeVideo]:
        """
        Get videos by channel ID.
        
        Args:
            channel_id: YouTube channel ID
            limit: Maximum number of videos to return
            
        Returns:
            List of videos from the channel, sorted by published_at (newest first)
        """
        query = (
            self.query()
            .filter(YouTubeVideo.channel_id == channel_id)
            .order_by(YouTubeVideo.published_at.desc())
        )
        if limit:
            query = query.limit(limit)
        return query.all()

    def update_transcript(
        self,
        video_id: str,
        transcript: Optional[str],
        status: TranscriptStatus,
        error: Optional[str] = None,
    ) -> Optional[YouTubeVideo]:
        """
        Update video transcript and status.
        
        Args:
            video_id: YouTube video ID
            transcript: Transcript text (None if extraction failed)
            status: New transcript status
            error: Error message if status is FAILED
            
        Returns:
            Updated video instance if found, None otherwise
            
        Note:
            Does not commit - caller must commit the session
        """
        video = self.get_by_video_id(video_id)
        if not video:
            return None

        video.transcript = transcript
        video.transcript_status = status
        if error:
            video.transcript_error = error
        elif status != TranscriptStatus.FAILED:
            video.transcript_error = None

        return self.update(video)

    def bulk_create(self, videos: List[YouTubeVideo]) -> int:
        """
        Create multiple videos efficiently using bulk insert.
        
        Args:
            videos: List of YouTubeVideo instances to create
            
        Returns:
            Number of videos created
            
        Note:
            Uses bulk_insert_mappings for efficiency.
            Does not populate relationships or return instances with IDs.
            For smaller batches or when you need IDs, use individual create() calls.
        """
        if not videos:
            return 0

        mappings = [
            {
                "video_id": v.video_id,
                "title": v.title,
                "description": v.description,
                "channel_id": v.channel_id,
                "channel_name": v.channel_name,
                "published_at": v.published_at,
                "url": v.url,
                "thumbnail_url": v.thumbnail_url,
                "duration": v.duration,
                "transcript_status": v.transcript_status.value
                if isinstance(v.transcript_status, TranscriptStatus)
                else v.transcript_status,
            }
            for v in videos
        ]

        self.session.bulk_insert_mappings(YouTubeVideo, mappings)
        self.session.flush()
        return len(videos)


class OpenAIArticleRepository(BaseRepository[OpenAIArticle]):
    """
    Repository for OpenAI article operations.
    
    Provides methods for managing OpenAI blog articles including
    processing status tracking and content operations.
    """

    def __init__(self, session: Session) -> None:
        """Initialize OpenAI article repository."""
        super().__init__(session, OpenAIArticle)

    def get_by_article_id(self, article_id: str) -> Optional[OpenAIArticle]:
        """
        Get an article by its RSS article ID.
        
        Args:
            article_id: Unique identifier from RSS feed
            
        Returns:
            OpenAIArticle instance if found, None otherwise
        """
        return self.query().filter(OpenAIArticle.article_id == article_id).first()

    def get_by_url(self, url: str) -> Optional[OpenAIArticle]:
        """
        Get an article by its URL.
        
        Args:
            url: Article URL
            
        Returns:
            OpenAIArticle instance if found, None otherwise
        """
        return self.query().filter(OpenAIArticle.url == url).first()

    def get_or_create_by_article_id(
        self, article_id: str, defaults: Optional[Dict[str, Any]] = None
    ) -> tuple[OpenAIArticle, bool]:
        """
        Get existing article or create a new one if it doesn't exist.
        
        Args:
            article_id: RSS article ID
            defaults: Dictionary of default values for new article creation
            
        Returns:
            Tuple of (article_instance, created) where created is True if new
        """
        article = self.get_by_article_id(article_id)
        if article:
            return article, False

        defaults = defaults or {}
        defaults["article_id"] = article_id
        article = OpenAIArticle(**defaults)
        return self.create(article), True

    def get_unprocessed_articles(self) -> List[OpenAIArticle]:
        """
        Get articles that need processing (PENDING or FAILED status).
        
        Returns:
            List of articles with processing_status in [PENDING, FAILED]
        """
        return (
            self.query()
            .filter(
                or_(
                    OpenAIArticle.processing_status == ProcessingStatus.PENDING,
                    OpenAIArticle.processing_status == ProcessingStatus.FAILED,
                )
            )
            .all()
        )

    def get_pending_processing(self) -> List[OpenAIArticle]:
        """
        Get articles with PENDING processing status.
        
        Returns:
            List of articles with processing_status = PENDING
        """
        return (
            self.query()
            .filter(OpenAIArticle.processing_status == ProcessingStatus.PENDING)
            .all()
        )

    def get_failed_processing(self) -> List[OpenAIArticle]:
        """
        Get articles with FAILED processing status.
        
        Returns:
            List of articles with processing_status = FAILED
        """
        return (
            self.query()
            .filter(OpenAIArticle.processing_status == ProcessingStatus.FAILED)
            .all()
        )

    def get_recent_articles(
        self, hours: int = 24, limit: Optional[int] = None
    ) -> List[OpenAIArticle]:
        """
        Get articles published within the last N hours.
        
        Args:
            hours: Number of hours to look back (default: 24)
            limit: Maximum number of articles to return
            
        Returns:
            List of articles sorted by published_at (newest first)
        """
        cutoff_time = datetime.now().replace(tzinfo=None) - timedelta(hours=hours)
        query = (
            self.query()
            .filter(OpenAIArticle.published_at >= cutoff_time)
            .order_by(OpenAIArticle.published_at.desc())
        )
        if limit:
            query = query.limit(limit)
        return query.all()

    def update_processing_status(
        self,
        article_id: str,
        status: ProcessingStatus,
        markdown: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> Optional[OpenAIArticle]:
        """
        Update article processing status and optionally content.
        
        Args:
            article_id: RSS article ID
            status: New processing status
            markdown: Optional markdown content to update
            summary: Optional summary to update
            
        Returns:
            Updated article instance if found, None otherwise
            
        Note:
            Does not commit - caller must commit the session
        """
        article = self.get_by_article_id(article_id)
        if not article:
            return None

        article.processing_status = status
        if markdown is not None:
            article.content_markdown = markdown
        if summary is not None:
            article.summary = summary

        return self.update(article)

    def bulk_create(self, articles: List[OpenAIArticle]) -> int:
        """
        Create multiple articles efficiently using bulk insert.
        
        Args:
            articles: List of OpenAIArticle instances to create
            
        Returns:
            Number of articles created
            
        Note:
            Uses bulk_insert_mappings for efficiency.
            Does not populate relationships or return instances with IDs.
        """
        if not articles:
            return 0

        mappings = [
            {
                "article_id": a.article_id,
                "title": a.title,
                "url": a.url,
                "author": a.author,
                "published_at": a.published_at,
                "content": a.content,
                "processing_status": a.processing_status.value
                if isinstance(a.processing_status, ProcessingStatus)
                else a.processing_status,
            }
            for a in articles
        ]

        self.session.bulk_insert_mappings(OpenAIArticle, mappings)
        self.session.flush()
        return len(articles)


class AnthropicArticleRepository(BaseRepository[AnthropicArticle]):
    """
    Repository for Anthropic article operations.
    
    Provides methods for managing Anthropic blog articles including
    processing status tracking and content operations.
    """

    def __init__(self, session: Session) -> None:
        """Initialize Anthropic article repository."""
        super().__init__(session, AnthropicArticle)

    def get_by_article_id(self, article_id: str) -> Optional[AnthropicArticle]:
        """
        Get an article by its RSS article ID.
        
        Args:
            article_id: Unique identifier from RSS feed
            
        Returns:
            AnthropicArticle instance if found, None otherwise
        """
        return self.query().filter(AnthropicArticle.article_id == article_id).first()

    def get_by_url(self, url: str) -> Optional[AnthropicArticle]:
        """
        Get an article by its URL.
        
        Args:
            url: Article URL
            
        Returns:
            AnthropicArticle instance if found, None otherwise
        """
        return self.query().filter(AnthropicArticle.url == url).first()

    def get_or_create_by_article_id(
        self, article_id: str, defaults: Optional[Dict[str, Any]] = None
    ) -> tuple[AnthropicArticle, bool]:
        """
        Get existing article or create a new one if it doesn't exist.
        
        Args:
            article_id: RSS article ID
            defaults: Dictionary of default values for new article creation
            
        Returns:
            Tuple of (article_instance, created) where created is True if new
        """
        article = self.get_by_article_id(article_id)
        if article:
            return article, False

        defaults = defaults or {}
        defaults["article_id"] = article_id
        article = AnthropicArticle(**defaults)
        return self.create(article), True

    def get_unprocessed_articles(self) -> List[AnthropicArticle]:
        """
        Get articles that need processing (PENDING or FAILED status).
        
        Returns:
            List of articles with processing_status in [PENDING, FAILED]
        """
        return (
            self.query()
            .filter(
                or_(
                    AnthropicArticle.processing_status == ProcessingStatus.PENDING,
                    AnthropicArticle.processing_status == ProcessingStatus.FAILED,
                )
            )
            .all()
        )

    def get_pending_processing(self) -> List[AnthropicArticle]:
        """
        Get articles with PENDING processing status.
        
        Returns:
            List of articles with processing_status = PENDING
        """
        return (
            self.query()
            .filter(
                AnthropicArticle.processing_status == ProcessingStatus.PENDING
            )
            .all()
        )

    def get_failed_processing(self) -> List[AnthropicArticle]:
        """
        Get articles with FAILED processing status.
        
        Returns:
            List of articles with processing_status = FAILED
        """
        return (
            self.query()
            .filter(AnthropicArticle.processing_status == ProcessingStatus.FAILED)
            .all()
        )

    def get_recent_articles(
        self, hours: int = 24, limit: Optional[int] = None
    ) -> List[AnthropicArticle]:
        """
        Get articles published within the last N hours.
        
        Args:
            hours: Number of hours to look back (default: 24)
            limit: Maximum number of articles to return
            
        Returns:
            List of articles sorted by published_at (newest first)
        """
        cutoff_time = datetime.now().replace(tzinfo=None) - timedelta(hours=hours)
        query = (
            self.query()
            .filter(AnthropicArticle.published_at >= cutoff_time)
            .order_by(AnthropicArticle.published_at.desc())
        )
        if limit:
            query = query.limit(limit)
        return query.all()

    def update_processing_status(
        self,
        article_id: str,
        status: ProcessingStatus,
        markdown: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> Optional[AnthropicArticle]:
        """
        Update article processing status and optionally content.
        
        Args:
            article_id: RSS article ID
            status: New processing status
            markdown: Optional markdown content to update
            summary: Optional summary to update
            
        Returns:
            Updated article instance if found, None otherwise
            
        Note:
            Does not commit - caller must commit the session
        """
        article = self.get_by_article_id(article_id)
        if not article:
            return None

        article.processing_status = status
        if markdown is not None:
            article.content_markdown = markdown
        if summary is not None:
            article.summary = summary

        return self.update(article)

    def bulk_create(self, articles: List[AnthropicArticle]) -> int:
        """
        Create multiple articles efficiently using bulk insert.
        
        Args:
            articles: List of AnthropicArticle instances to create
            
        Returns:
            Number of articles created
            
        Note:
            Uses bulk_insert_mappings for efficiency.
            Does not populate relationships or return instances with IDs.
        """
        if not articles:
            return 0

        mappings = [
            {
                "article_id": a.article_id,
                "title": a.title,
                "url": a.url,
                "author": a.author,
                "published_at": a.published_at,
                "content": a.content,
                "processing_status": a.processing_status.value
                if isinstance(a.processing_status, ProcessingStatus)
                else a.processing_status,
            }
            for a in articles
        ]

        self.session.bulk_insert_mappings(AnthropicArticle, mappings)
        self.session.flush()
        return len(articles)


class DigestRepository(BaseRepository[Digest]):
    """
    Repository for digest operations.
    
    Provides methods for managing daily digests including content
    aggregation and email delivery tracking.
    """

    def __init__(self, session: Session) -> None:
        """Initialize digest repository."""
        super().__init__(session, Digest)

    def get_by_date(self, digest_date: date) -> Optional[Digest]:
        """
        Get digest for a specific date.
        
        Args:
            digest_date: Date to get digest for
            
        Returns:
            Digest instance if found, None otherwise
        """
        return (
            self.query().filter(Digest.digest_date == digest_date).first()
        )

    def get_or_create_by_date(
        self, digest_date: date, defaults: Optional[Dict[str, Any]] = None
    ) -> tuple[Digest, bool]:
        """
        Get existing digest or create a new one for the date.
        
        Args:
            digest_date: Date for the digest
            defaults: Dictionary of default values for new digest creation
            
        Returns:
            Tuple of (digest_instance, created) where created is True if new
        """
        digest = self.get_by_date(digest_date)
        if digest:
            return digest, False

        defaults = defaults or {}
        defaults["digest_date"] = digest_date
        digest = Digest(**defaults)
        return self.create(digest), True

    def get_unsent_digests(self) -> List[Digest]:
        """
        Get digests that haven't been sent via email.
        
        Returns:
            List of digests where email_sent = False
        """
        return (
            self.query().filter(Digest.email_sent == False).order_by(Digest.digest_date.desc()).all()
        )

    def mark_email_sent(self, digest_id: int) -> Optional[Digest]:
        """
        Mark a digest as sent with current timestamp.
        
        Args:
            digest_id: Digest ID to mark as sent
            
        Returns:
            Updated digest instance if found, None otherwise
            
        Note:
            Does not commit - caller must commit the session
        """
        digest = self.get_by_id(digest_id)
        if not digest:
            return None

        digest.email_sent = True
        digest.email_sent_at = datetime.now()
        return self.update(digest)

    def get_recent_digests(self, limit: int = 10) -> List[Digest]:
        """
        Get most recent digests.
        
        Args:
            limit: Maximum number of digests to return (default: 10)
            
        Returns:
            List of digests sorted by digest_date (newest first)
        """
        return (
            self.query()
            .order_by(Digest.digest_date.desc())
            .limit(limit)
            .all()
        )

    def get_by_date_range(
        self, start_date: date, end_date: date
    ) -> List[Digest]:
        """
        Get digests within a date range.
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            
        Returns:
            List of digests sorted by digest_date (newest first)
        """
        return (
            self.query()
            .filter(
                and_(
                    Digest.digest_date >= start_date,
                    Digest.digest_date <= end_date,
                )
            )
            .order_by(Digest.digest_date.desc())
            .all()
        )

    def add_content(
        self,
        digest_id: int,
        videos: Optional[List[YouTubeVideo]] = None,
        openai_articles: Optional[List[OpenAIArticle]] = None,
        anthropic_articles: Optional[List[AnthropicArticle]] = None,
    ) -> Optional[Digest]:
        """
        Add content (videos/articles) to a digest.
        
        Args:
            digest_id: Digest ID to add content to
            videos: Optional list of YouTube videos to add
            openai_articles: Optional list of OpenAI articles to add
            anthropic_articles: Optional list of Anthropic articles to add
            
        Returns:
            Updated digest instance if found, None otherwise
            
        Note:
            Does not commit - caller must commit the session
        """
        digest = self.get_by_id(digest_id)
        if not digest:
            return None

        if videos:
            digest.youtube_videos.extend(videos)
        if openai_articles:
            digest.openai_articles.extend(openai_articles)
        if anthropic_articles:
            digest.anthropic_articles.extend(anthropic_articles)

        return self.update(digest)

