"""add missing alert rule scheduling fields

Revision ID: 10c51a4fa5af
Revises:
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "10c51a4fa5af"
down_revision = "7b2f8f8a1c3d"
branch_labels = None
depends_on = None


def _column_names(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "alert_rules"):
        return
    column_names = _column_names(bind, "alert_rules")

    if "excluded_platforms" not in column_names:
        op.add_column(
            "alert_rules",
            sa.Column(
                "excluded_platforms",
                postgresql.JSON(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::json"),
            ),
        )

    if "severity" not in column_names:
        op.add_column(
            "alert_rules",
            sa.Column("severity", sa.String(length=16), nullable=False, server_default="warning"),
        )

    if "schedule" not in column_names:
        op.add_column(
            "alert_rules",
            sa.Column(
                "schedule",
                postgresql.JSON(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{\"type\":\"manual\"}'::json"),
            ),
        )

    if "last_triggered_at" not in column_names:
        op.add_column("alert_rules", sa.Column("last_triggered_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "alert_rules"):
        return
    column_names = _column_names(bind, "alert_rules")

    if "last_triggered_at" in column_names:
        op.drop_column("alert_rules", "last_triggered_at")

    if "schedule" in column_names:
        op.drop_column("alert_rules", "schedule")

    if "severity" in column_names:
        op.drop_column("alert_rules", "severity")

    if "excluded_platforms" in column_names:
        op.drop_column("alert_rules", "excluded_platforms")
