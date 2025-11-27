"""
User profile settings and helper functions for personalization.

This module defines a high-level user profile model (`UserProfileSettings`)
used across the application and helpers to load/save profiles from the
database `UserProfile` model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Sequence

from sqlalchemy.orm import Session

from app.database.models import UserProfile


@dataclass
class UserProfileSettings:
    """
    High-level user profile settings used for personalization.

    This is a lightweight dataclass used throughout the application and by
    AI agents (e.g., CuratorAgent, EmailAgent) instead of working directly
    with the SQLAlchemy model.
    """

    name: str
    email: str
    topics: List[str] = field(default_factory=lambda: ["ai", "ml"])
    providers: List[str] = field(
        default_factory=lambda: ["openai", "google", "anthropic"]
    )
    formats: List[str] = field(default_factory=lambda: ["video", "article"])
    expertise_level: str = "intermediate"  # 'beginner' | 'intermediate' | 'expert'
    receive_daily_digest: bool = True
    timezone: str | None = "UTC"

    def to_db_model(self, existing: UserProfile | None = None) -> UserProfile:
        """
        Convert settings to a UserProfile SQLAlchemy model instance.

        Args:
            existing: Optional existing UserProfile to update. If not provided,
                      a new instance is created.
        """
        instance = existing or UserProfile(
            name=self.name,
            email=self.email,
            preferred_topics="[]",
            preferred_providers="[]",
            preferred_formats="[]",
            expertise_level=self.expertise_level,
            receive_daily_digest=self.receive_daily_digest,
            timezone=self.timezone,
        )

        instance.name = self.name
        instance.email = self.email
        instance.preferred_topics = json.dumps(self.topics)
        instance.preferred_providers = json.dumps(self.providers)
        instance.preferred_formats = json.dumps(self.formats)
        instance.expertise_level = self.expertise_level
        instance.receive_daily_digest = self.receive_daily_digest
        instance.timezone = self.timezone

        return instance

    @classmethod
    def from_db_model(cls, model: UserProfile) -> "UserProfileSettings":
        """Create settings from a UserProfile SQLAlchemy model."""

        def _parse_list(value: str | None) -> List[str]:
            if not value:
                return []
            try:
                data = json.loads(value)
                if isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
                    return [str(x) for x in data]
            except json.JSONDecodeError:
                return []
            return []

        return cls(
            name=model.name,
            email=model.email,
            topics=_parse_list(model.preferred_topics),
            providers=_parse_list(model.preferred_providers),
            formats=_parse_list(model.preferred_formats),
            expertise_level=model.expertise_level,
            receive_daily_digest=model.receive_daily_digest,
            timezone=model.timezone,
        )


def get_default_user_profile(
    email: str | None = None,
    name: str | None = None,
) -> UserProfileSettings:
    """
    Create a default user profile settings object.

    Args:
        email: Optional email to set on the profile.
        name: Optional name to set on the profile.
    """
    return UserProfileSettings(
        name=name or "AI News Reader",
        email=email or "user@example.com",
    )


def load_user_profile(session: Session, email: str) -> UserProfileSettings:
    """
    Load a user profile from the database by email.

    If the profile does not exist, a new one is created with default settings
    using the provided email.
    """
    profile = (
        session.query(UserProfile)
        .filter(UserProfile.email == email)
        .order_by(UserProfile.id.asc())
        .first()
    )

    if profile is None:
        default_settings = get_default_user_profile(email=email)
        profile = default_settings.to_db_model()
        session.add(profile)
        session.commit()
        session.refresh(profile)
        return default_settings

    return UserProfileSettings.from_db_model(profile)


def save_user_profile(session: Session, settings: UserProfileSettings) -> UserProfile:
    """
    Save (upsert) a user profile to the database.

    If a profile with the same email exists, it is updated. Otherwise, a new
    record is created.
    """
    profile = (
        session.query(UserProfile)
        .filter(UserProfile.email == settings.email)
        .order_by(UserProfile.id.asc())
        .first()
    )

    profile = settings.to_db_model(existing=profile)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


