"""User profile system for personalization.

This package exposes high-level user profile settings and helper functions
for loading and saving profiles backed by the database.
"""

from .user_profile import (
    UserProfileSettings,
    get_default_user_profile,
    load_user_profile,
    save_user_profile,
)

__all__ = [
    "UserProfileSettings",
    "get_default_user_profile",
    "load_user_profile",
    "save_user_profile",
]
