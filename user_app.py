"""
User onboarding Streamlit app for AI News Daily.

This app introduces AI News Daily to end-users and lets them
enter their personalization preferences, which are then stored
in the `user_profiles` database table.
"""

import json
import re
from typing import List
import threading
import time
from datetime import datetime

import streamlit as st
from sqlalchemy.orm import Session

from app.database.models import Base, UserProfile
from app.database.repositories import UserProfileRepository
from app.database.session import get_session, init_engine
from app.profiles.user_profile import (
    UserProfileSettings,
    save_user_profile,
)

def run_daily_digest_job():
    """
    Background thread to run daily digest at a specified time.
    
    This function runs in a daemon thread and checks every hour if it's time
    to run the daily digest pipeline. The default time is 7 AM UTC.
    
    Note: This is a simple scheduler. For production, consider using a proper
    task scheduler like APScheduler or Railway's cron jobs.
    """
    import logging
    
    logger = logging.getLogger(__name__)
    last_run_date = None
    
    while True:
        try:
            current_time = datetime.now()
            current_hour = current_time.hour
            current_date = current_time.date()
            
            # Run around 7 AM UTC (adjust to your needs)
            # Only run once per day
            if current_hour == 7 and current_date != last_run_date:
                logger.info(f"Starting daily digest job at {current_time}")
                print(f"[Scheduler] Running daily digest at {current_time}")
                
                try:
                    from app.daily_runner import DailyPipelineRunner
                    runner = DailyPipelineRunner()
                    result = runner.run_complete_pipeline()
                    
                    last_run_date = current_date
                    logger.info(f"Daily digest job completed: {result}")
                    print(f"[Scheduler] Daily job completed: {result}")
                    
                except Exception as e:
                    logger.error(f"Error running daily digest: {e}", exc_info=True)
                    print(f"[Scheduler] Error running daily digest: {e}")
            
            # Sleep for an hour before checking again
            time.sleep(3600)
            
        except Exception as e:
            logger.error(f"Unexpected error in scheduler: {e}", exc_info=True)
            print(f"[Scheduler] Unexpected error: {e}")
            # Sleep before retrying to avoid tight error loop
            time.sleep(3600)
