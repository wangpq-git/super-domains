# Domain Manage - Approval Workflow Plan

> Generated: 2026-04-08
> Scope: Domain / DNS / nameserver change approval workflow for API callers and website users
> Models consulted via hive-style discussion: `qwen3.6-plus`, `kimi-for-coding`, `kimi-for-coding`
> Reassigned hive execution set: `kimi-for-coding`, `qwen3.6-plus`, `glm-5-turbo`

---

## Goal

Build a unified approval workflow so that:
- API callers cannot directly execute domain / DNS write operations
- Website normal users cannot directly execute domain / DNS write operations
- All write actions become approval requests first
- Feishu is used as the main approval entry and notification channel
- The system remains the source of truth for status, permissions, execution, and audit

This plan uses four phases: `P0` to `P3`.

---

## Core Decision

Adopt a unified `change request` model:
- All write actions become `change_requests`
- Request creation returns immediately with `202 Accepted`
- Approver confirms or rejects in Feishu
- Only approved requests execute the existing domain / DNS service logic
- API callers and website users share the same backend state machine

Why this is the recommended design:
- Approval is inherently asynchronous
- Existing execution code can be reused with minimal disruption
- Audit and rollback analysis become much easier
- Future risk-based automation can be added without redesigning the system

---

## Target Scope

Covered operations:
- DNS record create
- DNS record update
- DNS record delete
- Batch DNS update / replace
- Nameserver update
- Future domain create / update / delete APIs

Not in first-wave scope:
- Full multi-level approval chain
- Fine-grained policy engine
- Automatic rollback engine
- External tenant-specific approval routing

---

## Target Architecture

### Request flow
1. User or API client submits a write request
2. Backend validates payload and converts it into a `change_request`
3. Backend stores snapshots and request metadata
4. Backend sends a Feishu approval card
5. Approver clicks `approve` or `reject`
6. Backend verifies signature, role, token freshness, and request state
7. If approved, backend executes the existing service method
8. Backend updates request status and emits notifications
9. Audit/event records are persisted throughout the lifecycle

### Core states
- `pending_approval`
- `approved`
- `rejected`
- `executing`
- `succeeded`
- `failed`
- `expired`
- `cancelled`

---

## Recommended Hive Model Assignment

| Work Type | Recommended Hive Model | Why |
|---|---|---|
| Architecture, schema design, state machine, API contract | `qwen3.6-plus` | Best fit among this set for system design, data modeling, implementation planning, and test coverage |
| Feishu integration, backend feature implementation, workflow coding | `kimi-for-coding` | Strongest coding-oriented choice here for service wiring, callback handling, and end-to-end feature delivery |
| Fast follow-up changes, docs polishing, utility modules, low-complexity glue work | `glm-5-turbo` | Best used for faster small-to-medium tasks, documentation updates, helper logic, and lightweight optimizations |

### Suggested usage in this project
- Use `qwen3.6-plus` for `P0` design decisions: request schema, status machine, risk classification, API contracts, and test strategy
- Use `kimi-for-coding` for `P1` core implementation: migrations, models, service orchestration, Feishu callback handling, and route interception
- Use `qwen3.6-plus` again for `P2` rule design, cancellation/timeout flow, and regression-oriented backend changes
- Use `glm-5-turbo` for docs, notification copy, admin-facing helper endpoints, lightweight UI glue, and non-critical polish

### Practical scoring-based assignment
- `kimi-for-coding`: highest priority for coding-heavy tickets
- `qwen3.6-plus`: highest priority for architecture-heavy and test-heavy tickets
- `glm-5-turbo`: highest priority for speed-sensitive utility and documentation tickets

## Phase P0 - Architecture and MVP Contract

Objective:
- Lock the data model, status machine, and API contract before touching execution paths

Deliverables:
- Approved workflow design
- New database entities defined
- API contract defined for create/query/approve/reject/cancel
- Feishu callback contract defined
- Security and idempotency rules defined

### Tasks

