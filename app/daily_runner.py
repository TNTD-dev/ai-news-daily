"""
Daily pipeline orchestrator for complete end-to-end workflow.

This module provides DailyPipelineRunner which orchestrates:
1. Content scraping (YouTube, OpenAI, Anthropic)
2. Content collection and aggregation
3. Digest generation using AI agents
4. Personalized content curation
5. Email delivery to subscribers

The pipeline handles errors gracefully at each stage and provides
comprehensive logging throughout the process.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.agent.curator import CuratorAgent
from app.agent.digest import DigestAgent
from app.agent.email import EmailAgent
from app.config import AppConfig, settings
from app.database.models import (
    AnthropicArticle,
    Digest,
    OpenAIArticle,
    TranscriptStatus,
    UserProfile,
    YouTubeVideo,
)
from app.database.repositories import (
    AnthropicArticleRepository,
    DigestRepository,
    OpenAIArticleRepository,
    UserProfileRepository,
    YouTubeVideoRepository,
)
from app.database.session import get_session
from app.profiles.user_profile import UserProfileSettings
from app.runner import run_scraping_only
from app.services.email_service import EmailService


class DailyPipelineRunner:
    """
    Orchestrator for the complete daily pipeline from scraping to email delivery.
    
    Coordinates all stages of the pipeline:
    - Scraping content from various sources
    - Collecting and aggregating content
    - Generating digests using AI
    - Curating personalized content
    - Sending emails to subscribers
    """

    def __init__(self, config: AppConfig | None = None, session: Session | None = None):
        """
        Initialize the daily pipeline runner.
        
        Args:
            config: Application configuration (uses settings singleton if not provided)
            session: Database session (creates new one if not provided)
        """
        self.config = config or settings
        self.session = session
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Initialize agents
        self.digest_agent = DigestAgent(self.config)
        self.curator_agent = CuratorAgent(self.config)
        self.email_agent = EmailAgent(self.config)
        
        # Initialize repositories (will be set when session is available)
        self.youtube_repo: Optional[YouTubeVideoRepository] = None
        self.openai_repo: Optional[OpenAIArticleRepository] = None
        self.anthropic_repo: Optional[AnthropicArticleRepository] = None
        self.digest_repo: Optional[DigestRepository] = None
        self.user_profile_repo: Optional[UserProfileRepository] = None
        
        # Initialize email service (will be set when session is available)
        self.email_service: Optional[EmailService] = None
        
        # Initialize repositories if session is provided
        if self.session is not None:
            self._initialize_repositories()

    def _run_scraping_stage(self) -> Dict[str, Any]:
        """
        Execute the scraping stage by running all configured scrapers.
        
        Returns:
            Dictionary with scraping results including success status and details
        """
        self.logger.info("Starting scraping stage")
        
        try:
            results = run_scraping_only(self.config)
            
            # Calculate summary statistics
            total_scrapers = len(results)
            successful_scrapers = sum(1 for r in results.values() if r.get("success", False))
            
            self.logger.info(
                f"Scraping stage completed: total_scrapers={total_scrapers}, "
                f"successful={successful_scrapers}, failed={total_scrapers - successful_scrapers}"
            )
            
            return {
                "success": successful_scrapers > 0,  # Consider successful if at least one scraper worked
                "total_scrapers": total_scrapers,
                "successful_scrapers": successful_scrapers,
                "results": results,
            }
            
        except Exception as e:
            self.logger.error(
                f"Scraping stage failed with exception: {e}",
                exc_info=True
            )
            return {
                "success": False,
                "error": str(e),
                "total_scrapers": 0,
                "successful_scrapers": 0,
                "results": {},
            }

    def _collect_recent_content(self, hours: int | None = None) -> Dict[str, List]:
        """
        Collect recent content from all sources for digest generation.
        
        Args:
            hours: Number of hours to look back (uses config.scraping.hours_lookback if not provided)
            
        Returns:
            Dictionary with keys: 'videos', 'openai_articles', 'anthropic_articles'
        """
        if self.youtube_repo is None or self.openai_repo is None or self.anthropic_repo is None:
            raise ValueError("Repositories must be initialized before collecting content")
        
        hours_lookback = hours or self.config.scraping.hours_lookback
        max_items = self.config.scraping.max_articles
        
        self.logger.info(
            f"Collecting recent content: hours_lookback={hours_lookback}, max_items={max_items}"
        )
        
        try:
            # Get recent videos (only those with completed transcripts)
            videos = self.youtube_repo.get_recent_videos(hours=hours_lookback, limit=max_items)
            # Filter to only completed transcripts
            videos = [v for v in videos if v.transcript_status == TranscriptStatus.COMPLETED]
            
            # Get recent OpenAI articles
            openai_articles = self.openai_repo.get_recent_articles(
                hours=hours_lookback, limit=max_items
            )
            
            # Get recent Anthropic articles
            anthropic_articles = self.anthropic_repo.get_recent_articles(
                hours=hours_lookback, limit=max_items
            )
            
            self.logger.info(
                f"Content collection completed: videos={len(videos)}, "
                f"openai_articles={len(openai_articles)}, "
                f"anthropic_articles={len(anthropic_articles)}, "
                f"total_items={len(videos) + len(openai_articles) + len(anthropic_articles)}"
            )
            
            return {
                "videos": videos,
                "openai_articles": openai_articles,
                "anthropic_articles": anthropic_articles,
            }
            
        except Exception as e:
            self.logger.error(
                f"Content collection failed: {e}",
                exc_info=True
            )
            return {
                "videos": [],
                "openai_articles": [],
                "anthropic_articles": [],
            }

    def _generate_digest(
        self, target_date: date, content: Dict[str, List]
    ) -> Optional[Digest]:
        """
        Generate a digest for the target date using collected content.
        
        Args:
            target_date: Date for which to generate the digest
            content: Dictionary with 'videos', 'openai_articles', 'anthropic_articles'
            
        Returns:
            Digest instance if successful, None otherwise
        """
        if self.digest_repo is None:
            raise ValueError("DigestRepository must be initialized before generating digest")
        
        self.logger.info(
            f"Generating digest for target_date={target_date}, "
            f"videos={len(content.get('videos', []))}, "
            f"openai_articles={len(content.get('openai_articles', []))}, "
            f"anthropic_articles={len(content.get('anthropic_articles', []))}"
        )
        
        try:
            # Check if digest already exists
            existing_digest = self.digest_repo.get_by_date(target_date)
            if existing_digest:
                self.logger.info(
                    f"Digest already exists for date target_date={target_date}, "
                    f"digest_id={existing_digest.id}"
                )
                # Update content associations if needed
                if content.get("videos") or content.get("openai_articles") or content.get("anthropic_articles"):
                    self.digest_repo.add_content(
                        digest_id=existing_digest.id,
                        videos=content.get("videos"),
                        openai_articles=content.get("openai_articles"),
                        anthropic_articles=content.get("anthropic_articles"),
                    )
                    self.session.commit()
                return existing_digest
            
            # Generate digest content using DigestAgent
            videos = content.get("videos", [])
            openai_articles = content.get("openai_articles", [])
            anthropic_articles = content.get("anthropic_articles", [])
            
            if not videos and not openai_articles and not anthropic_articles:
                self.logger.warning(
                    f"No content available for digest generation for target_date={target_date}"
                )
                return None
            
            digest_content = self.digest_agent.aggregate_from_sources(
                videos=videos if videos else None,
                openai_articles=openai_articles if openai_articles else None,
                anthropic_articles=anthropic_articles if anthropic_articles else None,
            )
            
            if not digest_content or digest_content.strip() == "":
                self.logger.warning(
                    f"Digest agent returned empty content for target_date={target_date}"
                )
                return None
            
            # Create digest title
            digest_title = f"AI News Daily Digest – {target_date:%Y-%m-%d}"
            
            # Create or get digest record
            digest, created = self.digest_repo.get_or_create_by_date(
                target_date,
                defaults={
                    "title": digest_title,
                    "content": digest_content,
                },
            )
            
            if not created:
                # Update existing digest
                digest.title = digest_title
                digest.content = digest_content
                self.digest_repo.update(digest)
            
            # Associate content with digest
            self.digest_repo.add_content(
                digest_id=digest.id,
                videos=videos if videos else None,
                openai_articles=openai_articles if openai_articles else None,
                anthropic_articles=anthropic_articles if anthropic_articles else None,
            )
            
            # Commit changes
            self.session.commit()
            
            self.logger.info(
                f"Digest generated successfully: digest_id={digest.id}, "
                f"target_date={target_date}, content_length={len(digest_content)}"
            )
            
            return digest
            
        except Exception as e:
            self.logger.error(
                f"Digest generation failed for target_date={target_date}: {e}",
                exc_info=True
            )
            if self.session:
                self.session.rollback()
            return None

    def _send_digests_to_subscribers(self, digest: Digest) -> Dict[str, Any]:
        """
        Send personalized digest emails to all subscribers.
        
        Args:
            digest: Digest instance to send (must have relationships loaded)
            
        Returns:
            Dictionary with email delivery results including success/failure counts
        """
        if self.user_profile_repo is None or self.email_service is None:
            raise ValueError(
                "UserProfileRepository and EmailService must be initialized before sending emails"
            )
        
        self.logger.info(
            f"Starting email delivery to subscribers: digest_id={digest.id}, "
            f"digest_date={digest.digest_date}"
        )
        
        try:
            # Get all subscribers
            subscribers = self.user_profile_repo.get_subscribers()
            
            if not subscribers:
                self.logger.warning(
                    f"No subscribers found, using fallback email from config",
                )
                # Fallback to config email if no subscribers
                fallback_email = self.config.email.to_email
                if fallback_email:
                    # Try to get or create a profile for the fallback email
                    fallback_profile = self.user_profile_repo.get_by_email(fallback_email)
                    if not fallback_profile:
                        # Create a temporary profile for fallback (won't be saved)
                        from app.profiles.user_profile import get_default_user_profile
                        fallback_settings = get_default_user_profile(
                            email=fallback_email, name="Subscriber"
                        )
                        fallback_profile = fallback_settings.to_db_model()
                    subscribers = [fallback_profile]
            
            if not subscribers:
                self.logger.warning(f"No subscribers and no fallback email configured")
                return {
                    "success": False,
                    "total_subscribers": 0,
                    "emails_sent": 0,
                    "emails_failed": 0,
                    "errors": ["No subscribers found and no fallback email configured"],
                }
            
            self.logger.info(
                f"Found {len(subscribers)} subscribers"
            )
            
            # Ensure digest relationships are loaded
            # Refresh to ensure we have the latest data
            self.session.refresh(digest)
            
            emails_sent = 0
            emails_failed = 0
            errors: List[str] = []
            
            # Send email to each subscriber
            for user_profile_db in subscribers:
                try:
                    # Convert to UserProfileSettings
                    user_profile = UserProfileSettings.from_db_model(user_profile_db)
                    
                    self.logger.info(
                        f"Processing subscriber: email={user_profile.email}, "
                        f"name={user_profile.name}"
                    )
                    
                    # Curate content for this user
                    curated_items = self.curator_agent.curate_from_digest(
                        digest, user_profile
                    )
                    
                    # Optionally get LLM explanation
                    recommendations_explanation = None
                    if curated_items:
                        try:
                            recommendations_explanation = (
                                self.curator_agent.refine_recommendations_with_llm(
                                    curated_items, user_profile
                                )
                            )
                        except Exception as e:
                            self.logger.warning(
                                f"Failed to generate LLM explanation for {user_profile.email}, "
                                f"continuing without it: {e}"
                            )
                    
                    # Send email
                    success = self.email_service.send_digest_email(
                        digest=digest,
                        curated_items=curated_items,
                        user_email=user_profile.email,
                        user_profile=user_profile,
                        use_llm_subject=True,
                        use_llm_intro=True,
                    )
                    
                    if success:
                        emails_sent += 1
                        self.logger.info(
                            f"Email sent successfully to {user_profile.email}, "
                            f"curated_items_count={len(curated_items)}"
                        )
                    else:
                        emails_failed += 1
                        error_msg = f"Failed to send email to {user_profile.email}"
                        errors.append(error_msg)
                        self.logger.error(
                            f"Email delivery failed for {user_profile.email}"
                        )
                        
                except Exception as e:
                    emails_failed += 1
                    error_msg = f"Error processing subscriber {user_profile_db.email}: {str(e)}"
                    errors.append(error_msg)
                    self.logger.error(
                        f"Error processing subscriber {user_profile_db.email}: {e}",
                        exc_info=True
                    )
            
            result = {
                "success": emails_sent > 0,
                "total_subscribers": len(subscribers),
                "emails_sent": emails_sent,
                "emails_failed": emails_failed,
            }
            
            if errors:
                result["errors"] = errors
            
            self.logger.info(
                f"Email delivery stage completed: total_subscribers={len(subscribers)}, "
                f"emails_sent={emails_sent}, emails_failed={emails_failed}"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                f"Email delivery stage failed with exception for digest_id={digest.id}: {e}",
                exc_info=True
            )
            return {
                "success": False,
                "total_subscribers": 0,
                "emails_sent": 0,
                "emails_failed": 0,
                "errors": [str(e)],
            }

    def _initialize_repositories(self) -> None:
        """Initialize all repositories with the current session."""
        if self.session is None:
            raise ValueError("Session must be set before initializing repositories")
        
        self.youtube_repo = YouTubeVideoRepository(self.session)
        self.openai_repo = OpenAIArticleRepository(self.session)
        self.anthropic_repo = AnthropicArticleRepository(self.session)
        self.digest_repo = DigestRepository(self.session)
        self.user_profile_repo = UserProfileRepository(self.session)
        self.email_service = EmailService(self.config, self.session, self.email_agent)

    def run_complete_pipeline(self, target_date: date | None = None) -> Dict[str, Any]:
        """
        Run the complete daily pipeline from scraping to email delivery.
        
        This method orchestrates all stages:
        1. Scraping content from all sources
        2. Collecting recent content
        3. Generating digest
        4. Sending emails to subscribers
        
        Args:
            target_date: Date for digest (defaults to today)
            
        Returns:
            Dictionary with results from each stage including:
            - scraping: Scraping stage results
            - content_collection: Content collection results
            - digest_generation: Digest generation results
            - email_delivery: Email delivery results
            - overall_success: Boolean indicating if pipeline completed successfully
        """
        if target_date is None:
            target_date = date.today()
        
        self.logger.info(
            f"Starting complete daily pipeline for target_date={target_date}"
        )
        
        # Initialize session if not provided
        session_provided = self.session is not None
        if not session_provided:
            session = get_session().__enter__()
            self.session = session
            self._initialize_repositories()
        else:
            session = None
        
        results: Dict[str, Any] = {
            "target_date": target_date.isoformat(),
            "overall_success": False,
        }
        
        try:
            # Stage 1: Scraping
            self.logger.info("=" * 60)
            self.logger.info("STAGE 1: Scraping")
            self.logger.info("=" * 60)
            scraping_results = self._run_scraping_stage()
            results["scraping"] = scraping_results
            
            # Stage 2: Content Collection
            self.logger.info("=" * 60)
            self.logger.info("STAGE 2: Content Collection")
            self.logger.info("=" * 60)
            content = self._collect_recent_content()
            results["content_collection"] = {
                "videos_count": len(content.get("videos", [])),
                "openai_articles_count": len(content.get("openai_articles", [])),
                "anthropic_articles_count": len(content.get("anthropic_articles", [])),
                "total_items": (
                    len(content.get("videos", []))
                    + len(content.get("openai_articles", []))
                    + len(content.get("anthropic_articles", []))
                ),
            }
            
            # Stage 3: Digest Generation
            self.logger.info("=" * 60)
            self.logger.info("STAGE 3: Digest Generation")
            self.logger.info("=" * 60)
            digest = self._generate_digest(target_date, content)
            if digest:
                results["digest_generation"] = {
                    "success": True,
                    "digest_id": digest.id,
                    "digest_date": digest.digest_date.isoformat(),
                    "title": digest.title,
                }
            else:
                results["digest_generation"] = {
                    "success": False,
                    "error": "Failed to generate digest",
                }
                self.logger.error("Pipeline stopped: digest generation failed")
                results["overall_success"] = False
                return results
            
            # Stage 4: Email Delivery
            self.logger.info("=" * 60)
            self.logger.info("STAGE 4: Email Delivery")
            self.logger.info("=" * 60)
            email_results = self._send_digests_to_subscribers(digest)
            results["email_delivery"] = email_results
            
            # Determine overall success
            results["overall_success"] = (
                scraping_results.get("success", False)
                and digest is not None
                and email_results.get("success", False)
            )
            
            # Final summary
            self.logger.info("=" * 60)
            self.logger.info("PIPELINE COMPLETE")
            self.logger.info("=" * 60)
            self.logger.info(
                f"Pipeline summary for target_date={target_date}: "
                f"overall_success={results['overall_success']}, "
                f"scraping_success={scraping_results.get('success', False)}, "
                f"digest_created={digest is not None}, "
                f"emails_sent={email_results.get('emails_sent', 0)}, "
                f"emails_failed={email_results.get('emails_failed', 0)}"
            )
            
        except Exception as e:
            self.logger.error(
                f"Pipeline failed with unhandled exception for target_date={target_date}: {e}",
                exc_info=True
            )
            results["overall_success"] = False
            results["error"] = str(e)
            
        finally:
            # Clean up session if we created it
            if not session_provided and session is not None:
                try:
                    session.__exit__(None, None, None)
                except Exception:
                    pass
        
        return results


def main() -> None:
    """
    CLI entry-point for running the complete daily pipeline.
    
    Usage:
        python -m app.daily_runner
    """
    import sys
    from datetime import date
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    
    # Parse command line arguments (optional date)
    target_date = None
    if len(sys.argv) > 1:
        try:
            target_date = date.fromisoformat(sys.argv[1])
        except ValueError:
            print(f"Error: Invalid date format '{sys.argv[1]}'. Use YYYY-MM-DD format.")
            sys.exit(1)
    
    # Run pipeline
    runner = DailyPipelineRunner()
    results = runner.run_complete_pipeline(target_date=target_date)
    
    # Print summary
    print("\n" + "=" * 60)
    print("DAILY PIPELINE SUMMARY")
    print("=" * 60)
    print(f"Target Date: {results.get('target_date', 'N/A')}")
    print(f"Overall Success: {results.get('overall_success', False)}")
    print()
    
    # Scraping results
    scraping = results.get("scraping", {})
    print(f"Scraping: {'✓' if scraping.get('success') else '✗'}")
    if scraping.get("successful_scrapers"):
        print(f"  - Successful scrapers: {scraping.get('successful_scrapers')}/{scraping.get('total_scrapers', 0)}")
    
    # Content collection
    content = results.get("content_collection", {})
    print(f"Content Collection:")
    print(f"  - Videos: {content.get('videos_count', 0)}")
    print(f"  - OpenAI Articles: {content.get('openai_articles_count', 0)}")
    print(f"  - Anthropic Articles: {content.get('anthropic_articles_count', 0)}")
    print(f"  - Total Items: {content.get('total_items', 0)}")
    
    # Digest generation
    digest_gen = results.get("digest_generation", {})
    print(f"Digest Generation: {'✓' if digest_gen.get('success') else '✗'}")
    if digest_gen.get("digest_id"):
        print(f"  - Digest ID: {digest_gen.get('digest_id')}")
        print(f"  - Title: {digest_gen.get('title', 'N/A')}")
    
    # Email delivery
    email_delivery = results.get("email_delivery", {})
    print(f"Email Delivery: {'✓' if email_delivery.get('success') else '✗'}")
    print(f"  - Total Subscribers: {email_delivery.get('total_subscribers', 0)}")
    print(f"  - Emails Sent: {email_delivery.get('emails_sent', 0)}")
    print(f"  - Emails Failed: {email_delivery.get('emails_failed', 0)}")
    
    if email_delivery.get("errors"):
        print(f"  - Errors:")
        for error in email_delivery.get("errors", [])[:5]:  # Show first 5 errors
            print(f"    • {error}")
        if len(email_delivery.get("errors", [])) > 5:
            print(f"    ... and {len(email_delivery.get('errors', [])) - 5} more errors")
    
    print("=" * 60)
    
    # Exit with appropriate code
    sys.exit(0 if results.get("overall_success", False) else 1)


if __name__ == "__main__":
    main()

