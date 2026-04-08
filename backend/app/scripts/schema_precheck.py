"""Schema precheck for Alembic-first rollout.

Usage:
    python app/scripts/schema_precheck.py

The script inspects the current database schema and prints a rollout suggestion:
- fresh database -> run `alembic upgrade head`
- legacy create_all database without alembic_version -> consider `alembic stamp head`
- partially migrated database -> inspect manually before proceeding
- migrated database -> optionally run `alembic upgrade head`
"""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402

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

EXPECTED_TABLES = CORE_TABLES | APPROVAL_TABLES
HEAD_REVISION = "4f9d3c1b7a21"
BASELINE_REVISION = "7b2f8f8a1c3d"


def _print_header(title: str) -> None:
    print(f"\n== {title} ==")


async def main() -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    async with engine.connect() as conn:
        data = await conn.run_sync(_collect_schema_state)

    await engine.dispose()

    _print_header("Database")
    print(f"DATABASE_URL={settings.DATABASE_URL}")

    _print_header("Detected tables")
    print(", ".join(sorted(data["tables"])) or "<no tables>")

    _print_header("Coverage")
    missing = sorted(EXPECTED_TABLES - data["tables"])
    extra = sorted(data["tables"] - EXPECTED_TABLES - {"alembic_version"})
    print(f"core_tables_present={sorted(CORE_TABLES & data['tables'])}")
    print(f"approval_tables_present={sorted(APPROVAL_TABLES & data['tables'])}")
    print(f"missing_expected_tables={missing}")
    print(f"extra_tables={extra}")

    _print_header("Alembic")
    print(f"alembic_version_present={data['has_alembic_version']}")
    print(f"current_revision={data['revision'] or '<none>'}")
    print(f"head_revision={HEAD_REVISION}")

    _print_header("Recommendation")
    for line in _recommend(data):
        print(line)



def _collect_schema_state(sync_conn):
    inspector = inspect(sync_conn)
    tables = set(inspector.get_table_names())
    has_alembic_version = "alembic_version" in tables
    revision = None

    if has_alembic_version:
        try:
            revision = sync_conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        except Exception:
            revision = "<unreadable>"

    return {
        "tables": tables,
        "has_alembic_version": has_alembic_version,
        "revision": revision,
    }



def _recommend(data: dict) -> list[str]:
    tables = data["tables"]
    revision = data["revision"]
    has_alembic_version = data["has_alembic_version"]
    expected_without_version = EXPECTED_TABLES & tables
    missing_expected = EXPECTED_TABLES - tables

    if not expected_without_version and not has_alembic_version:
        return [
            "status=fresh_database",
            "suggestion=run `alembic -c alembic.ini upgrade head`",
            f"expected_chain={BASELINE_REVISION} -> 10c51a4fa5af -> {HEAD_REVISION}",
        ]

    if has_alembic_version and revision == HEAD_REVISION:
        return [
            "status=fully_migrated",
            "suggestion=database already matches current migration head",
            "next_action=run `alembic -c alembic.ini upgrade head` during deploy as a no-op safety step",
        ]

    if has_alembic_version and revision and revision != HEAD_REVISION:
        return [
            "status=partially_migrated",
            f"suggestion=current revision is {revision}; review changelog then run `alembic -c alembic.ini upgrade head`",
            f"missing_expected_tables={sorted(missing_expected)}",
        ]

    if not has_alembic_version and not missing_expected:
        return [
            "status=legacy_create_all_database",
            "suggestion=after verifying schema matches current models, consider `alembic -c alembic.ini stamp head`",
            "warning=do not stamp blindly if schema drift exists; compare critical tables and columns first",
        ]

    if not has_alembic_version and expected_without_version:
        return [
            "status=partially_bootstrapped_database",
            "suggestion=manual review required before migration",
            "warning=database has some expected tables but not a complete schema and no alembic_version",
            f"missing_expected_tables={sorted(missing_expected)}",
        ]

    return [
        "status=unknown",
        "suggestion=inspect schema manually before migration",
    ]


if __name__ == "__main__":
    asyncio.run(main())
