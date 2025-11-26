"""
Manual test script for CuratorAgent and EmailAgent using Gemini.

Usage (from project root):

    python test_curator_email_agents.py

Requires:
- GEMINI_API_KEY (and optional GEMINI_MODEL) in your environment / .env
"""

from __future__ import annotations

import logging
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

# Ensure project root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agent import (  # type: ignore  # noqa: E402
    CuratorAgent,
    EmailAgent,
    UserPreferences,
)
from app.config import settings  # type: ignore  # noqa: E402
from app.database.models import (  # type: ignore  # noqa: E402
    AnthropicArticle,
    Digest,
    OpenAIArticle,
    YouTubeVideo,
)


def build_fake_digest() -> Digest:
    """Create an in-memory Digest with some fake content items."""
    now = datetime.now(timezone.utc)

    # Fake YouTube video
    yt_video = YouTubeVideo(
        video_id="fake_video_1",
        title="New Gemini model and GPT-4 comparison",
        description="A deep-dive into the latest multimodal AI models.",
        channel_id="channel_123",
        channel_name="AI Explainer",
        published_at=now - timedelta(hours=5),
        url="https://youtube.com/watch?v=fake_video_1",
        thumbnail_url=None,
        duration=600,
        transcript=(
            "In this video we explore the differences between Gemini and GPT-4, "
            "including multimodal capabilities and reasoning benchmarks."
        ),
        transcript_status=None,  # not used in curator
        transcript_error=None,
    )

    # Fake OpenAI article
    oa_article = OpenAIArticle(
        article_id="fake_openai_1",
        title="Advances in AI reasoning and safety",
        url="https://openai.com/blog/fake-advances",
        author="OpenAI Research",
        published_at=now - timedelta(days=1),
        content="Long-form article content about AI reasoning, safety, and evaluations.",
        content_markdown="Article about AI reasoning, safety, and evaluation benchmarks.",
        summary="Overview of recent advances in AI reasoning and safety from OpenAI.",
        processing_status=None,  # not used here
    )

    # Fake Anthropic article
    an_article = AnthropicArticle(
        article_id="fake_anthropic_1",
        title="Constitutional AI and better alignment",
        url="https://www.anthropic.com/news/fake-constitutional-ai",
        author="Anthropic",
        published_at=now - timedelta(days=2),
        content="Discussion of Constitutional AI and techniques for safer models.",
        content_markdown="Anthropic article about Constitutional AI and alignment.",
        summary="Summary of Anthropic's work on Constitutional AI.",
        processing_status=None,  # not used here
    )

    digest = Digest(
        digest_date=date.today(),
        title="Daily AI News Digest",
        content="This is a fake digest content used for manual testing.",
        email_sent=False,
    )

    # Attach related items (works in-memory without DB commit)
    digest.youtube_videos.append(yt_video)
    digest.openai_articles.append(oa_article)
    digest.anthropic_articles.append(an_article)

    return digest


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    print("Gemini model:", settings.gemini.model)

    digest = build_fake_digest()

    prefs = UserPreferences(
        topics=["gemini", "gpt-4", "reasoning", "safety"],
        providers=["AI Explainer", "OpenAI", "Anthropic"],
        max_items=5,
        name="Test User",
    )

    curator = CuratorAgent(settings)
    curated_items = curator.curate_from_digest(digest, prefs)
    explanation = curator.refine_recommendations_with_llm(curated_items, prefs)

    print("\n--- Curated items ---")
    for item in curated_items:
        print(f"- [{item.source_type}] {item.title} (score={item.score:.2f}) -> {item.url}")

    print("\nRecommendation explanation:")
    print(explanation)

    email_agent = EmailAgent(settings)
    email_content = email_agent.compose_digest_email(
        digest=digest,
        curated_items=curated_items,
        prefs=prefs,
        use_llm_subject=True,
        use_llm_intro=True,
        recommendations_explanation=explanation,
    )

    print("\n--- Email Subject ---")
    print(email_content.subject)

    print("\n--- Email Text Body (first 400 chars) ---")
    print(email_content.text_body[:400] + ("..." if len(email_content.text_body) > 400 else ""))

    print("\n--- Email HTML Body length ---")
    print(len(email_content.html_body), "characters")


if __name__ == "__main__":
    main()


