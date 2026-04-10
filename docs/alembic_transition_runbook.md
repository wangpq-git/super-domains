# Alembic Transition Runbook

> Updated: 2026-04-08
> Goal: move legacy environments from runtime `create_all()` toward Alembic-first schema management safely

## 1. When to use this runbook

Use this document if your environment was created before the new baseline migration and you are not sure whether to run:
- `alembic upgrade head`
- `alembic stamp <revision>`
- or a manual review first

Typical legacy signs:
- database tables already exist
- `alembic_version` table is missing
- environment previously relied on `Base.metadata.create_all()`

## 2. Pre-check script

Run the preflight checker first:

```bash
cd backend
DATABASE_URL='<your_database_url>' python -m app.scripts.preflight_alembic_transition
```

JSON output is also supported:

```bash
cd backend
DATABASE_URL='<your_database_url>' python -m app.scripts.preflight_alembic_transition --json
```

The script checks at least:
- core tables: `users`, `platform_accounts`, `domains`, `dns_records`, `alert_rules`, `audit_logs`
- approval tables: `change_requests`, `change_request_events`
- `alert_rules` patch columns required by later revisions
- presence and current value of `alembic_version`

## 3. How to read the result

### `fresh_database_upgrade`
Meaning:
- empty or almost empty database

Action:

```bash
cd backend
alembic -c alembic.ini upgrade head
```

### `managed_database_upgrade`
Meaning:
- database already has `alembic_version`
- but it is not yet on current head

Action:

```bash
cd backend
alembic -c alembic.ini upgrade head
```

### `already_on_head`
Meaning:
- environment is already at current Alembic head

Action:
- no migration action required
- continue with application deployment checks

### `legacy_schema_stamp_head`
Meaning:
- legacy schema appears complete
- `alembic_version` is missing
- database was likely created by `create_all()` or equivalent

Action:
- confirm schema really matches current application expectation
- back up the database
- then stamp without applying DDL again

```bash
cd backend
alembic -c alembic.ini stamp 4f9d3c1b7a21
```

### `legacy_schema_stamp_baseline_then_upgrade`
Meaning:
- legacy core tables exist
- approval tables do not exist
- `alembic_version` is missing

Recommended action:

```bash
cd backend
alembic -c alembic.ini stamp 7b2f8f8a1c3d
alembic -c alembic.ini upgrade head
```

This is the most common path for environments that existed before approval workflow rollout.

### `manual_review_required`
Meaning:
- schema is partially present or inconsistent
- blind stamp/upgrade may be unsafe

Action:
- stop automatic migration
- inspect actual schema manually
- compare missing tables/columns from script output against expected model set

## 4. Production rollout checklist

Before migration:
- back up the production database
- set `AUTO_CREATE_TABLES=false`
- ensure only one deployment job applies Alembic migrations
- verify backend image and migration code are from the same commit

Migration steps:
1. run preflight script
2. choose the matching action path
3. run `alembic` command(s)
4. verify `alembic_version`
5. start backend
6. verify `/health`
7. verify one read-only API and one approval workflow path

## 5. Current revision chain

Current expected chain:
- `7b2f8f8a1c3d` -> core baseline
- `10c51a4fa5af` -> alert rule scheduling fields
- `4f9d3c1b7a21` -> approval tables

Current Alembic head:
- `4f9d3c1b7a21`

## 6. Notes

- Production should prefer Alembic-first schema management.
- `AUTO_CREATE_TABLES=true` should be treated as a temporary bootstrap convenience for development only.
- If your database has drift from handwritten changes, do not stamp blindly; inspect first.
