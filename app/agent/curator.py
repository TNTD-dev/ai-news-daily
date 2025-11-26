"""
Curator agent for ranking and personalizing content based on user preferences.

This module defines:
- UserPreferences: lightweight preferences model
- CuratedItem: normalized view of content items
- CuratorAgent: logic for scoring, ranking, and optional LLM refinement
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, List

from app.agent.base import BaseAgent
from app.config import AppConfig
from app.database.models import AnthropicArticle, Digest, OpenAIArticle, YouTubeVideo


@dataclass
class UserPreferences:
    """
    Generic user preferences for content curation.

    Attributes:
        topics: List of preferred topics/keywords (lowercased for matching).
        providers: Preferred providers (e.g., YouTube channel names, domains).
        max_items: Maximum number of recommended items to return.
        boost_recency: Weight for recency in scoring (0-1 range, heuristic).
        boost_matching_topics: Weight for topic matches.
        name: Optional user name for personalization in explanations/emails.
    """

    topics: List[str] = field(default_factory=list)
    providers: List[str] = field(default_factory=list)
    max_items: int = 10
    boost_recency: float = 0.3
    boost_matching_topics: float = 1.0
    name: str | None = None

    def normalized_topics(self) -> List[str]:
        return [t.lower() for t in self.topics if t.strip()]

    def normalized_providers(self) -> List[str]:
        return [p.lower() for p in self.providers if p.strip()]


@dataclass
class CuratedItem:
    """
    Normalized representation of a content item for curation and email.

    Attributes:
        source_type: 'youtube' | 'openai' | 'anthropic'
        title: Human-readable title
        summary: Short summary or key content
        url: Link to the original content
        published_at: Datetime when the item was published
        provider: Channel or site (e.g., YouTube channel name)
        score: Relevance score computed by CuratorAgent
    """

    source_type: str
    title: str
    summary: str
    url: str
    published_at: datetime | None
    provider: str | None = None
    score: float = 0.0


class CuratorAgent(BaseAgent):
    """
    Agent responsible for content curation and ranking.

    Uses simple heuristic scoring based on:
    - Topic keyword matches in title/summary
    - Preferred providers (channels/sites)
    - Recency (newer content is favored)
    """

    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def curate_from_digest(
        self, digest: Digest, prefs: UserPreferences
    ) -> List[CuratedItem]:
        """
        Build and rank curated items from a Digest and user preferences.

        Args:
            digest: Digest instance with related videos and articles loaded.
            prefs: User preferences for ranking.

        Returns:
            List of CuratedItem sorted by descending score.
        """
        items: list[CuratedItem] = []

        # YouTube videos
        for video in digest.youtube_videos:
            items.append(self._from_youtube_video(video))

        # OpenAI articles
        for article in digest.openai_articles:
            items.append(self._from_openai_article(article))

        # Anthropic articles
        for article in digest.anthropic_articles:
            items.append(self._from_anthropic_article(article))

        ranked = self.rank_items(items, prefs)

        self._log_info(
            "Curated items from digest",
            digest_id=digest.id,
            digest_date=digest.digest_date,
            total_items=len(items),
            returned=len(ranked),
        )

        return ranked

    def rank_items(
        self, items: Iterable[CuratedItem], prefs: UserPreferences
    ) -> List[CuratedItem]:
        """
        Compute relevance scores for items and return top-N ranked list.

        Args:
            items: Iterable of CuratedItem to score.
            prefs: User preferences guiding the scoring.

        Returns:
            Ranked list of CuratedItem with scores populated.
        """
        scored: list[CuratedItem] = []

        for item in items:
            item.score = self.compute_relevance_score(item, prefs)
            scored.append(item)

        scored.sort(key=lambda i: i.score, reverse=True)
        return scored[: max(prefs.max_items, 0) or len(scored)]

    def compute_relevance_score(
        self, item: CuratedItem, prefs: UserPreferences
    ) -> float:
        """
        Compute a simple relevance score for a single item.

        Heuristic:
        - Base topic score: count of preferred topics appearing in title+summary
          multiplied by boost_matching_topics.
        - Provider boost: +1 if provider matches preferred list.
        - Recency score: normalized to [0, 1] based on age (up to ~7 days)
          multiplied by boost_recency.
        """
        topics = prefs.normalized_topics()
        providers = prefs.normalized_providers()

        text = f"{item.title} {item.summary}".lower()

        # Topic score
        topic_matches = 0
        for t in topics:
            if t and t in text:
                topic_matches += 1
        topic_score = topic_matches * prefs.boost_matching_topics

        # Provider boost
        provider_score = 0.0
        if item.provider and providers:
            provider_lc = item.provider.lower()
            if any(p in provider_lc for p in providers):
                provider_score = 1.0

        # Recency score: full score for <=1 day old, fades to 0 by ~7 days
        recency_score = 0.0
        if item.published_at:
            now = datetime.now(timezone.utc)
            published = item.published_at
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            age_hours = (now - published).total_seconds() / 3600.0
            if age_hours <= 0:
                recency_score = 1.0
            else:
                # Linear decay: 0-24h -> ~1, 24-168h -> down to 0
                max_hours = 24.0 * 7.0
                recency_score = max(0.0, 1.0 - min(age_hours, max_hours) / max_hours)

        total_score = topic_score + provider_score + recency_score * prefs.boost_recency

        return total_score

    def refine_recommendations_with_llm(
        self, items: List[CuratedItem], prefs: UserPreferences
    ) -> str:
        """
        Use Gemini to generate a human-readable explanation of recommendations.

        This is optional but useful for personalized intros in emails.
        """
        if not items:
            return "No recommendations are available for today."

        item_lines = []
        for idx, item in enumerate(items, start=1):
            item_lines.append(
                f"{idx}. [{item.source_type}] {item.title} (score={item.score:.2f})"
            )

        prefs_desc = ""
        if prefs.topics:
            prefs_desc += f"- Preferred topics: {', '.join(prefs.topics)}\n"
        if prefs.providers:
            prefs_desc += f"- Preferred providers: {', '.join(prefs.providers)}\n"

        user_name = prefs.name or "there"

        prompt = f"""You are an AI assistant helping to explain a set of recommended AI news items to a user.

