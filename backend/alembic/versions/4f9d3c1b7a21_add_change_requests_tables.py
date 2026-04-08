"""add change requests tables

Revision ID: 4f9d3c1b7a21
Revises: 10c51a4fa5af
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "4f9d3c1b7a21"
down_revision = "10c51a4fa5af"
branch_labels = None
depends_on = None


def _json_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSON(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    json_type = _json_type()

    op.create_table(
        "change_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_no", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="api"),
        sa.Column("requester_user_id", sa.Integer(), nullable=False),
        sa.Column("requester_name", sa.String(length=100), nullable=True),
        sa.Column("operation_type", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("domain_id", sa.Integer(), nullable=True),
        sa.Column("payload", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("before_snapshot", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("after_snapshot", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("risk_level", sa.String(length=16), nullable=False, server_default="high"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending_approval"),
        sa.Column("approval_channel", sa.String(length=16), nullable=False, server_default="feishu"),
        sa.Column("approver_user_id", sa.Integer(), nullable=True),
        sa.Column("approver_name", sa.String(length=100), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        sa.Column("execution_result", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_change_requests_request_no", "change_requests", ["request_no"], unique=True)
    op.create_index("ix_change_requests_status", "change_requests", ["status"], unique=False)
    op.create_index("ix_change_requests_requester_user_id", "change_requests", ["requester_user_id"], unique=False)
    op.create_index("ix_change_requests_domain_id", "change_requests", ["domain_id"], unique=False)
    op.create_index("ix_change_requests_idempotency_key", "change_requests", ["idempotency_key"], unique=False)
    op.create_index("ix_change_requests_operation_type", "change_requests", ["operation_type"], unique=False)

    op.create_table(
        "change_request_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("change_request_id", sa.Integer(), sa.ForeignKey("change_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("detail", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_change_request_events_change_request_id", "change_request_events", ["change_request_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_change_request_events_change_request_id", table_name="change_request_events")
    op.drop_table("change_request_events")

    op.drop_index("ix_change_requests_operation_type", table_name="change_requests")
    op.drop_index("ix_change_requests_idempotency_key", table_name="change_requests")
    op.drop_index("ix_change_requests_domain_id", table_name="change_requests")
    op.drop_index("ix_change_requests_requester_user_id", table_name="change_requests")
    op.drop_index("ix_change_requests_status", table_name="change_requests")
    op.drop_index("ix_change_requests_request_no", table_name="change_requests")
    op.drop_table("change_requests")
