# Alembic Cutover Runbook

> Updated: 2026-04-08
> Audience: operators migrating an existing environment from runtime `create_all()` behavior to Alembic-first schema management
> Hive model note: architecture and migration review uses `qwen3.6-plus`, implementation uses `kimi-for-coding`

## 1. Why this runbook exists

Older environments may have been initialized by application startup logic instead of Alembic migrations.
That means the database can already contain tables, but no `alembic_version` record.

This runbook helps decide whether to:
- run `alembic upgrade head`
- run `alembic stamp head`
- stop and inspect schema drift manually

## 2. Precheck script

Use the new schema precheck script before touching production revision state:

```bash
cd backend
.venv313/bin/python app/scripts/schema_precheck.py
```

The script inspects:
- current tables
- whether `alembic_version` exists
- current Alembic revision if present
- whether expected core and approval tables exist

Current expected migration head:
- `4f9d3c1b7a21`

Current baseline revision:
- `7b2f8f8a1c3d`

## 3. How to interpret precheck output

### Case A: `status=fresh_database`
Meaning:
- database is effectively empty for this app
- no current schema needs preservation

Action:

```bash
cd backend
alembic -c alembic.ini upgrade head
```

### Case B: `status=fully_migrated`
Meaning:
- `alembic_version` exists and already points to current head

Action:
- deploy normally
- keep `AUTO_CREATE_TABLES=false`
- optionally still run `alembic -c alembic.ini upgrade head` as a safe no-op during deployment

### Case C: `status=partially_migrated`
Meaning:
- database has Alembic state, but not at current head

Action:

```bash
cd backend
alembic -c alembic.ini upgrade head
```

Before running in production:
- review migration history
- confirm backup exists

### Case D: `status=legacy_create_all_database`
Meaning:
- the schema appears complete
- there is no `alembic_version`
- the environment was likely created by `Base.metadata.create_all()` or manual DDL

Recommended action:
1. backup the database
2. manually verify a few critical tables and columns
3. if schema matches current code, stamp the revision instead of replaying all migrations

Suggested command:

```bash
cd backend
alembic -c alembic.ini stamp head
```

Do not do this blindly if schema drift exists.

### Case E: `status=partially_bootstrapped_database`
Meaning:
- database has some expected tables but not a full schema
- there is no Alembic version table

Action:
- stop automatic rollout
- inspect table/column drift manually
- decide whether to repair schema first or rebuild from backup

## 4. Minimal manual verification before `stamp head`

If the precheck suggests `legacy_create_all_database`, verify at least these tables exist:
- `users`
- `platform_accounts`
- `domains`
- `dns_records`
- `alert_rules`
- `audit_logs`
- `change_requests`
- `change_request_events`

Also spot-check these key columns:
- `change_requests.status`
- `change_requests.request_no`
- `change_requests.payload`
- `alert_rules.excluded_platforms`
- `alert_rules.schedule`
- `platform_accounts.credentials`
- `dns_records.external_id`

## 5. Production cutover checklist

1. Backup the production database
2. Set `AUTO_CREATE_TABLES=false`
3. Run `python app/scripts/schema_precheck.py`
4. Choose one path:
   - `alembic upgrade head`
   - `alembic stamp head`
   - manual review first
5. Deploy backend
6. Verify `/health`
7. Verify pending approval creation works
8. Verify Feishu callback works
9. Verify `/change-requests` fallback page works

## 6. Recommended production policy going forward

After cutover:
- do not rely on startup table creation in production
- keep all schema evolution in Alembic revisions
- use precheck before future major schema rollouts if an environment's history is uncertain
