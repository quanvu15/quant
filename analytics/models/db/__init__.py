"""
SQLAlchemy ORM models for the `analytics` PostgreSQL schema.

All tables live in schema="analytics" as required by Requirement 0.5.
"""

from models.db.base import Base, metadata
from models.db.news import NewsSource, NewsArticle
from models.db.chat import ChatSession, ChatMessage
from models.db.agent import AgentRun
from models.db.audit import AuditLog

__all__ = [
    "Base",
    "metadata",
    "NewsSource",
    "NewsArticle",
    "ChatSession",
    "ChatMessage",
    "AgentRun",
    "AuditLog",
]