| ID | Task | Priority | Hive Model | Output |
|---|---|---|---|---|
| P0.1 | Define request lifecycle and status machine | P0 | `qwen3.6-plus` | State transition spec |
| P0.2 | Define `change_requests` schema | P0 | `qwen3.6-plus` | Table fields and indexes |
| P0.3 | Define `change_request_events` schema | P0 | `qwen3.6-plus` | Event/audit timeline schema |
| P0.4 | Define unified API contract | P0 | `qwen3.6-plus` | REST endpoints and response schema |
| P0.5 | Define Feishu card fields and callback flow | P0 | `kimi-for-coding` | Card design and callback contract |
| P0.6 | Define risk levels and MVP approval policy | P0 | `kimi-for-coding` | Low/medium/high action rules |
| P0.7 | Review security boundaries and replay protection | P0 | `qwen3.6-plus` | Security checklist |

### Proposed API contract
- `POST /api/v1/change-requests`
- `GET /api/v1/change-requests/{id}`
- `GET /api/v1/change-requests/me`
- `POST /api/v1/change-requests/{id}/approve`
- `POST /api/v1/change-requests/{id}/reject`
- `POST /api/v1/change-requests/{id}/cancel`
- `POST /api/v1/webhooks/feishu/change-requests`

### Proposed core tables

#### `change_requests`
- `id`
- `request_no`
- `source` (`api`, `web`, `internal`)
- `requester_user_id`
- `requester_name`
- `requester_type`
- `operation_type`
- `target_type`
- `target_id`
- `domain_id`
- `payload`
- `before_snapshot`
- `after_snapshot`
- `risk_level`
- `status`
- `approval_channel`
- `approver_user_id`
- `approver_name`
- `approved_at`
- `rejected_at`
- `rejection_reason`
- `executed_at`
- `execution_result`
- `error_message`
- `idempotency_key`
- `expires_at`
- `created_at`
- `updated_at`

#### `change_request_events`
- `id`
- `change_request_id`
- `event_type`
- `actor_type`
- `actor_id`
- `detail`
- `created_at`

### P0 acceptance criteria
- One agreed state machine
- One agreed schema for request + event tables
- One agreed endpoint set
- One agreed Feishu callback pattern
- One agreed MVP approval policy

---

## Phase P1 - Backend MVP

Objective:
- Introduce approval workflow without rewriting the existing execution services

Strategy:
- Add a new orchestration layer and intercept write APIs at the boundary
- Keep the current `dns_service` and related execution logic as the executor

### Tasks

| ID | Task | Priority | Hive Model | Output |
|---|---|---|---|---|
| P1.1 | Add Alembic migration for approval tables | P1 | `kimi-for-coding` | Migration script |
| P1.2 | Add models/schemas for change requests | P1 | `kimi-for-coding` | SQLAlchemy + Pydantic models |
| P1.3 | Add `change_request_service` orchestration | P1 | `kimi-for-coding` | Request create/approve/reject/cancel logic |
| P1.4 | Add Feishu notification/callback service | P1 | `kimi-for-coding` | Card sender and callback parser |
| P1.5 | Add approval endpoints | P1 | `kimi-for-coding` | FastAPI routes |
| P1.6 | Intercept `backend/app/api/v1/dns.py` write endpoints | P1 | `kimi-for-coding` | Direct writes become approval requests |
| P1.7 | Intercept `backend/app/api/v1/batch.py` write endpoints | P1 | `kimi-for-coding` | Batch operations become approval requests |
| P1.8 | Reuse `dns_service` as execution engine after approval | P1 | `kimi-for-coding` | Approved request executor |
| P1.9 | Log request lifecycle to approval events + audit log | P1 | `glm-5-turbo` | Traceable action chain |
| P1.10 | Add result notifications to Feishu/group | P1 | `glm-5-turbo` | Success/reject/fail messages |
| P1.11 | Security review of callback verification and replay prevention | P1 | `qwen3.6-plus` | Review notes/fixes |

### Backend implementation notes
- MVP can execute approved requests synchronously
- Celery is optional in P1; do not block MVP on queue refactor
- Approval execution must be idempotent
- Approval callback must reject already-processed requests
- Use one-time action token or signed callback payload

