"""
Digest agent for content summarization and aggregation.

This module implements the DigestAgent class that processes content from multiple
sources (YouTube videos, OpenAI articles, Anthropic articles) to create digest summaries.
"""

from datetime import datetime
from typing import Any

from app.agent.base import BaseAgent
from app.config import AppConfig
from app.database.models import (
    AnthropicArticle,
    OpenAIArticle,
    TranscriptStatus,
    YouTubeVideo,
)


class DigestAgent(BaseAgent):
    """
    AI agent for creating digest summaries from multiple content sources.
    
    This agent aggregates and summarizes content from:
    - YouTube videos (using transcripts)
    - OpenAI blog articles (using markdown content or summaries)
    - Anthropic blog articles (using markdown content or summaries)
    
    Features:
    - Individual content item summarization
    - Multi-source content aggregation
    - Token limit handling for large content
    - Structured prompt engineering
    """

    # Approximate token limits (conservative estimates)
    # GPT-4 has ~8k context window, we'll use ~6k for input to leave room for output
    MAX_INPUT_TOKENS = 500000
    # Rough estimate: 1 token ≈ 4 characters
    CHARS_PER_TOKEN = 4
    MAX_INPUT_CHARS = MAX_INPUT_TOKENS * CHARS_PER_TOKEN

    def __init__(self, config: AppConfig) -> None:
        """
        Initialize digest agent.
        
        Args:
            config: Application configuration
        """
        super().__init__(config)

    def summarize_content(
        self, content: str, content_type: str, metadata: dict[str, Any] | None = None
    ) -> str:
        """
        Summarize individual content items.
        
        Args:
            content: The content text to summarize
            content_type: Type of content (e.g., "youtube_video", "openai_article", "anthropic_article")
            metadata: Optional metadata dictionary with title, author, published_at, url, etc.
            
        Returns:
            Summarized content as a string
        """
        if not content or not content.strip():
            self._log_error("Empty content provided for summarization", content_type=content_type)
            return ""

        # Build metadata context
        metadata_str = ""
        if metadata:
            parts = []
            if metadata.get("title"):
                parts.append(f"Title: {metadata['title']}")
            if metadata.get("author"):
                parts.append(f"Author: {metadata['author']}")
            if metadata.get("published_at"):
                pub_date = metadata["published_at"]
                if isinstance(pub_date, datetime):
                    parts.append(f"Published: {pub_date.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                else:
                    parts.append(f"Published: {pub_date}")
            if metadata.get("url"):
                parts.append(f"URL: {metadata['url']}")
            if metadata.get("channel_name"):
                parts.append(f"Channel: {metadata['channel_name']}")
            
            if parts:
                metadata_str = "\n".join(parts) + "\n\n"

        # Create prompt for summarization
        prompt = f"""You are an expert AI news analyst specializing in summarizing technical articles, research papers, and video content about artificial intelligence. 
        Your role is to create concise, informative digests that help readers quickly understand the key points and significance of AI-related content.
        Summarize the following {content_type} content in a way that is easy to understand and engaging.

{metadata_str}Content:
{content}

Please provide a concise summary that captures:
1. The main topic and key points
2. Important details or insights
3. Any notable conclusions or takeaways

Keep the summary clear, informative, and well-structured. Aim for 2-4 paragraphs."""

        # Handle token limits by chunking if necessary
        if len(content) > self.MAX_INPUT_CHARS:
            self._log_info(
                f"Content exceeds token limit, chunking for summarization",
                content_type=content_type,
                content_length=len(content),
                max_chars=self.MAX_INPUT_CHARS,
            )
            return self._summarize_large_content(content, content_type, metadata_str)

        try:
            messages = [
                {"role": "system", "content": "You are a helpful assistant that creates clear, concise summaries of technical and educational content."},
                {"role": "user", "content": prompt},
            ]

            summary = self._call_llm(
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
            )

            self._log_info(
                f"Successfully summarized {content_type}",
                content_length=len(content),
                summary_length=len(summary),
            )

            return summary.strip()

        except Exception as e:
            self._log_error(
                f"Failed to summarize {content_type}",
                exception=e,
                content_length=len(content),
            )
            # Return a fallback summary
            return f"Summary unavailable for this {content_type}. Original content length: {len(content)} characters."

    def _summarize_large_content(
        self, content: str, content_type: str, metadata_str: str
    ) -> str:
        """
        Summarize large content by chunking it into smaller pieces.
        
        Args:
            content: The content text to summarize
            content_type: Type of content
            metadata_str: Metadata string to include in each chunk
            
        Returns:
            Aggregated summary of all chunks
        """
        # Split content into chunks
        chunk_size = self.MAX_INPUT_CHARS - 500  # Leave room for prompt overhead
        chunks = []
        for i in range(0, len(content), chunk_size):
            chunks.append(content[i : i + chunk_size])

        self._log_info(
            f"Chunking large content into {len(chunks)} pieces",
            content_type=content_type,
            total_chunks=len(chunks),
        )

        # Summarize each chunk
        chunk_summaries = []
        for idx, chunk in enumerate(chunks):
            try:
                chunk_prompt = f"""You are summarizing a portion of a larger {content_type}. This is chunk {idx + 1} of {len(chunks)}.

{metadata_str}Content chunk:
{chunk}

Provide a concise summary of this portion of the content."""

                messages = [
                    {"role": "system", "content": "You are a helpful assistant that creates clear, concise summaries."},
                    {"role": "user", "content": chunk_prompt},
                ]

                chunk_summary = self._call_llm(
                    messages=messages,
                    temperature=0.7,
                    max_tokens=500,
                )
                chunk_summaries.append(chunk_summary.strip())
            except Exception as e:
                self._log_error(
                    f"Failed to summarize chunk {idx + 1}",
                    exception=e,
                    chunk_index=idx + 1,
                    total_chunks=len(chunks),
                )
                # Skip failed chunks
                continue

        if not chunk_summaries:
            return f"Failed to summarize large {content_type} content."

        # Combine chunk summaries into final summary
        combined_summaries = "\n\n".join(chunk_summaries)
        
        try:
            final_prompt = f"""You are creating a final summary from multiple partial summaries of a {content_type}.

Partial summaries:
{combined_summaries}

{metadata_str}Please create a cohesive, comprehensive summary that combines all the partial summaries into a single well-structured summary. Remove redundancy and ensure the summary flows naturally."""

            messages = [
                {"role": "system", "content": "You are a helpful assistant that synthesizes multiple summaries into a cohesive final summary."},
                {"role": "user", "content": final_prompt},
            ]

            final_summary = self._call_llm(
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
            )

            return final_summary.strip()
        except Exception as e:
            self._log_error(
                f"Failed to combine chunk summaries",
                exception=e,
            )
            # Return combined summaries as fallback
            return combined_summaries

    def _extract_video_content(self, video: YouTubeVideo) -> tuple[str, dict[str, Any]]:
        """
        Extract content and metadata from a YouTube video.
        
        Args:
            video: YouTubeVideo instance
            
        Returns:
            Tuple of (content, metadata_dict)
        """
        # Prefer transcript, fallback to description
        content = video.transcript or video.description or ""
        
        metadata = {
            "title": video.title,
            "channel_name": video.channel_name,
            "published_at": video.published_at,
            "url": video.url,
        }
        
        return content, metadata

    def _extract_article_content(
        self, article: OpenAIArticle | AnthropicArticle
    ) -> tuple[str, dict[str, Any]]:
        """
        Extract content and metadata from an article (OpenAI or Anthropic).
        
        Args:
            article: OpenAIArticle or AnthropicArticle instance
            
        Returns:
            Tuple of (content, metadata_dict)
        """
        # Prefer markdown, then summary, then raw content
        content = (
            article.content_markdown
            or article.summary
            or getattr(article, "content", "")
        )
        
        metadata = {
            "title": article.title,
            "author": article.author,
            "published_at": article.published_at,
            "url": article.url,
        }
        
        return content, metadata

    def aggregate_from_sources(
        self,
        videos: list[YouTubeVideo] | None = None,
        openai_articles: list[OpenAIArticle] | None = None,
        anthropic_articles: list[AnthropicArticle] | None = None,
    ) -> str:
        """
        Aggregate and summarize content from multiple sources.
        
        This method processes content from all provided sources and creates
        a comprehensive digest summary.
        
        Args:
            videos: Optional list of YouTubeVideo instances
            openai_articles: Optional list of OpenAIArticle instances
            anthropic_articles: Optional list of AnthropicArticle instances
            
        Returns:
            Aggregated digest summary as formatted text
        """
        summaries = []

        # Process YouTube videos
        if videos:
            self._log_info(f"Processing {len(videos)} YouTube videos")
            for video in videos:
                # Only process videos with completed transcripts
                if video.transcript_status != TranscriptStatus.COMPLETED:
                    self._log_info(
                        f"Skipping video without completed transcript",
                        video_id=video.video_id,
                        status=video.transcript_status.value,
                    )
                    continue

                content, metadata = self._extract_video_content(video)
                if content:
                    summary = self.summarize_content(
                        content, "youtube_video", metadata
                    )
                    if summary:
                        summaries.append({
                            "type": "YouTube Video",
                            "title": video.title,
                            "channel": video.channel_name,
                            "url": video.url,
                            "summary": summary,
                        })

        # Process OpenAI articles
        if openai_articles:
            self._log_info(f"Processing {len(openai_articles)} OpenAI articles")
            for article in openai_articles:
                content, metadata = self._extract_article_content(article)
                if content:
                    summary = self.summarize_content(
                        content, "openai_article", metadata
                    )
                    if summary:
                        summaries.append({
                            "type": "OpenAI Article",
                            "title": article.title,
                            "author": article.author or "Unknown",
                            "url": article.url,
                            "summary": summary,
                        })

        # Process Anthropic articles
        if anthropic_articles:
            self._log_info(f"Processing {len(anthropic_articles)} Anthropic articles")
            for article in anthropic_articles:
                content, metadata = self._extract_article_content(article)
                if content:
                    summary = self.summarize_content(
                        content, "anthropic_article", metadata
                    )
                    if summary:
                        summaries.append({
                            "type": "Anthropic Article",
                            "title": article.title,
                            "author": article.author or "Unknown",
                            "url": article.url,
                            "summary": summary,
                        })

        if not summaries:
            self._log_info("No content to aggregate")
            return "No content available for digest generation."

        # Create final aggregated summary
        return self._create_final_digest(summaries)

    def _create_final_digest(self, summaries: list[dict[str, Any]]) -> str:
        """
        Create a final formatted digest from individual summaries.
        
        Args:
            summaries: List of summary dictionaries with type, title, url, summary
            
        Returns:
            Formatted digest text
        """
        # Build content for aggregation prompt
        content_parts = []
        for idx, item in enumerate(summaries, 1):
            content_parts.append(
                f"""Item {idx}: {item['type']}
Title: {item['title']}
URL: {item['url']}
Summary: {item['summary']}"""
            )

        content_text = "\n\n---\n\n".join(content_parts)

        # Create aggregation prompt
        prompt = f"""You are creating a daily AI news digest from multiple sources. Below are summaries of individual items from YouTube videos, OpenAI blog articles, and Anthropic blog articles.

Your task is to create a cohesive, well-organized daily digest that:
1. Groups related content together
2. Highlights the most important developments
3. Provides clear, engaging summaries
4. Maintains a professional but accessible tone

Individual item summaries:
{content_text}

Please create a comprehensive daily digest with:
- An engaging introduction
- Organized sections by topic/theme
- Clear summaries of each item
- A brief conclusion

Format the digest in markdown with proper headings, links, and structure."""

        try:
            messages = [
                {
                    "role": "system",
                    "content": "You are an expert content curator and writer who creates engaging, well-structured daily news digests.",
                },
                {"role": "user", "content": prompt},
            ]

            digest = self._call_llm(
                messages=messages,
                temperature=0.8,
                max_tokens=2000,
            )

            self._log_info(
                f"Successfully created digest from {len(summaries)} items",
                digest_length=len(digest),
            )

            return digest.strip()

        except Exception as e:
            self._log_error(
                f"Failed to create final digest",
                exception=e,
                num_items=len(summaries),
            )
            # Fallback: return formatted summaries
            return self._format_fallback_digest(summaries)

    def _format_fallback_digest(self, summaries: list[dict[str, Any]]) -> str:
        """
        Format summaries as a simple digest when aggregation fails.
        
        Args:
            summaries: List of summary dictionaries
            
        Returns:
            Formatted digest text
        """
        lines = ["# Daily AI News Digest\n"]
        
        for item in summaries:
            lines.append(f"## {item['title']}")
            lines.append(f"**Source:** {item['type']}")
            if 'author' in item:
                lines.append(f"**Author:** {item['author']}")
            lines.append(f"**URL:** {item['url']}\n")
            lines.append(item['summary'])
            lines.append("\n---\n")

        return "\n".join(lines)

