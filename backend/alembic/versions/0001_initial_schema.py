"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("full_name", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("oauth_provider", sa.String(50), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token", sa.String(512), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token", "refresh_tokens", ["token"], unique=True)

    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("repo_url", sa.String(500), nullable=False),
        sa.Column("owner", sa.String(100), nullable=False),
        sa.Column("repo", sa.String(100), nullable=False),
        sa.Column("commit_sha", sa.String(64), nullable=True),
        sa.Column("assignment_brief", sa.Text(), nullable=True),
        sa.Column(
            "roast_level",
            sa.Enum("mild", "medium", "savage", name="roastlevel", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column(
            "language_style",
            sa.Enum(
                "tamil_script", "tanglish", name="languagestyle", native_enum=False, length=20
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "fetching",
                "analysing",
                "roasting",
                "done",
                "failed",
                name="submissionstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_submissions_status", "submissions", ["status"])
    op.create_index("ix_submissions_user_id_created_at", "submissions", ["user_id", "created_at"])
    op.create_index(
        "ix_submissions_owner_repo_commit_sha", "submissions", ["owner", "repo", "commit_sha"]
    )

    op.create_table(
        "repo_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "submission_id",
            sa.Integer(),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("file_tree", sa.JSON(), nullable=True),
        sa.Column("readme", sa.Text(), nullable=True),
        sa.Column("selected_files", sa.JSON(), nullable=True),
        sa.Column("total_bytes", sa.Integer(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
    )

    op.create_table(
        "analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "submission_id",
            sa.Integer(),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("strengths", sa.JSON(), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
    )
    op.create_index("ix_analyses_submission_id", "analyses", ["submission_id"])

    op.create_table(
        "roasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "submission_id",
            sa.Integer(),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("roast_text", sa.Text(), nullable=False),
        sa.Column("one_liner", sa.String(300), nullable=True),
        sa.Column("fixes", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("share_slug", sa.String(64), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_roasts_submission_id", "roasts", ["submission_id"])
    op.create_index("ix_roasts_share_slug", "roasts", ["share_slug"], unique=True)

    op.create_table(
        "usage_counters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("roasts_used", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "date", name="uq_usage_counters_user_id_date"),
    )
    op.create_index("ix_usage_counters_user_id", "usage_counters", ["user_id"])

    op.create_table(
        "credit_balances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("credits", sa.Integer(), nullable=False),
        *_timestamps(),
    )


def downgrade() -> None:
    op.drop_table("credit_balances")
    op.drop_table("usage_counters")
    op.drop_table("roasts")
    op.drop_table("analyses")
    op.drop_table("repo_snapshots")
    op.drop_table("submissions")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
