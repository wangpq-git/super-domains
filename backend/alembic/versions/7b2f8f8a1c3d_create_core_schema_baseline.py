"""create core schema baseline

Revision ID: 7b2f8f8a1c3d
Revises:
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "7b2f8f8a1c3d"
down_revision = None
branch_labels = None
depends_on = None


def _json_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSON(astext_type=sa.Text())
    return sa.JSON()


def _json_default(value: str) -> sa.TextClause:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.text(f"'{value}'::json")
    return sa.text(f"'{value}'")


def _table_names() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def upgrade() -> None:
    json_type = _json_type()
    table_names = _table_names()

    if "users" not in table_names:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(length=50), nullable=False, unique=True),
            sa.Column("email", sa.String(length=100), nullable=True, unique=True),
            sa.Column("password_hash", sa.String(length=255), nullable=True),
            sa.Column("role", sa.String(length=16), nullable=False, server_default="viewer"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("auth_source", sa.String(length=16), nullable=False, server_default="ldap"),
            sa.Column("display_name", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if "platform_accounts" not in table_names:
        op.create_table(
            "platform_accounts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("account_name", sa.String(length=100), nullable=True),
            sa.Column("credentials", sa.Text(), nullable=False),
            sa.Column("config", json_type, nullable=False, server_default=_json_default("{}")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_sync_at", sa.DateTime(), nullable=True),
            sa.Column("sync_status", sa.String(length=20), nullable=False, server_default="idle"),
            sa.Column("sync_error", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("platform", "account_name", name="uq_platform_account"),
        )

    if "domains" not in table_names:
        op.create_table(
            "domains",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("platform_accounts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("domain_name", sa.String(length=255), nullable=True),
            sa.Column("tld", sa.String(length=50), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("registration_date", sa.DateTime(), nullable=True),
            sa.Column("expiry_date", sa.DateTime(), nullable=False),
            sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("whois_privacy", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("nameservers", json_type, nullable=False, server_default=_json_default("[]")),
            sa.Column("raw_data", json_type, nullable=False, server_default=_json_default("{}")),
            sa.Column("external_id", sa.String(length=100), nullable=True),
            sa.Column("last_synced_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("account_id", "domain_name", name="uq_account_domain"),
        )
        op.create_index("idx_domain_expiry", "domains", ["expiry_date"], unique=False)
        op.create_index("idx_domain_account", "domains", ["account_id"], unique=False)

    if "dns_records" not in table_names:
        op.create_table(
            "dns_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("domain_id", sa.Integer(), sa.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False),
            sa.Column("record_type", sa.String(length=20), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("ttl", sa.Integer(), nullable=False, server_default="3600"),
            sa.Column("priority", sa.Integer(), nullable=True),
            sa.Column("proxied", sa.Boolean(), nullable=True),
            sa.Column("external_id", sa.String(length=128), nullable=True),
            sa.Column("sync_status", sa.String(length=20), nullable=False, server_default="synced"),
            sa.Column("raw_data", json_type, nullable=False, server_default=_json_default("{}")),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if "alert_rules" not in table_names:
        op.create_table(
            "alert_rules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("rule_type", sa.String(length=30), nullable=False),
            sa.Column("days_before", sa.Integer(), nullable=True),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("channels", json_type, nullable=False, server_default=_json_default("[]")),
            sa.Column("recipients", json_type, nullable=False, server_default=_json_default("[]")),
            sa.Column("apply_to_all", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("specific_platforms", json_type, nullable=True),
            sa.Column("specific_domains", json_type, nullable=True),
            sa.Column("excluded_platforms", json_type, nullable=False, server_default=_json_default("[]")),
            sa.Column("severity", sa.String(length=16), nullable=False, server_default="warning"),
            sa.Column("schedule", json_type, nullable=False, server_default=_json_default('{"type":"manual"}')),
            sa.Column("last_triggered_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if "audit_logs" not in table_names:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("target_type", sa.String(length=32), nullable=True),
            sa.Column("target_id", sa.Integer(), nullable=True),
            sa.Column("detail", json_type, nullable=False, server_default=_json_default("{}")),
            sa.Column("ip_address", sa.String(length=45), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    table_names = _table_names()

    if "audit_logs" in table_names:
        op.drop_table("audit_logs")
    if "alert_rules" in table_names:
        op.drop_table("alert_rules")
    if "dns_records" in table_names:
        op.drop_table("dns_records")
    if "domains" in table_names:
        for index_name in ("idx_domain_account", "idx_domain_expiry"):
            op.drop_index(index_name, table_name="domains")
        op.drop_table("domains")
    if "platform_accounts" in table_names:
        op.drop_table("platform_accounts")
    if "users" in table_names:
        op.drop_table("users")
