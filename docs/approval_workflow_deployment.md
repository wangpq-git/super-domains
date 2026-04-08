# Approval Workflow Deployment Guide

> Scope: P1 approval workflow for DNS / nameserver change requests
> Updated: 2026-04-08
> Hive model note: architecture/test review uses `qwen3.6-plus`, implementation uses `kimi-for-coding`, docs/glue uses `glm-5-turbo`

## 1. What this deployment enables

After deployment:
- DNS and batch write APIs no longer execute immediately
- Write requests first become `change_requests`
- Feishu is the primary approval entry
- `/change-requests` is the web fallback approval center
- Approved requests execute once, and repeated clicks stay idempotent

## 2. Required environment variables

Set these in production before enabling approval-required writes:

- `FEISHU_APPROVAL_WEBHOOK_URL`
  - Feishu bot webhook used for pending approval cards and final result notifications
- `FEISHU_APPROVAL_BASE_URL`
  - Public backend or site base URL, for card metadata and callback-related links
- `FEISHU_APPROVAL_CALLBACK_TOKEN`
  - Token used to validate Feishu callback requests
- `FEISHU_APPROVAL_ENCRYPT_KEY`
  - Encrypt key used for callback signature validation
- `FEISHU_APPROVAL_SIGNATURE_TOLERANCE_SECONDS`
  - Allowed timestamp skew for callback signature validation, default `300`
- `FEISHU_APPROVAL_ADMIN_MAP`
  - JSON map from Feishu identity to local admin username or local admin id

Example:

```env
FEISHU_APPROVAL_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/<token>
FEISHU_APPROVAL_BASE_URL=https://domain-manage.example.com
FEISHU_APPROVAL_CALLBACK_TOKEN=<callback_token>
FEISHU_APPROVAL_ENCRYPT_KEY=<encrypt_key>
FEISHU_APPROVAL_SIGNATURE_TOLERANCE_SECONDS=300
FEISHU_APPROVAL_ADMIN_MAP={"ou_xxx":"testadmin","admin@example.com":"testadmin"}
AUTO_CREATE_TABLES=false
```

## 3. Database migration strategy

Current project status:
- A core baseline migration now exists: `7b2f8f8a1c3d_create_core_schema_baseline.py`
- Approval-related Alembic migrations extend from that baseline and can upgrade an empty database to the current approval schema
- Runtime auto-create is now controlled by `AUTO_CREATE_TABLES`

Recommended production rule:
- Use Alembic as the primary schema migration path for approval workflow rollout
- Keep `AUTO_CREATE_TABLES=false` in production
- Do not rely on ad hoc runtime schema creation in production

Minimum rollout sequence:
1. Stop old backend instances
2. Backup production database
3. Run `python app/scripts/schema_precheck.py`
4. Based on the result, choose `alembic upgrade head` or `alembic stamp head`
5. Run the selected Alembic command
4. Start backend with approval env vars enabled
5. Verify callback endpoint and approval center access

Detailed legacy cutover runbook:
- `docs/alembic_cutover_runbook.md`

Validated approval migration path:
- `7b2f8f8a1c3d_create_core_schema_baseline.py`
- `10c51a4fa5af_add_missing_alert_rule_scheduling_fields.py`
- `4f9d3c1b7a21_add_change_requests_tables.py`

## 4. Feishu-side setup

You need two Feishu-side pieces:

### 4.1 Group bot webhook
Used to send:
- pending approval cards
- approved / rejected / failed result cards

Configure its webhook URL into:
- `FEISHU_APPROVAL_WEBHOOK_URL`

### 4.2 Event callback subscription
Used to receive:
- button click callbacks from approval cards

Backend callback endpoint:
- `POST /api/v1/webhooks/feishu/change-requests`

Configure in Feishu:
- callback URL -> `https://<your-domain>/api/v1/webhooks/feishu/change-requests`
- verification token -> same as `FEISHU_APPROVAL_CALLBACK_TOKEN`
- encrypt key -> same as `FEISHU_APPROVAL_ENCRYPT_KEY`

## 5. Local admin mapping requirement

Before go-live, ensure at least one local active admin user exists.

The callback resolver currently supports:
- local user id from callback payload
- local username
- local email
- mapped Feishu identity from `FEISHU_APPROVAL_ADMIN_MAP`

Recommended mapping strategy:
- map Feishu `open_id` or email to local admin username
- keep at least one verified admin test account for dry runs

Example:

```json
{
  "ou_0123456789abcdef": "testadmin",
  "admin@example.com": "testadmin"
}
```

## 6. Approval center fallback

Web fallback page:
- `/change-requests`

Role behavior:
- admin: can see all requests, approve, reject, inspect payload/result
- normal user: can see own requests and cancel pending ones

Use this page when:
- Feishu callback is unavailable
- bot delivery is delayed
- admin wants to inspect payload/result in the system UI

## 7. Go-live checklist

Before enabling for all users, verify this end-to-end path:

1. Create a DNS record through API or web UI
2. Confirm backend returns `202 Accepted` with `pending_approval`
3. Confirm Feishu receives a pending approval card
4. Approve in Feishu
5. Confirm backend executes exactly once
6. Confirm Feishu receives a final result card
7. Click the same card again and confirm it returns idempotent processed state
8. Open `/change-requests` and confirm final state is visible
9. Reject another request and confirm no provider-side execution occurs

## 8. Operational notes

Current known follow-up items:
- Full-project Alembic-first baseline is now in place for the current model set, but older environments that were created via `create_all()` should still be upgraded carefully
- Frontend approval center is MVP-level fallback, not yet a full audit console
- Existing warnings in tests are mostly deprecations and do not block this workflow rollout