# Page configuration
st.set_page_config(
    page_title="AI News Daily – Personalized AI Digest",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Custom CSS for beautiful, professional UI (high-contrast)
st.markdown(
    """
    <style>
    .main-hero {
        padding: 2.5rem 2rem 1.5rem 2rem;
        border-radius: 1rem;
        background: linear-gradient(135deg, #1d4ed8, #1f77b4);
        color: #ffffff;
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.18);
        margin-bottom: 2rem;
    }
    .main-hero h1 {
        font-size: 2.7rem;
        margin-bottom: 0.5rem;
        font-weight: 800;
    }
    .main-hero p {
        font-size: 1.1rem;
        opacity: 0.95;
    }
    .tagline {
        letter-spacing: 0.08em;
        text-transform: uppercase;
        font-size: 0.8rem;
        opacity: 0.95;
        margin-bottom: 0.5rem;
    }
    .pill {
        display: inline-block;
        padding: 0.25rem 0.7rem;
        border-radius: 999px;
        background: #f97316;
        color: #111827;
        font-size: 0.75rem;
        margin-right: 0.4rem;
        font-weight: 600;
    }
    .feature-card {
        background: #ffffff;
        border-radius: 0.9rem;
        padding: 1.2rem 1.3rem;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.08);
        border: 1px solid rgba(148, 163, 184, 0.3);
        height: 100%;
    }
    .feature-icon {
        font-size: 1.7rem;
        margin-bottom: 0.4rem;
    }
    .feature-title {
        font-weight: 700;
        margin-bottom: 0.3rem;
        font-size: 1.0rem;
        color: #0f172a;
    }
    .feature-desc {
        font-size: 0.9rem;
        color: #4b5563;
    }
    .section-title {
        font-size: 1.4rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
        color: #f9fafb;
    }
    .section-subtitle {
        font-size: 0.95rem;
        color: #e5e7eb;
        margin-bottom: 1.3rem;
    }
    .summary-card {
        background: #0f172a;
        border-radius: 0.9rem;
        padding: 1.2rem 1.3rem;
        border: 1px solid #1d4ed8;
        color: #e5e7eb;
    }
    .summary-badge {
        display: inline-block;
        padding: 0.18rem 0.6rem;
        border-radius: 999px;
        background: #1d4ed8;
        color: white;
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 0.4rem;
    }
    .stButton>button {
        border-radius: 999px;
        padding: 0.6rem 1.5rem;
        font-weight: 600;
        border: none;
        box-shadow: 0 8px 20px rgba(37, 99, 235, 0.35);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def init_database_tables() -> None:
    """
    Initialize all database tables if they don't exist.
    
    This function imports all models to ensure their metadata is registered,
    then creates all tables (including association tables) in the database.
    Tables that already exist will be skipped automatically by SQLAlchemy.
    
    Tables created:
    - youtube_videos
    - openai_articles
    - anthropic_articles
    - digests
    - user_profiles
    - digest_youtube_videos (association table)
    - digest_openai_articles (association table)
    - digest_anthropic_articles (association table)
    """
    try:
        engine = init_engine()
        
        # Import all models to register their metadata with Base
        # This ensures all tables (including association tables) are included
        # Association tables are automatically registered when models are imported
        from app.database.models import (
            AnthropicArticle,
            Digest,
            OpenAIArticle,
            UserProfile,
            YouTubeVideo,
        )
        
        # Ensure all models are imported (this registers them with Base.metadata)
        # Association tables (digest_youtube_videos, digest_openai_articles, 
        # digest_anthropic_articles) are automatically included when models are imported
        _ = (AnthropicArticle, Digest, OpenAIArticle, UserProfile, YouTubeVideo)
        
        # Create all tables (this is idempotent - existing tables are skipped)
        # checkfirst=True ensures SQLAlchemy checks if tables exist before creating
        Base.metadata.create_all(engine, checkfirst=True)
        
        # Log success (only in non-Streamlit contexts to avoid errors)
        try:
            import logging
            logger = logging.getLogger(__name__)
            logger.info("Database tables initialized successfully")
        except Exception:
            pass  # Ignore logging errors in Streamlit context
            
    except Exception as e:
        error_msg = str(e).lower()
        # Only show error if it's not a "table already exists" type error
        if "already exists" not in error_msg and "duplicate" not in error_msg:
            # Use print for Railway logs, st.error for Streamlit UI
            print(f"❌ Error while initializing database: {str(e)}")
            try:
                st.error(f"❌ Error while initializing database: {str(e)}")
            except Exception:
                pass  # If Streamlit context is not available, just print


def get_db_session():
    """Get database session context manager."""
    return get_session()


def validate_email(email: str) -> bool:
    """Validate email format (same regex as admin streamlit app)."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def render_hero_section() -> None:
    """Render the main hero section introducing AI News Daily."""
    with st.container():
        st.markdown(
            """
            <div class="main-hero">
                <div class="tagline">AI NEWS DAILY • PERSONALIZED DIGEST</div>
                <h1>Stay up to date with AI – in a feed tailored just for you.</h1>
                <p>
                    AI News Daily automatically collects, analyzes and summarizes
                    the most important AI updates from YouTube, OpenAI, Anthropic
                    and other leading sources – then sends you a concise,
                    easy-to-read digest every day.
                </p>
                <div style="margin-top: 0.8rem;">
                    <span class="pill">Personalized to your interests</span>
                    <span class="pill">Daily email digest</span>
                    <span class="pill">Save hours of scrolling</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_features_section() -> None:
    """Render feature cards describing the system capabilities."""
    st.markdown("")
    st.markdown('<div class="section-title">Highlights</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subtitle">Designed for developers, researchers, product people '
        "and anyone who wants to keep up with AI without getting overwhelmed.</div>",
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-title">Multi-source aggregation</div>
                <div class="feature-desc">
                    Collects content from YouTube, OpenAI, Anthropic
                    and other top AI sources – into a single digest.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-title">Deep personalization</div>
                <div class="feature-desc">
                    Choose topics, providers, formats and expertise level
                    so you only get what truly matters to you.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            """
            <div class="feature-card">
                <div class="feature-title">Time-saving summaries</div>
                <div class="feature-desc">
                    Digest-style summaries focus on key insights so you
                    can stay up to date in just a few minutes a day.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _topics_options() -> List[str]:
    return [
        "ai",
        "machine learning",
        "deep learning",
        "nlp",
        "computer vision",
        "robotics",
        "neural networks",
        "reinforcement learning",
        "data science",
        "python",
    ]


def _providers_options() -> List[str]:
    return ["openai", "google", "anthropic", "meta", "microsoft"]


def _formats_options() -> List[str]:
    return ["video", "article", "podcast"]


def _timezone_options() -> List[str]:
    return [
        "UTC",
        "Asia/Ho_Chi_Minh",
        "America/New_York",
        "America/Los_Angeles",
        "Europe/London",
        "Asia/Tokyo",
    ]


def render_user_form() -> None:
    """Render the onboarding form and handle persistence."""
    st.markdown("---")
    st.markdown(
        '<div class="section-title">Personalize your AI digest</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-subtitle">Tell us a bit about yourself so we can tailor the content to your interests and level. You can change these settings any time.</div>',
        unsafe_allow_html=True,
    )

    with st.form("user_onboarding_form", clear_on_submit=False):
        st.subheader("Basic information")
        name = st.text_input("Your name *", placeholder="e.g. Alex Nguyen")
        email = st.text_input("Email *", placeholder="e.g. you@company.com")
        st.caption("We use this email to send your daily digest. No spam, unsubscribe any time.")

        st.markdown("---")
        st.subheader("Content preferences")

        topics = st.multiselect(
            "Topics you care about",
            _topics_options(),
            default=["ai", "machine learning"],
            help="Choose the AI areas you want to follow regularly.",
        )

        providers = st.multiselect(
            "Preferred content providers",
            _providers_options(),
            default=["openai", "google", "anthropic"],
            help="Pick the companies / organizations you trust the most.",
        )

        formats = st.multiselect(
            "Preferred content formats",
            _formats_options(),
            default=["video", "article"],
            help="Select how you prefer to consume content.",
        )

        st.markdown("---")
        st.subheader("Advanced settings")

        col1, col2 = st.columns(2)

        with col1:
            expertise_level = st.selectbox(
                "Your experience level with AI",
                ["beginner", "intermediate", "expert"],
                index=1,
                help="Beginner: just getting started • Intermediate: some background • Expert: work deeply with AI.",
            )

        with col2:
            timezone = st.selectbox(
                "Time zone for sending the digest",
                _timezone_options(),
                index=1,
                help="We use this to choose a good time of day to send your email.",
            )

        receive_digest = st.checkbox(
            "I want to receive the AI News Daily email every day",
            value=True,
        )

        submitted = st.form_submit_button(
            "🚀 Start receiving my personalized AI digest",
            type="primary",
            use_container_width=True,
        )

        if not submitted:
            return

        # Validation
        if not name or not name.strip():
            st.error("❌ Please enter your name.")
            return

        if not email or not email.strip():
            st.error("❌ Please enter your email.")
            return

        if not validate_email(email.strip()):
            st.error("❌ This email address looks invalid. Please check again.")
            return

        try:
            session_gen = get_db_session()
            with session_gen as session:
                _persist_user_profile(
                    session=session,
                    name=name.strip(),
                    email=email.strip(),
                    topics=topics or ["ai", "ml"],
                    providers=providers or ["openai", "google", "anthropic"],
                    formats=formats or ["video", "article"],
                    expertise_level=expertise_level,
                    receive_daily_digest=receive_digest,
                    timezone=timezone,
                )
        except Exception as e:
            st.error(f"❌ Something went wrong while saving your preferences: {str(e)}")
            return


def _persist_user_profile(
    session: Session,
    name: str,
    email: str,
    topics: List[str],
    providers: List[str],
    formats: List[str],
    expertise_level: str,
    receive_daily_digest: bool,
    timezone: str | None,
) -> None:
    """
    Persist user profile into database, reusing the same pattern as admin app.

    If a profile with the same email exists, it will be updated.
    """
    # Check existing email
    repo = UserProfileRepository(session)
    existing = repo.get_by_email(email)
    if existing:
        st.error(
            f"❌ The email address **{email}** is already registered. "
            "If this is you, please reuse this email or choose a different one."
        )
        return

    profile_settings = UserProfileSettings(
        name=name,
        email=email,
        topics=topics,
        providers=providers,
        formats=formats,
        expertise_level=expertise_level,
        receive_daily_digest=receive_daily_digest,
        timezone=timezone,
    )

    saved_profile = save_user_profile(session, profile_settings)

    st.success("✅ Your profile has been saved successfully!")
    st.balloons()
    _render_post_submit_summary(saved_profile)


def _render_post_submit_summary(user: UserProfile) -> None:
    """Render a nice summary card after successful onboarding."""
    try:
        topics = json.loads(user.preferred_topics or "[]")
        providers = json.loads(user.preferred_providers or "[]")
        formats = json.loads(user.preferred_formats or "[]")
    except Exception:
        topics, providers, formats = [], [], []

    st.markdown("")
    st.markdown(
        """
        <div class="summary-card">
            <div class="summary-badge">Profile created</div>
            <h3 style="margin: 0 0 0.5rem 0;">Thanks for joining AI News Daily!</h3>
            <p style="margin: 0 0 0.5rem 0; font-size: 0.95rem;">
                We'll use the preferences below to personalize the AI digest we send to you.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_main, col_side = st.columns([2, 1])

    with col_main:
        st.markdown(f"**Name:** {user.name}")
        st.markdown(f"**Email:** {user.email}")
        st.markdown(
            f"**Topics:** {', '.join(topics) if topics else 'Default (ai, ml)'}"
        )
        st.markdown(
            f"**Providers:** {', '.join(providers) if providers else 'Default'}"
        )
        st.markdown(
            f"**Formats:** {', '.join(formats) if formats else 'Default'}"
        )
        st.markdown(
            f"**Expertise level:** {user.expertise_level.title()}"
        )
        digest_status = (
            "✅ You will receive a daily digest."
            if user.receive_daily_digest
            else "⏸ Daily digest is currently turned off for your profile."
        )
        st.markdown(f"**Digest status:** {digest_status}")
        st.markdown(f"**Time zone:** {user.timezone or 'Not set'}")

    with col_side:
        st.info(
            "⏰ We typically send the digest near the start of your day in the selected "
            "time zone. If you don't see it, please check your spam or promotions folders."
        )


def main() -> None:
    """Main entry for the user onboarding app."""
    # Initialize database tables first (idempotent - safe to call multiple times)
    init_database_tables()
    
    # Start the daily digest scheduler in a background thread
    # This runs the daily pipeline at the specified time (7 AM UTC by default)
    scheduler_thread = threading.Thread(target=run_daily_digest_job, daemon=True)
    scheduler_thread.start()
    
    # Render the Streamlit UI
    render_hero_section()
    render_features_section()
    render_user_form()


if __name__ == "__main__":
    main()


