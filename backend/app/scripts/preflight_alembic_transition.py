import argparse
import asyncio
import json
import os
from dataclasses import dataclass, asdict
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

CURRENT_HEAD = "4f9d3c1b7a21"
BASELINE_REVISION = "7b2f8f8a1c3d"
CORE_TABLES = {
    "users",
    "platform_accounts",
    "domains",
    "dns_records",
    "alert_rules",
    "audit_logs",
}
APPROVAL_TABLES = {
    "change_requests",
    "change_request_events",
}
ALERT_RULE_EXPECTED_COLUMNS = {
    "excluded_platforms",
    "severity",
    "schedule",
    "last_triggered_at",
}


@dataclass
class Report:
    database_url: str
    dialect: str
    table_names: list[str]
    has_alembic_version: bool
    alembic_versions: list[str]
    missing_core_tables: list[str]
    missing_approval_tables: list[str]
    missing_alert_rule_columns: list[str]
    recommendation: str
    rationale: list[str]
    suggested_commands: list[str]


async def inspect_async_db(database_url: str) -> dict[str, Any]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            def _inspect(sync_conn):
                inspector = sa.inspect(sync_conn)
                table_names = set(inspector.get_table_names())
                columns = {}
                if "alert_rules" in table_names:
                    columns["alert_rules"] = {col["name"] for col in inspector.get_columns("alert_rules")}
                return table_names, columns

            table_names, columns = await conn.run_sync(_inspect)
            versions: list[str] = []
            if "alembic_version" in table_names:
                rows = await conn.execute(text("select version_num from alembic_version"))
                versions = [row[0] for row in rows.fetchall()]
            return {
                "dialect": engine.dialect.name,
                "table_names": table_names,
                "columns": columns,
                "alembic_versions": versions,
            }
    finally:
        await engine.dispose()


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


async def inspect_database(database_url: str) -> dict[str, Any]:
    database_url = normalize_database_url(database_url)
    url = make_url(database_url)
    if "+asyncpg" in url.drivername or "+aiosqlite" in url.drivername:
        return await inspect_async_db(database_url)

    engine = sa.create_engine(database_url)
    try:
        inspector = sa.inspect(engine)
        table_names = set(inspector.get_table_names())
        columns = {}
        if "alert_rules" in table_names:
            columns["alert_rules"] = {col["name"] for col in inspector.get_columns("alert_rules")}
        versions: list[str] = []
        if "alembic_version" in table_names:
            with engine.connect() as conn:
                rows = conn.execute(text("select version_num from alembic_version"))
                versions = [row[0] for row in rows.fetchall()]
        return {
            "dialect": engine.dialect.name,
            "table_names": table_names,
            "columns": columns,
            "alembic_versions": versions,
        }
    finally:
        engine.dispose()


def build_recommendation(database_url: str, inspected: dict[str, Any]) -> Report:
    table_names = inspected["table_names"]
    versions = inspected["alembic_versions"]
    alert_rule_columns = inspected["columns"].get("alert_rules", set())
    missing_core_tables = sorted(CORE_TABLES - table_names)
    missing_approval_tables = sorted(APPROVAL_TABLES - table_names)
    missing_alert_rule_columns = sorted(ALERT_RULE_EXPECTED_COLUMNS - alert_rule_columns) if "alert_rules" in table_names else sorted(ALERT_RULE_EXPECTED_COLUMNS)

    rationale: list[str] = []
    commands: list[str] = []

    if not table_names or table_names == {"alembic_version"}:
        recommendation = "fresh_database_upgrade"
        rationale.append("Database is empty or only contains alembic metadata.")
        commands.append("cd backend && alembic -c alembic.ini upgrade head")
    elif versions:
        if CURRENT_HEAD in versions:
            recommendation = "already_on_head"
            rationale.append(f"Alembic version already includes current head {CURRENT_HEAD}.")
        else:
            recommendation = "managed_database_upgrade"
            rationale.append(f"Database is Alembic-managed but not on current head: {versions}.")
            commands.append("cd backend && alembic -c alembic.ini upgrade head")
    else:
        if not missing_core_tables and not missing_approval_tables and not missing_alert_rule_columns:
            recommendation = "legacy_schema_stamp_head"
            rationale.append("Database schema looks complete but alembic_version is missing.")
            rationale.append("This usually indicates a legacy create_all-managed environment.")
            commands.append(f"cd backend && alembic -c alembic.ini stamp {CURRENT_HEAD}")
        elif not missing_core_tables and missing_approval_tables:
            recommendation = "legacy_schema_stamp_baseline_then_upgrade"
            rationale.append("Core legacy tables exist, but approval tables are missing and alembic_version is absent.")
            rationale.append("Stamp to baseline first, then run migrations for alert patch and approval tables.")
            commands.append(f"cd backend && alembic -c alembic.ini stamp {BASELINE_REVISION}")
            commands.append("cd backend && alembic -c alembic.ini upgrade head")
        else:
            recommendation = "manual_review_required"
            rationale.append("Database schema is partially populated or diverges from expected baseline.")
            rationale.append("Automatic stamp/upgrade could be unsafe without manual inspection.")

    return Report(
        database_url=database_url,
        dialect=inspected["dialect"],
        table_names=sorted(table_names),
        has_alembic_version=bool(versions),
        alembic_versions=versions,
        missing_core_tables=missing_core_tables,
        missing_approval_tables=missing_approval_tables,
        missing_alert_rule_columns=missing_alert_rule_columns,
        recommendation=recommendation,
        rationale=rationale,
        suggested_commands=commands,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight checker for migrating legacy environments to Alembic-first schema management.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""), help="Database URL. Defaults to env DATABASE_URL.")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON.")
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL is required via --database-url or environment variable")

    inspected = await inspect_database(args.database_url)
    report = build_recommendation(args.database_url, inspected)

    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
        return

    print("Alembic Transition Preflight")
    print(f"- dialect: {report.dialect}")
    print(f"- table_count: {len(report.table_names)}")
    print(f"- alembic_versions: {report.alembic_versions or ['<none>']}")
    print(f"- recommendation: {report.recommendation}")
    if report.missing_core_tables:
        print(f"- missing_core_tables: {', '.join(report.missing_core_tables)}")
    if report.missing_approval_tables:
        print(f"- missing_approval_tables: {', '.join(report.missing_approval_tables)}")
    if report.missing_alert_rule_columns:
        print(f"- missing_alert_rule_columns: {', '.join(report.missing_alert_rule_columns)}")
    if report.rationale:
        print("- rationale:")
        for item in report.rationale:
            print(f"  - {item}")
    if report.suggested_commands:
        print("- suggested_commands:")
        for cmd in report.suggested_commands:
            print(f"  - {cmd}")


if __name__ == "__main__":
    asyncio.run(main())