User name: {user_name}
User preferences:
{prefs_desc if prefs_desc else '- No explicit preferences were provided.'}

Recommended items:
{chr(10).join(item_lines)}

Write a short, friendly explanation (2-3 sentences) summarizing why these items were selected for the user,
highlighting how they match the user's interests and the most important themes for today.
"""

        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant that explains personalized content recommendations clearly and briefly.",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            explanation = self._call_llm(messages=messages, temperature=0.7, max_tokens=200)
            return explanation.strip() or "Here are your recommended items for today."
        except Exception as e:
            self._log_error("Failed to generate LLM explanation for recommendations", exception=e)
            return "Here are your recommended items for today."

    # ------------------------------------------------------------------
    # Internal helpers to build CuratedItem instances
    # ------------------------------------------------------------------

    def _from_youtube_video(self, video: YouTubeVideo) -> CuratedItem:
        summary = (video.transcript or video.description or "").strip()
        return CuratedItem(
            source_type="youtube",
            title=video.title,
            summary=summary,
            url=video.url,
            published_at=video.published_at,
            provider=video.channel_name,
        )

    def _from_openai_article(self, article: OpenAIArticle) -> CuratedItem:
        summary = (article.summary or article.content_markdown or article.content or "").strip()
        return CuratedItem(
            source_type="openai",
            title=article.title,
            summary=summary,
            url=article.url,
            published_at=article.published_at,
            provider=article.author,
        )

    def _from_anthropic_article(self, article: AnthropicArticle) -> CuratedItem:
        summary = (article.summary or article.content_markdown or article.content or "").strip()
        return CuratedItem(
            source_type="anthropic",
            title=article.title,
            summary=summary,
            url=article.url,
            published_at=article.published_at,
            provider=article.author,
        )


