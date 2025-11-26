"""
Manual test script for DigestAgent using Gemini.

Usage:
    Ensure .env has GEMINI_API_KEY (and optional GEMINI_MODEL).
    Then run from project root:

        python test_digest_agent.py
"""

import logging
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import settings  # type: ignore  # noqa: E402
from app.agent.digest import DigestAgent  # type: ignore  # noqa: E402


def main() -> None:
    # Basic logging to console
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    print("GEMINI_MODEL:", settings.gemini.model)
    print("GEMINI_API_KEY set:", bool(os.getenv("GEMINI_API_KEY")))

    agent = DigestAgent(settings)

    sample_content = (
        "OpenAI, Google, and Anthropic continue to release new AI models and tools. "
        "Recent advances include multimodal models that can process text, images, "
        "and even audio, as well as improved reasoning capabilities. "
        "There is also growing focus on safety, evaluation benchmarks, "
        "and practical applications in education, coding, and productivity."
    )

    metadata = {
        "title": "Recent AI Developments",
        "author": "AI News Bot",
        "url": "https://example.com/ai-news",
    }

    print("\n--- Running DigestAgent.summarize_content() ---\n")
    summary = agent.summarize_content(
        content=sample_content,
        content_type="openai_article",
        metadata=metadata,
    )

    print("Summary:\n")
    print(summary)


if __name__ == "__main__":
    main()


