"""
Pipeline runner that orchestrates all scraping jobs end-to-end.

Responsibilities:
    1. Initialize database session via the shared session manager.
    2. Load the application configuration (singleton `settings`).
    3. Instantiate and execute all configured scrapers.
    4. Aggregate and report results for observability.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Tuple, Type

from app.config import AppConfig, settings
from app.database.session import get_session
from app.scrapers.anthropic import AnthropicScraper
from app.scrapers.openai import OpenAIScraper
from app.scrapers.youtube import YouTubeScraper

# Type aliases for readability
ScrapeResult = Dict[str, Any]
ScraperFactory = Callable[[Any, AppConfig], Any]


logger = logging.getLogger("app.runner")
logging.basicConfig(level=logging.INFO)

# Ordered list of scrapers to run as part of the pipeline.
SCRAPER_REGISTRY: List[Tuple[str, Type]] = [
    ("youtube", YouTubeScraper),
    ("openai", OpenAIScraper),
    ("anthropic", AnthropicScraper),
]


def _run_single_scraper(name: str, scraper_cls: Type, session, config: AppConfig) -> ScrapeResult:
    """
    Instantiate and execute a scraper, ensuring consistent error handling.
    """
    logger.info("Starting scraper: %s", name)

    try:
        scraper = scraper_cls(session=session, config=config)
        result = scraper.scrape()

        # Normalize result payload to guarantee basic keys.
        normalized: ScrapeResult = {
            "success": bool(result.get("success", True)),
            "details": result,
        }

        logger.info(
            "Scraper finished: %s | success=%s | summary=%s",
            name,
            normalized["success"],
            {k: v for k, v in result.items() if k not in {"errors"}},
        )
        if result.get("errors"):
            logger.warning("Scraper %s reported errors: %s", name, result["errors"])

        return normalized

    except Exception as exc:
        logger.exception("Scraper %s failed with unhandled exception", name)
        return {
            "success": False,
            "details": {"success": False, "errors": [str(exc)]},
        }


def run_pipeline(config: AppConfig | None = None) -> Dict[str, ScrapeResult]:
    """
    Execute the scraping pipeline and return per-scraper results.
    
    This function runs only the scraping stage (YouTube, OpenAI, Anthropic).
    For the complete pipeline including digest generation and email delivery,
    use app.daily_runner.DailyPipelineRunner instead.
    
    Args:
        config: Optional application configuration (uses settings singleton if not provided)
        
    Returns:
        Dictionary mapping scraper names to their results
    """
    return run_scraping_only(config)


def run_scraping_only(config: AppConfig | None = None) -> Dict[str, ScrapeResult]:
    """
    Execute only the scraping stage of the pipeline.
    
    This is a helper function that explicitly runs scraping only.
    The run_pipeline() function calls this internally for backward compatibility.
    
    Args:
        config: Optional application configuration (uses settings singleton if not provided)
        
    Returns:
        Dictionary mapping scraper names to their results
    """
    cfg = config or settings
    pipeline_results: Dict[str, ScrapeResult] = {}

    logger.info("Initializing database session for scraping pipeline")

    with get_session() as session:
        for scraper_name, scraper_cls in SCRAPER_REGISTRY:
            pipeline_results[scraper_name] = _run_single_scraper(
                scraper_name,
                scraper_cls,
                session,
                cfg,
            )

    overall_success = all(result["success"] for result in pipeline_results.values())
    logger.info("Scraping pipeline completed | overall_success=%s", overall_success)

    return pipeline_results


def main() -> None:
    """
    CLI entry-point so `python -m app.runner` launches the pipeline.
    """
    results = run_pipeline()

    # Emit concise report to stdout for quick inspection.
    print("Scraping pipeline finished")
    for name, result in results.items():
        status = "ok" if result["success"] else "failed"
        print(f" - {name}: {status}")
        details = result["details"]
        if details.get("errors"):
            for err in details["errors"]:
                print(f"    error: {err}")


if __name__ == "__main__":
    main()

