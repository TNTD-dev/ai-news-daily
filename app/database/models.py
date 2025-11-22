"""
Database models for the AI News Aggregator application.

This module defines SQLAlchemy models for storing content from multiple sources
(YouTube, OpenAI, Anthropic) and generated digests. All models include proper
indexing, relationships, and processing status tracking.
"""

from datetime import date, datetime
from enum import Enum
from typing import List

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class ProcessingStatus(str, Enum):
    """
    Enumeration for content processing status.
    
    Used to track the processing pipeline stages for articles and videos.
    Values represent the current state of processing.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TranscriptStatus(str, Enum):
    """
    Enumeration for YouTube video transcript extraction status.
    
    Used specifically for tracking transcript extraction pipeline stages.
    Values represent the current state of transcript processing.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TimestampMixin:
    """
    Mixin class providing created_at and updated_at timestamp fields.
    
    All models that inherit from this mixin will automatically have
    timestamp tracking for when records are created and updated.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when the record was created",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="Timestamp when the record was last updated",
    )


class YouTubeVideo(Base, TimestampMixin):
    """
    Model for storing YouTube video metadata and transcripts.
    
    This model stores information about YouTube videos scraped from RSS feeds,
    including metadata (title, description, channel info) and extracted transcripts.
    Processing status is tracked to enable retry logic for failed transcript extractions.
    
    Attributes:
        id: Primary key
        video_id: Unique YouTube video ID (e.g., from URL: youtube.com/watch?v=VIDEO_ID)
        title: Video title
        description: Video description (nullable)
        channel_id: YouTube channel ID
        channel_name: Channel display name
        published_at: When the video was published on YouTube
        url: Full YouTube URL
        thumbnail_url: URL to video thumbnail image
        duration: Video duration in seconds
        transcript: Extracted video transcript text
        transcript_status: Processing status ('pending', 'processing', 'completed', 'failed')
        transcript_error: Error message if transcript extraction failed
    """

    __tablename__ = "youtube_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, doc="Primary key")
    video_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        doc="Unique YouTube video ID",
    )
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, index=True, doc="Video title"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="Video description"
    )
    channel_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, doc="YouTube channel ID"
    )
    channel_name: Mapped[str] = mapped_column(
        String(200), nullable=False, doc="Channel display name"
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="Video publication date on YouTube",
    )
    url: Mapped[str] = mapped_column(
        String(500), unique=True, nullable=False, doc="Full YouTube URL"
    )
    thumbnail_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True, doc="URL to video thumbnail"
    )
    duration: Mapped[int | None] = mapped_column(
        Integer, nullable=True, doc="Video duration in seconds"
    )
    transcript: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="Extracted video transcript"
    )
    transcript_status: Mapped[TranscriptStatus] = mapped_column(
        SQLEnum(TranscriptStatus, native_enum=True),
        nullable=False,
        default=TranscriptStatus.PENDING,
        index=True,
        doc="Processing status: 'pending', 'processing', 'completed', 'failed'",
    )
    transcript_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="Error message if transcript extraction failed"
    )

    # Relationships
    digests: Mapped[List["Digest"]] = relationship(
        "Digest",
        secondary="digest_youtube_videos",
        back_populates="youtube_videos",
        doc="Digests that include this video",
    )

    __table_args__ = (
        Index("idx_youtube_video_published_at", "published_at"),
        Index("idx_youtube_video_channel_published", "channel_id", "published_at"),
    )

    def __repr__(self) -> str:
        return f"<YouTubeVideo(id={self.id}, video_id='{self.video_id}', title='{self.title[:50]}...')>"


class OpenAIArticle(Base, TimestampMixin):
    """
    Model for storing OpenAI blog articles.
    
    This model stores articles scraped from OpenAI's RSS feed, including
    full content, markdown conversion, and AI-generated summaries.
    Processing status tracks the conversion and summarization pipeline stages.
    
    Attributes:
        id: Primary key
        article_id: Unique identifier from RSS feed
        title: Article title
        url: Article URL (unique)
        author: Article author (nullable)
        published_at: When the article was published
        content: Full article content (HTML/text)
        content_markdown: Converted markdown content (nullable)
        summary: AI-generated summary (nullable)
        processing_status: Processing status ('pending', 'processing', 'completed', 'failed')
    """

    __tablename__ = "openai_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, doc="Primary key")
    article_id: Mapped[str] = mapped_column(
        String(200),
        unique=True,
        nullable=False,
        index=True,
        doc="Unique identifier from RSS feed",
    )
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, index=True, doc="Article title"
    )
    url: Mapped[str] = mapped_column(
        String(500), unique=True, nullable=False, doc="Article URL"
    )
    author: Mapped[str | None] = mapped_column(
        String(200), nullable=True, doc="Article author"
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="Article publication date",
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Full article content"
    )
    content_markdown: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="Converted markdown content"
    )
    summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="AI-generated summary"
    )
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        SQLEnum(ProcessingStatus, native_enum=True),
        nullable=False,
        default=ProcessingStatus.PENDING,
        index=True,
        doc="Processing status: 'pending', 'processing', 'completed', 'failed'",
    )

    # Relationships
    digests: Mapped[List["Digest"]] = relationship(
        "Digest",
        secondary="digest_openai_articles",
        back_populates="openai_articles",
        doc="Digests that include this article",
    )

    __table_args__ = (
        Index("idx_openai_article_published_at", "published_at"),
    )

    def __repr__(self) -> str:
        return f"<OpenAIArticle(id={self.id}, article_id='{self.article_id}', title='{self.title[:50]}...')>"


class AnthropicArticle(Base, TimestampMixin):
    """
    Model for storing Anthropic blog articles.
    
    This model stores articles scraped from Anthropic's RSS feeds, including
    full content, markdown conversion, and AI-generated summaries.
    Processing status tracks the conversion and summarization pipeline stages.
    
    Attributes:
        id: Primary key
        article_id: Unique identifier from RSS feed
        title: Article title
        url: Article URL (unique)
        author: Article author (nullable)
        published_at: When the article was published
        content: Full article content (HTML/text)
        content_markdown: Converted markdown content (nullable)
        summary: AI-generated summary (nullable)
        processing_status: Processing status ('pending', 'processing', 'completed', 'failed')
    """

    __tablename__ = "anthropic_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, doc="Primary key")
    article_id: Mapped[str] = mapped_column(
        String(200),
        unique=True,
        nullable=False,
        index=True,
        doc="Unique identifier from RSS feed",
    )
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, index=True, doc="Article title"
    )
    url: Mapped[str] = mapped_column(
        String(500), unique=True, nullable=False, doc="Article URL"
    )
    author: Mapped[str | None] = mapped_column(
        String(200), nullable=True, doc="Article author"
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="Article publication date",
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Full article content"
    )
    content_markdown: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="Converted markdown content"
    )
    summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, doc="AI-generated summary"
    )
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        SQLEnum(ProcessingStatus, native_enum=True),
        nullable=False,
        default=ProcessingStatus.PENDING,
        index=True,
        doc="Processing status: 'pending', 'processing', 'completed', 'failed'",
    )

    # Relationships
    digests: Mapped[List["Digest"]] = relationship(
        "Digest",
        secondary="digest_anthropic_articles",
        back_populates="anthropic_articles",
        doc="Digests that include this article",
    )

    __table_args__ = (
        Index("idx_anthropic_article_published_at", "published_at"),
    )

    def __repr__(self) -> str:
        return f"<AnthropicArticle(id={self.id}, article_id='{self.article_id}', title='{self.title[:50]}...')>"


# Association tables for many-to-many relationships
digest_youtube_videos = Table(
    "digest_youtube_videos",
    Base.metadata,
    Column("digest_id", Integer, ForeignKey("digests.id"), primary_key=True),
    Column("youtube_video_id", Integer, ForeignKey("youtube_videos.id"), primary_key=True),
    doc="Association table linking digests to YouTube videos",
)

digest_openai_articles = Table(
    "digest_openai_articles",
    Base.metadata,
    Column("digest_id", Integer, ForeignKey("digests.id"), primary_key=True),
    Column("openai_article_id", Integer, ForeignKey("openai_articles.id"), primary_key=True),
    doc="Association table linking digests to OpenAI articles",
)

digest_anthropic_articles = Table(
    "digest_anthropic_articles",
    Base.metadata,
    Column("digest_id", Integer, ForeignKey("digests.id"), primary_key=True),
    Column("anthropic_article_id", Integer, ForeignKey("anthropic_articles.id"), primary_key=True),
    doc="Association table linking digests to Anthropic articles",
)


class Digest(Base, TimestampMixin):
    """
    Model for storing generated daily digests.
    
    A digest aggregates curated content from multiple sources (YouTube videos,
    OpenAI articles, Anthropic articles) into a single daily summary. The model
    tracks email delivery status and maintains relationships to all included content.
    
    Attributes:
        id: Primary key
        digest_date: Date the digest was generated for (unique per day)
        title: Digest title
        content: Full digest HTML/markdown content
        email_sent: Whether the digest email was sent
        email_sent_at: Timestamp when email was sent (nullable)
        youtube_videos: Related YouTube videos included in this digest
        openai_articles: Related OpenAI articles included in this digest
        anthropic_articles: Related Anthropic articles included in this digest
    """

    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, doc="Primary key")
    digest_date: Mapped[date] = mapped_column(
        Date,
        unique=True,
        nullable=False,
        index=True,
        doc="Date the digest was generated for",
    )
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, doc="Digest title"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Full digest HTML/markdown content"
    )
    email_sent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        doc="Whether the digest email was sent",
    )
    email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp when email was sent",
    )

    # Relationships
    youtube_videos: Mapped[List["YouTubeVideo"]] = relationship(
        "YouTubeVideo",
        secondary=digest_youtube_videos,
        back_populates="digests",
        doc="YouTube videos included in this digest",
    )
    openai_articles: Mapped[List["OpenAIArticle"]] = relationship(
        "OpenAIArticle",
        secondary=digest_openai_articles,
        back_populates="digests",
        doc="OpenAI articles included in this digest",
    )
    anthropic_articles: Mapped[List["AnthropicArticle"]] = relationship(
        "AnthropicArticle",
        secondary=digest_anthropic_articles,
        back_populates="digests",
        doc="Anthropic articles included in this digest",
    )

    __table_args__ = (
        Index("idx_digest_date", "digest_date"),
        Index("idx_digest_email_sent", "email_sent"),
        CheckConstraint(
            "digest_date <= CURRENT_DATE",
            name="check_digest_date_not_future",
        ),
    )

    def __repr__(self) -> str:
        return f"<Digest(id={self.id}, digest_date={self.digest_date}, title='{self.title[:50]}...')>"

