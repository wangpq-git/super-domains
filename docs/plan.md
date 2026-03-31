# Domain Manage Platform - Development Plan

> Generated: 2026-03-31
> Models consulted: qwen3.5-plus, kimi-k2.5, glm-5, gpt-5.4

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI + Python 3.11+ |
| Frontend | Vue 3 + TypeScript + Element Plus |
| Database | PostgreSQL 15 + Redis |
| ORM | SQLAlchemy 2.0 + Alembic |
| Task Queue | Celery + Redis |
| Deploy | Docker Compose + Nginx |
| Auth | JWT |

## Supported Platforms

name.com / cloudflare / dynadot / godaddy / namecheap / namesilo / openprovider / porkbun / spaceship

---

## Phase 1: Foundation + MVP (3-4 weeks)

Core infrastructure and 2 pilot platform integrations.

| ID | Task | Priority | Hive Model | Est |
|----|------|----------|------------|-----|
| 1.1 | Project scaffolding (FastAPI + Vue3 + Docker Compose) | P0 | kimi-k2.5 | 2d |
| 1.2 | Database models + Alembic migrations (users, platform_accounts, domains, dns_records, transfers, alert_rules, audit_logs) | P0 | qwen3.5-plus | 2d |
| 1.3 | Core config (env management, logging, exception handler, CORS) | P0 | glm-5 | 1d |
| 1.4 | JWT auth + RBAC (admin/editor/viewer) | P0 | kimi-k2.5 | 2d |
| 1.5 | API credential encryption (AES-256-GCM, key from env) | P0 | qwen3.5-plus | 1d |
| 1.6 | Platform account CRUD API + frontend page | P0 | kimi-k2.5 | 2d |
| 1.7 | BasePlatformAdapter abstract class + factory | P0 | qwen3.5-plus | 1d |
| 1.8 | Cloudflare adapter (domains + DNS) | P0 | kimi-for-coding | 3d |
| 1.9 | Name.com adapter (domains + DNS) | P0 | kimi-for-coding | 2d |
| 1.10 | Domain sync service + Celery scheduled task | P0 | qwen3.5-plus | 2d |
| 1.11 | Domain list API (pagination, multi-dimension filter) | P0 | glm-5 | 2d |
| 1.12 | Frontend: login + layout + domain list + filters | P0 | kimi-k2.5 | 4d |
| 1.13 | Docker Compose deployment config | P1 | glm-5-turbo | 1d |

**Phase 1 Deliverable**: Working MVP with Cloudflare + Name.com, domain list dashboard, manual/auto sync.

---

## Phase 2: Full Platform Coverage + DNS + Alerts (3-4 weeks)

Remaining 7 platform adapters, DNS management, expiry alerts.

| ID | Task | Priority | Hive Model | Est |
|----|------|----------|------------|-----|
| 2.1 | GoDaddy adapter | P1 | kimi-for-coding | 2d |
| 2.2 | Namecheap adapter (XML parsing, IP whitelist) | P1 | qwen3.5-plus | 3d |
| 2.3 | Porkbun adapter | P1 | glm-5 | 1.5d |
| 2.4 | NameSilo adapter (XML response) | P1 | glm-5 | 1.5d |
| 2.5 | Dynadot adapter (unstable format, signature) | P2 | qwen3.5-plus | 2.5d |
| 2.6 | OpenProvider adapter (token auth + refresh) | P2 | kimi-k2.5 | 2d |
| 2.7 | Spaceship adapter (new platform, docs may be incomplete) | P2 | kimi-k2.5 | 2d |
| 2.8 | Unified rate limiter (token bucket via Redis) | P1 | qwen3.5-plus | 1d |
| 2.9 | Retry mechanism (exponential backoff, tenacity) | P1 | glm-5-turbo | 0.5d |
| 2.10 | DNS record CRUD API (view/add/update/delete) | P1 | kimi-for-coding | 3d |
| 2.11 | Frontend: DNS management page | P1 | kimi-k2.5 | 3d |
| 2.12 | Alert rules configuration API | P1 | glm-5 | 1.5d |
| 2.13 | Expiry check Celery task (30/14/7/3/1 day triggers) | P1 | qwen3.5-plus | 1d |
| 2.14 | Notification service: email (SMTP) | P1 | glm-5-turbo | 1d |
| 2.15 | Notification service: webhook (DingTalk/WeCom/Slack) | P2 | glm-5-turbo | 1d |
| 2.16 | Frontend: alert settings page | P2 | kimi-k2.5 | 2d |
| 2.17 | Frontend: dashboard stats (expiry distribution, platform distribution charts) | P2 | kimi-k2.5 | 2d |

**Phase 2 Deliverable**: All 9 platforms connected, DNS CRUD, expiry alerts via email/webhook.