### P1 acceptance criteria
- API write requests return `pending_approval`
- Feishu card can approve or reject a request
- Approved request executes exactly once
- Rejected request never touches external provider APIs
- Full request lifecycle is queryable and auditable

### P1 deployment config

Required environment variables for the current backend implementation:

| Key | Required | Purpose |
|---|---|---|
| `FEISHU_APPROVAL_WEBHOOK_URL` | Yes | Send pending approval cards and final result notifications to Feishu |
| `FEISHU_APPROVAL_BASE_URL` | Recommended | Generate absolute approve/reject/detail URLs embedded in cards |
| `FEISHU_APPROVAL_CALLBACK_TOKEN` | Yes | Basic token validation for Feishu callback requests |
| `FEISHU_APPROVAL_ENCRYPT_KEY` | Yes | Callback signature validation secret |
| `FEISHU_APPROVAL_SIGNATURE_TOLERANCE_SECONDS` | Recommended | Allowed callback timestamp skew; default `300` |
| `FEISHU_APPROVAL_ADMIN_MAP` | Recommended | JSON map from Feishu identity fields to local admin username or id |

Current callback behavior in code:
- `POST /api/v1/webhooks/feishu/change-requests`
- Validates token, signature, timestamp tolerance, and current request status
- Supports admin resolution by local user id, username, email, or configured identity mapping
- Returns processed-state card on success and idempotent `200` on repeated actions

Recommended `FEISHU_APPROVAL_ADMIN_MAP` examples:

```json
{
  "ou_0123456789abcdef": "testadmin",
  "admin@example.com": "testadmin",
  "testadmin": "testadmin",
  "4": 1
}
```

Deployment checklist:
- Expose backend callback endpoint to Feishu event subscription
- Configure Feishu event callback token and encrypt key to match backend env
- Ensure at least one local active `admin` user can be resolved from callback identity
- Verify the webhook bot can post to the target Feishu chat/group
- Test one approve flow and one reject flow before enabling for all production writes

---

## Phase P2 - Website Workflow and Risk-Based Automation

Objective:
- Make the workflow usable for normal users and reduce approval noise

### Tasks

| ID | Task | Priority | Hive Model | Output |
|---|---|---|---|---|
| P2.1 | Add website page: `My Change Requests` | P2 | `glm-5-turbo` | User request list page |
| P2.2 | Add website page: request detail/status timeline | P2 | `glm-5-turbo` | Request detail page |
| P2.3 | Add admin page: approval center fallback | P2 | `glm-5-turbo` | Web approval UI |
| P2.4 | Add cancel-before-approval support | P2 | `kimi-for-coding` | Request cancellation logic |
| P2.5 | Add timeout auto-reject | P2 | `kimi-for-coding` | Expiration job or scheduled scan |
| P2.6 | Add risk classification helper | P2 | `qwen3.6-plus` | Low/medium/high classifier |
| P2.7 | Add low-risk auto-approval rules | P2 | `qwen3.6-plus` | Rule-based bypass |
| P2.8 | Add post-execution user notification | P2 | `glm-5-turbo` | User-facing feedback |
| P2.9 | Review rule bypass risks and sensitive actions | P2 | `qwen3.6-plus` | Risk review |

### Recommended first risk rules

Auto-approve candidates:
- Add non-root `TXT` record
- Add non-root `CNAME`
- Small TTL-only change on non-critical records
- Requests from trusted internal automation with whitelist token

Must require approval:
- Delete any record
- Modify root `A/AAAA`
- Modify `MX`
- Modify `NS`
- Wildcard `*`
- Batch `replace`
- Any production critical domain on protected list

### P2 acceptance criteria
- Website users can submit requests and track status
- Admins can approve in Feishu or in website fallback UI
- At least one safe low-risk class can auto-pass
- Timeout requests are automatically closed out

---

## Phase P3 - Hardening, Scale, and Production Controls

Objective:
- Make the approval workflow reliable at scale and safer for production use

### Tasks

