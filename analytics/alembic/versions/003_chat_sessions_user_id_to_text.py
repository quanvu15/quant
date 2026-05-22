"""Change chat_sessions.user_id from UUID to Text.

QuantDinger uses integer user IDs (auto-increment from qd_users.id).
Analytics now stores user_id as str(int) for simplicity — no UUID conversion needed.

Revision ID: 003
Revises: 002
Create Date: 2026-05-21 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "analytics"


def upgrade() -> None:
    # Change chat_sessions.user_id from UUID to Text
    # Existing UUID values are cast to their text representation automatically.
    op.alter_column(
        "chat_sessions",
        "user_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        type_=sa.Text(),
        existing_nullable=False,
        schema=SCHEMA,
        postgresql_using="user_id::text",
    )


def downgrade() -> None:
    # Revert: Text back to UUID (only works if all values are valid UUIDs)
    op.alter_column(
        "chat_sessions",
        "user_id",
        existing_type=sa.Text(),
        type_=sa.dialects.postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        schema=SCHEMA,
        postgresql_using="user_id::uuid",
    )
