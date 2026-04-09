"""add system settings table

Revision ID: c2e9d5a4b301
Revises: 4f9d3c1b7a21
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa


revision = "c2e9d5a4b301"
down_revision = "4f9d3c1b7a21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("value_type", sa.String(length=20), nullable=False, server_default="string"),
        sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("restart_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_system_settings_key", "system_settings", ["key"], unique=True)
    op.create_index("ix_system_settings_category", "system_settings", ["category"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_system_settings_category", table_name="system_settings")
    op.drop_index("ix_system_settings_key", table_name="system_settings")
    op.drop_table("system_settings")