| ID | Task | Priority | Hive Model | Output |
|---|---|---|---|---|
| P3.1 | Move approved execution to Celery if latency/noise grows | P3 | `kimi-for-coding` | Async execution path |
| P3.2 | Add retry policy and failure handling for external provider calls | P3 | `kimi-for-coding` | Reliable execution wrapper |
| P3.3 | Add optimistic concurrency / locking for same-domain requests | P3 | `qwen3.6-plus` | Collision prevention |
| P3.4 | Add richer Feishu card diff and processed-state update | P3 | `glm-5-turbo` | Safer approval UX |
| P3.5 | Add metrics/dashboard for request volume and approval latency | P3 | `qwen3.6-plus` | Operational visibility |
| P3.6 | Add integration tests for callback and execution paths | P3 | `kimi-for-coding` | Regression coverage |
| P3.7 | Add security regression checks for replay/idempotency/rbac | P3 | `qwen3.6-plus` | Hardening checklist |
| P3.8 | Add policy configuration UI | P3 | `glm-5-turbo` | Admin rule management |

### P3 acceptance criteria
- Approval workflow remains stable under concurrent requests
- External provider failures are retriable and observable
- Feishu cards clearly show processed state and cannot be reused
- Operational metrics are available for support and tuning

---

## API Behavior Recommendations

### Submission behavior
- Always return `202 Accepted` for approval-required writes
- Response should include:
  - `request_id`
  - `request_no`
  - `status`
  - `expires_at`
  - optional `poll_url`

### Idempotency
- Support `idempotency_key` for API clients
- Duplicate request within a safe time window returns the original request record

### Query behavior
- Users can query only their own requests unless admin
- Admin can search by domain, status, source, operation type, time range

---

## Feishu Design Recommendations

Approval card should show:
- Request ID
- Applicant
- Source (`API` / `Web`)
- Domain
- Operation type
- Before/after diff
- Risk level
- Submitted time
- `Approve` and `Reject` buttons

Safe interaction rules:
- Reject requires a reason
- Action token expires
- Only allowed approvers can operate
- Once processed, the card should update to a non-actionable state
- All card actions must be verified by callback signature and current request status

---

## Security Requirements

Mandatory controls:
- Signed or one-time approval action token
- Replay protection
- Approver RBAC check on every approval action
- Idempotent execution guard
- Callback source verification
- Immutable lifecycle events
- Sensitive payload redaction if credentials or secrets appear in snapshots

---

## Testing Plan

### Must-have tests
- Request creation from API caller
- Request creation from website user
- Approve path executes exactly once
- Reject path does not execute provider call
- Duplicate callback cannot double-execute
- Expired request cannot be approved
- Normal user cannot approve requests
- Batch approval request preserves per-domain payload correctly

### Nice-to-have tests
- Same-domain concurrent requests
- Feishu callback signature failure
- Provider execution failure transitions to `failed`
- Auto-approval rule behavior

Recommended implementation/testing split:
- Backend workflow coding: `kimi-for-coding`
- Architecture and regression review: `qwen3.6-plus`
- Utility test scaffolding and docs polish: `glm-5-turbo`

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Feishu callback misuse or replay | High | Signed token, expiry, one-time state transition |
| Request approved twice | High | Atomic status transition + idempotent executor |
| Existing APIs bypass new flow | High | Centralize all writes behind orchestration layer |
| Batch requests too risky for MVP | Medium | Force batch writes through approval, no auto-pass initially |
| Approval fatigue | Medium | Introduce P2 low-risk auto-approval |
| Request payload leaks sensitive data | High | Snapshot sanitization and field redaction |
| External provider slow/failing execution | Medium | Add P3 async execution and retry wrapper |

---

## Suggested Delivery Order

1. Complete `P0` design lock
2. Implement `P1` backend MVP for DNS and batch write flows
3. Release `P2` website request visibility and low-risk automation
4. Harden with `P3` async execution, metrics, and policy controls

---

## Summary Recommendation

If only one path is chosen now, implement:
- `P0` immediately
- `P1` for DNS CRUD + batch nameserver/DNS approvals

That gives the biggest business value fastest:
- No more direct risky writes from users
- Feishu approval entry works for both API and website
- Existing execution code stays reusable
- The system can later evolve toward low-risk auto-approval without redesign
