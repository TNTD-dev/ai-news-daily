"""
Service layer for business logic operations.

This package provides services that coordinate between agents, repositories,
and external systems (e.g., email delivery).
"""

from app.services.email_service import EmailService

__all__ = [
    "EmailService",
]