---

## Phase 3: Advanced Features (2-3 weeks)

Transfer management, batch operations, reporting.

| ID | Task | Priority | Hive Model | Est |
|----|------|----------|------------|-----|
| 3.1 | Domain transfer API (get auth code, status tracking) | P2 | qwen3.5-plus | 2d |
| 3.2 | Frontend: transfer management page | P2 | kimi-k2.5 | 2d |
| 3.3 | Batch DNS operations (bulk update NS, bulk modify records) | P2 | kimi-for-coding | 2d |
| 3.4 | Batch domain operations UI | P3 | kimi-k2.5 | 2d |
| 3.5 | Data export (CSV/Excel) | P3 | glm-5-turbo | 1d |
| 3.6 | Domain search (fuzzy search, TLD filter, regex) | P2 | glm-5 | 1d |
| 3.7 | Audit log system (who did what when) | P3 | glm-5-turbo | 1d |
| 3.8 | Statistics & reports API (domain distribution, cost analysis) | P3 | qwen3.5-plus | 2d |
| 3.9 | Frontend: reports & charts page | P3 | kimi-k2.5 | 2d |

**Phase 3 Deliverable**: Full-featured platform with transfer mgmt, batch ops, audit trail.

---

## Phase 4: Optimization & Production (1-2 weeks)

Testing, monitoring, performance, production readiness.

| ID | Task | Priority | Hive Model | Est |
|----|------|----------|------------|-----|
| 4.1 | Unit tests for all adapters (mock API responses) | P3 | qwen3.5-plus | 3d |
| 4.2 | Integration tests (sync engine, notification service) | P3 | kimi-k2.5 | 2d |
| 4.3 | API response caching strategy (Redis TTL) | P4 | glm-5-turbo | 1d |
| 4.4 | Large dataset pagination optimization | P4 | glm-5-turbo | 1d |
| 4.5 | Error monitoring (Sentry integration) | P4 | glm-5-turbo | 0.5d |
| 4.6 | CI/CD pipeline (GitHub Actions) | P4 | glm-5-turbo | 1d |
| 4.7 | Production deployment docs | P4 | glm-5-turbo | 0.5d |
| 4.8 | Dark mode / i18n | P5 | kimi-k2.5 | 2d |
| 4.9 | Mobile responsive adaptation | P5 | kimi-k2.5 | 2d |
| 4.10 | API docs polish (OpenAPI/Swagger) | P5 | glm-5-turbo | 0.5d |

**Phase 4 Deliverable**: Production-ready, tested, monitored, documented.

---

## Hive Model Assignment Strategy

| Model | Strengths | Assign To |
|-------|-----------|-----------|
| **kimi-for-coding** | Coding: 0.93, Chinese: 0.95 | Platform adapter implementations, complex API integration, DNS CRUD |
| **qwen3.5-plus** | Coding: 0.88, Chinese: 0.90 | Architecture design, database models, sync engine, encryption, test cases |
| **kimi-k2.5** | Reasoning: 0.80, Pass: 0.83 | Auth system, frontend pages, transfer workflow, review tasks |
| **glm-5** | Coding: 0.85, Chinese: 0.90 | Config modules, search, simpler adapters (Porkbun/NameSilo) |
| **glm-5-turbo** | Pass: 0.91, fast | Utility tasks, notifications, caching, CI/CD, docs, small features |
| **gpt-5.4** | Strong reasoning | Architecture review, complex debugging, security audit |

### Priority Legend

| Level | Meaning |
|-------|---------|
| P0 | Must-have for MVP |
| P1 | Important, needed for complete product |
| P2 | Valuable enhancement |
| P3 | Nice-to-have |
| P4 | Optimization & ops |
| P5 | Future polish |

---

## Risk Matrix

| Risk | Impact | Mitigation |
|------|--------|------------|
| Dynadot/Spaceship API docs incomplete | High | Reserve extra debug time; fallback to manual import |
| Namecheap IP whitelist requirement | High | Deploy with fixed egress IP (NAT gateway) |
| API credential leak | Critical | AES-256 encryption from Phase 1; env-only keys |
| Rate limiting across platforms | Medium | Unified Redis token-bucket limiter + exponential backoff |
| China → overseas API latency | Medium | Consider proxy or overseas deploy node |
| Platform API breaking changes | Medium | Adapter integration tests in CI; monitor changelogs |

---

## Estimated Timeline

| Config | MVP (Phase 1) | Full (Phase 1-4) |
|--------|--------------|-------------------|
| 1 fullstack dev | 5-6 weeks | 14-16 weeks |
| 2 devs (1 BE + 1 FE) | 3-4 weeks | 8-10 weeks |
| 3 devs (2 BE + 1 FE) | 2-3 weeks | 6-8 weeks |
