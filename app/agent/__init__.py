"""
AI agent system for content processing.

This package provides AI agents for processing collected content to create
personalized digests, including summarization, curation, and email composition.
"""

from app.agent.base import BaseAgent
from app.agent.curator import CuratorAgent, CuratedItem, UserPreferences
from app.agent.digest import DigestAgent
from app.agent.email import EmailAgent, EmailContent

__all__ = [
    "BaseAgent",
    "DigestAgent",
    "CuratorAgent",
    "CuratedItem",
    "UserPreferences",
    "EmailAgent",
    "EmailContent",
]

