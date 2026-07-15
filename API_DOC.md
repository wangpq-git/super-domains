# Super Domains API Documentation

- Site: `http://super-domains.localities.site`
- API base: `http://super-domains.localities.site/api/v1`
- Health: `http://super-domains.localities.site/health`
- Ping: `http://super-domains.localities.site/api/v1/ping`
- Swagger UI: `http://super-domains.localities.site/docs`
- OpenAPI JSON: `http://super-domains.localities.site/openapi.json`

## 1. Authentication

### 1.1 Auth method
Most protected APIs use Bearer Token:

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

### 1.2 Permission levels
- Public: no login required
- Authenticated: login required
- Admin: admin role required

### 1.3 Common error responses

#### 401 Unauthorized
```json
{
  "detail": "Invalid token"
}
```
or
```json
{
  "detail": "Incorrect username or password"
}
```

#### 403 Forbidden
```json
{
  "detail": "仅管理员可操作"
}
```

#### 404 Not Found
```json
{
  "detail": "Domain not found"
}
```

#### 429 Too Many Requests
```json
{
  "detail": "同步频率过高，每5分钟最多3次"
}
```

## 1.4 Approval workflow for write actions

The following write operations no longer execute immediately. They first create a change request and return `202 Accepted`:

- DNS record create
- DNS record update
- DNS record delete
- Batch DNS update
- Batch nameserver update

Typical response:
```json
{
  "id": 12,
  "request_no": "3fa85f64c1ab",
  "operation_type": "dns_create",
  "status": "pending_approval",
  "approval_channel": "feishu"
}
```

Processing flow:
- User calls a write API
- Backend creates a change request
- Backend sends a Feishu interactive card
- Admin approves or rejects in Feishu
- Backend executes the real change only after approval
- Backend sends a final result notification to Feishu
- Web users and admins can also use the fallback approval center at `/change-requests`

Important deployment config:
- `FEISHU_APPROVAL_WEBHOOK_URL`: Feishu bot webhook for pending/result notifications
- `FEISHU_APPROVAL_BASE_URL`: public backend base URL shown in card metadata
- `FEISHU_APPROVAL_CALLBACK_TOKEN`: Feishu callback token validation
- `FEISHU_APPROVAL_ENCRYPT_KEY`: Feishu callback signature validation
- `FEISHU_APPROVAL_ADMIN_MAP`: JSON mapping from Feishu identity to local admin user

## 2. Public endpoints

### 2.1 Health check
- Method: `GET`
- Path: `/health`
- Auth: Public

Response example:
```json
{
  "status": "healthy",
  "service": "Domain Manage"
}
```

### 2.2 Ping
- Method: `GET`
- Path: `/api/v1/ping`
- Auth: Public

Response example:
```json
{
  "message": "pong"
}
```

## 3. Auth APIs

### 3.1 Login
- Method: `POST`
- Path: `/api/v1/auth/login`
- Auth: Public

Request body:
```json
{
  "username": "admin",
  "password": "your-password"
}
```

Response:
```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

cURL:
```bash
curl -X POST 'http://super-domains.localities.site/api/v1/auth/login' \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "admin",
    "password": "your-password"
  }'
```

### 3.2 Current user
- Method: `GET`
- Path: `/api/v1/auth/me`
- Auth: Authenticated

Response:
```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "role": "admin",
  "is_active": true,
  "auth_source": "local",
  "display_name": "Admin",
  "created_at": "2026-04-07T10:00:00"
}
```

### 3.3 Change password
- Method: `PUT`
- Path: `/api/v1/auth/password`
- Auth: Authenticated

Request body:
```json
{
  "old_password": "old-password",
  "new_password": "new-password"
}
```

Response:
```json
{
  "message": "Password updated"
}
```

## 4. Platform account APIs

### 4.1 List platform accounts
- Method: `GET`
- Path: `/api/v1/platforms`
- Auth: Public in current code

Query params:
- `sort_by`: default `created_at`
- `sort_order`: `asc` / `desc`, default `desc`
- `page`: default `1`
- `page_size`: default `20`, max `100`

Example:
```bash
curl 'http://super-domains.localities.site/api/v1/platforms?page=1&page_size=20&sort_by=created_at&sort_order=desc'
```

Response:
```json
{
  "items": [
    {
      "id": 1,
      "platform": "cloudflare",
      "account_name": "main-account",
      "is_active": true,
      "last_sync_at": "2026-04-07T16:00:00",
      "sync_status": "success",
      "sync_error": null,
      "domain_count": 120,
      "created_at": "2026-04-01T08:00:00"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### 4.2 Create platform account
- Method: `POST`
- Path: `/api/v1/platforms`
- Auth: Admin

Request body:
```json
{
  "platform": "cloudflare",
  "account_name": "main-account",
  "credentials": {
    "api_token": "xxx"
  },
  "config": {}
}
```

Response:
```json
{
  "id": 1,
  "platform": "cloudflare",
  "account_name": "main-account",
  "is_active": true,
  "last_sync_at": null,
  "sync_status": "idle",
  "sync_error": null,
  "domain_count": 0,
  "created_at": "2026-04-07T16:30:00"
}
```

### 4.3 Get platform account detail
- Method: `GET`
- Path: `/api/v1/platforms/{account_id}`
- Auth: Public in current code

Path params:
- `account_id`: platform account ID

### 4.4 Update platform account
- Method: `PUT`
- Path: `/api/v1/platforms/{account_id}`
- Auth: Admin

Request body fields are optional:
```json
{
  "account_name": "new-name",
  "credentials": {
    "api_token": "new-token"
  },
  "config": {},
  "is_active": true
}
```

### 4.5 Delete platform account
- Method: `DELETE`
- Path: `/api/v1/platforms/{account_id}`
- Auth: Admin

Response:
- HTTP `204 No Content`

### 4.6 Test account connection
- Method: `POST`
- Path: `/api/v1/platforms/{account_id}/test`
- Auth: Admin

Response example:
```json
{
  "message": "连接测试成功",
  "status": "success"
}
```
or
```json
{
  "message": "连接测试失败: invalid credential",
  "status": "failed"
}
```

### 4.7 Sync single account
- Method: `POST`
- Path: `/api/v1/platforms/{account_id}/sync`
- Auth: Authenticated
- Special rule: each user can call at most 3 times every 5 minutes

Response example:
```json
{
  "synced": 92,
  "status": "success"
}
```

Failure example:
```json
{
  "synced": 0,
  "status": "failed",
  "error": "some provider error"
}
```

### 4.8 Sync all accounts
- Method: `POST`
- Path: `/api/v1/platforms/sync-all`
- Auth: Authenticated

Response example:
```json
{
  "total": 5,
  "success": 4,
  "failed": 1,
  "results": [
    {
      "account_id": 1,
      "platform": "cloudflare",
      "account_name": "main-account",
      "status": "success",
      "upserted": 120,
      "removed": 0
    }
  ]
}
```

## 5. Domain APIs

### 5.1 List domains
- Method: `GET`
- Path: `/api/v1/domains`
- Auth: Public in current code

Query params:
- `platform`: string, optional
- `status`: string, optional
- `search`: string, optional
- `expiry_start`: string, optional
- `expiry_end`: string, optional
- `exclude_expired`: bool, default `false`
- `dns_manageable_only`: bool, default `false`
- `sort_by`: string, default `expiry_date`
- `sort_order`: `asc` / `desc`, default `asc`
- `page`: int, default `1`
- `page_size`: int, default `20`, max `500`

Example:
```bash
curl 'http://super-domains.localities.site/api/v1/domains?platform=cloudflare&search=example&dns_manageable_only=true&page=1&page_size=20'
```

Response example:
```json
{
  "items": [
    {
      "id": 101,
      "account_id": 1,
      "domain_name": "example.com",
      "tld": "com",
      "status": "active",
      "registration_date": "2025-04-01T00:00:00",
      "expiry_date": "2026-04-01T00:00:00",
      "auto_renew": true,
      "locked": true,
      "whois_privacy": false,
      "nameservers": ["ns1.cloudflare.com", "ns2.cloudflare.com"],
      "external_id": "example.com",
      "last_synced_at": "2026-04-07T16:00:00",
      "platform": "cloudflare",
      "account_name": "main-account"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### 5.2 Domain stats
- Method: `GET`
- Path: `/api/v1/domains/stats`
- Auth: Public in current code

Response example:
```json
{
  "total_domains": 500,
  "by_platform": {
    "cloudflare": 300,
    "porkbun": 200
  },
  "by_status": {
    "active": 480,
    "expired": 20
  },
  "expiring_30d": 23,
  "expiring_7d": 5,
  "expired": 20
}
```

### 5.3 Domain detail
- Method: `GET`
- Path: `/api/v1/domains/{domain_id}`
- Auth: Public in current code

Path params:
- `domain_id`: domain ID

## 6. DNS APIs

### 6.1 List DNS records
- Method: `GET`
- Path: `/api/v1/dns/{domain_id}/records`
- Auth: Public in current code

Query params:
- `sort_by`: default `record_type`
- `sort_order`: `asc` / `desc`, default `asc`

Response example:
```json
[
  {
    "id": 1,
    "domain_id": 101,
    "record_type": "A",
    "name": "example.com",
    "content": "1.2.3.4",
    "ttl": 600,
    "priority": null,
    "proxied": false,
    "external_id": "abc123",
    "sync_status": "synced",
    "created_at": "2026-04-07T16:00:00",
    "updated_at": "2026-04-07T16:00:00"
  }
]
```

### 6.2 Sync DNS records for a domain
- Method: `POST`
- Path: `/api/v1/dns/{domain_id}/sync`
- Auth: Public in current code

Success response example:
```json
{
  "domain_id": 101,
  "upserted": 5,
  "removed": 0
}
```

Failure response example:
```json
{
  "domain_id": 101,
  "upserted": 0,
  "removed": 0,
  "error": "provider api error"
}
```

### 6.3 Create DNS record
- Method: `POST`
- Path: `/api/v1/dns/{domain_id}/records`
- Auth: Admin

Request body:
```json
{
  "record_type": "A",
  "name": "www.example.com",
  "content": "1.2.3.4",
  "ttl": 600,
  "priority": null,
  "proxied": false
}
```

### 6.4 Update DNS record
- Method: `PUT`
- Path: `/api/v1/dns/records/{record_id}`
- Auth: Admin

Request body:
```json
{
  "content": "5.6.7.8",
  "ttl": 120,
  "priority": null,
  "proxied": true
}
```

### 6.5 Delete DNS record
- Method: `DELETE`
- Path: `/api/v1/dns/records/{record_id}`
- Auth: Admin

Response:
- HTTP `204 No Content`

## 7. Alert APIs

### 7.1 List alert rules
- Method: `GET`
- Path: `/api/v1/alerts/rules`
- Auth: Public in current code

Response example:
```json
[
  {
    "id": 1,
    "name": "7-day warning",
    "rule_type": "domain_expiry",
    "days_before": 7,
    "is_enabled": true,
    "channels": ["feishu"],
    "recipients": ["https://open.feishu.cn/..."],
    "apply_to_all": true,
    "specific_platforms": null,
    "specific_domains": null,
    "excluded_platforms": [],
    "severity": "warning",
    "schedule": {
      "type": "manual",
      "time": "09:00:00"
    },
    "last_triggered_at": null,
    "created_at": "2026-04-07T16:00:00"
  }
]
```

### 7.2 Create alert rule
- Method: `POST`
- Path: `/api/v1/alerts/rules`
- Auth: Admin

Request body:
```json
{
  "name": "7-day warning",
  "rule_type": "domain_expiry",
  "days_before": 7,
  "is_enabled": true,
  "channels": ["feishu"],
  "recipients": ["https://open.feishu.cn/open-apis/bot/v2/hook/xxx"],
  "apply_to_all": true,
  "specific_platforms": null,
  "specific_domains": null,
  "excluded_platforms": [],
  "severity": "warning",
  "schedule": {
    "type": "manual",
    "time": "09:00:00"
  }
}
```

Notes:
- `severity` allowed values: `urgent`, `warning`, `info`
- `days_before` range: `1` to `365`
- `schedule` is a free-form object in current code; current default is `{ "type": "manual", "time": "09:00:00" }`

### 7.3 Update alert rule
- Method: `PUT`
- Path: `/api/v1/alerts/rules/{rule_id}`
- Auth: Admin

Request body: same fields as create, all optional.

### 7.4 Delete alert rule
- Method: `DELETE`
- Path: `/api/v1/alerts/rules/{rule_id}`
- Auth: Admin

Response:
- HTTP `204 No Content`

### 7.5 Trigger alert check now
- Method: `POST`
- Path: `/api/v1/alerts/check`
- Auth: Authenticated

Response shape depends on `alert_service.check_expiring_domains` runtime result.
Typical automation should only check for HTTP status `200` and parse JSON dynamically.

### 7.6 List expiring domains
- Method: `GET`
- Path: `/api/v1/alerts/expiring`
- Auth: Public in current code

Query params:
- `days`: int, default `30`, range `1`-`365`
- `page`: int, default `1`
- `page_size`: int, default `20`, max `100`

Response example:
```json
{
  "items": [
    {
      "id": 101,
      "domain_name": "example.com",
      "expiry_date": "2026-04-15T00:00:00",
      "days_left": 8,
      "platform": "cloudflare",
      "account_name": "main-account"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

## 8. Batch APIs

### 8.1 Batch update DNS
- Method: `POST`
- Path: `/api/v1/batch/dns`
- Auth: Public in current code

Request body:
```json
{
  "domain_ids": [101, 102],
  "records": [
    {
      "record_type": "A",
      "name": "www.example.com",
      "content": "1.2.3.4",
      "ttl": 600,
      "priority": null,
      "proxied": false
    }
  ],
  "action": "add"
}
```

`action` values:
- `add`: add new records
- `replace`: delete all existing records first, then add supplied records

Response example:
```json
{
  "total": 2,
  "results": [
    {
      "domain_id": 101,
      "domain_name": "example.com",
      "status": "success"
    },
    {
      "domain_id": 102,
      "domain_name": "example.net",
      "status": "error",
      "message": "provider api error"
    }
  ]
}
```

### 8.2 Batch sync accounts
- Method: `POST`
- Path: `/api/v1/batch/sync`
- Auth: Public in current code

Request body:
```json
{
  "account_ids": [1, 2, 3]
}
```

Response example:
```json
{
  "total": 3,
  "results": [
    {
      "account_id": 1,
      "account_name": "main-account",
      "platform": "cloudflare",
      "status": "syncing"
    }
  ]
}
```

Note:
- This endpoint only marks account status to `syncing` in current code. It does not actually execute the full provider sync flow.

### 8.3 Batch update nameservers
- Method: `POST`
- Path: `/api/v1/batch/nameservers`
- Auth: Public in current code

Request body:
```json
{
  "domain_ids": [101, 102],
  "nameservers": ["ns1.example.com", "ns2.example.com"]
}
```

Response example:
```json
{
  "total": 2,
  "results": [
    {
      "domain_id": 101,
      "domain_name": "example.com",
      "status": "success",
      "nameservers": ["ns1.example.com", "ns2.example.com"]
    }
  ]
}
```

Note:
- Current code writes nameservers into the local database after creating adapter context.
- It does not call a provider API to push nameserver changes upstream.

## 9. Export APIs

### 9.1 Export domains
- Method: `GET`
- Path: `/api/v1/export/domains`
- Auth: Public in current code

Query params:
- `format`: `csv` or `xlsx`, default `csv`
- `platform`: optional
- `status`: optional
- `search`: optional

Examples:
```bash
curl -L 'http://super-domains.localities.site/api/v1/export/domains?format=csv' -o domains.csv
curl -L 'http://super-domains.localities.site/api/v1/export/domains?format=xlsx&platform=cloudflare' -o domains.xlsx
```

Response:
- CSV file download or XLSX file download

### 9.2 Export DNS records of a domain
- Method: `GET`
- Path: `/api/v1/export/dns/{domain_id}`
- Auth: Public in current code

Query params:
- `format`: `csv` or `xlsx`, default `csv`

Examples:
```bash
curl -L 'http://super-domains.localities.site/api/v1/export/dns/101?format=csv' -o dns_101.csv
curl -L 'http://super-domains.localities.site/api/v1/export/dns/101?format=xlsx' -o dns_101.xlsx
```

## 10. Report APIs

### 10.1 Overview report
- Method: `GET`
- Path: `/api/v1/reports/overview`
- Auth: Authenticated

Response example:
```json
{
  "total_domains": 500,
  "total_accounts": 12,
  "total_platforms": 6,
  "domains_by_status": {
    "active": 480,
    "expired": 20
  },
  "domains_by_platform": {
    "cloudflare": 300,
    "porkbun": 200
  },
  "expiry_timeline": [],
  "recent_syncs": []
}
```

### 10.2 Expiry report
- Method: `GET`
- Path: `/api/v1/reports/expiry`
- Auth: Authenticated

Query params:
- `days`: int, default `90`, range `1`-`365`

Response example:
```json
{
  "critical": [
    {
      "domain_name": "soon-expire.com",
      "platform": "cloudflare",
      "account": "main-account",
      "expiry_date": "2026-04-08",
      "days_left": 1
    }
  ],
  "warning": [],
  "notice": [],
  "total": 1
}
```

### 10.3 Platform report
- Method: `GET`
- Path: `/api/v1/reports/platforms`
- Auth: Authenticated

Response example:
```json
{
  "items": [
    {
      "platform": "cloudflare",
      "domain_count": 300,
      "avg_expiry": "2026-08-01",
      "auto_renew_rate": 0.82,
      "sync_success_rate": 0.97
    }
  ]
}
```

## 11. User management APIs

### 11.1 List users
- Method: `GET`
- Path: `/api/v1/users`
- Auth: Admin

Response example:
```json
[
  {
    "id": 1,
    "username": "admin",
    "display_name": "Admin",
    "email": "admin@example.com",
    "role": "admin",
    "is_active": true,
    "auth_source": "local",
    "created_at": "2026-04-01T08:00:00"
  }
]
```

### 11.2 Update user
- Method: `PUT`
- Path: `/api/v1/users/{user_id}`
- Auth: Admin

Request body:
```json
{
  "role": "viewer",
  "is_active": true
}
```

Notes:
- `role` currently supports `admin` and `viewer`
- Any other fields in body are ignored by current code

Response:
```json
{
  "message": "更新成功"
}
```

## 12. Data schema summary

### 12.1 PlatformAccountCreate
```json
{
  "platform": "string, required, max 32",
  "account_name": "string|null, max 100",
  "credentials": {},
  "config": {}
}
```

### 12.2 PlatformAccountUpdate
```json
{
  "account_name": "string|null",
  "credentials": {},
  "config": {},
  "is_active": true
}
```

### 12.3 DnsRecordCreate
```json
{
  "record_type": "string, required, max 20",
  "name": "string, required, max 255",
  "content": "string, required",
  "ttl": 3600,
  "priority": null,
  "proxied": null
}
```

### 12.4 DnsRecordUpdate
```json
{
  "content": "string|null",
  "ttl": 120,
  "priority": null,
  "proxied": true
}
```

### 12.5 AlertRuleCreate
```json
{
  "name": "string, required, max 100",
  "rule_type": "string, required, max 30",
  "days_before": 7,
  "is_enabled": true,
  "channels": ["feishu"],
  "recipients": ["hook-url"],
  "apply_to_all": true,
  "specific_platforms": ["cloudflare"],
  "specific_domains": [101, 102],
  "excluded_platforms": [],
  "severity": "warning",
  "schedule": {
    "type": "manual",
    "time": "09:00:00"
  }
}
```

### 12.6 AlertRuleUpdate
Same fields as `AlertRuleCreate`, but all optional.

## 13. Automation examples

### 13.1 Login and save token
```bash
TOKEN=$(curl -s -X POST 'http://super-domains.localities.site/api/v1/auth/login' \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"your-password"}' | jq -r '.access_token')
```

### 13.2 Sync one account
```bash
curl -X POST 'http://super-domains.localities.site/api/v1/platforms/10/sync' \
  -H "Authorization: Bearer $TOKEN"
```

### 13.3 Query manageable domains
```bash
curl 'http://super-domains.localities.site/api/v1/domains?dns_manageable_only=true&page=1&page_size=100' \
  -H "Authorization: Bearer $TOKEN"
```

### 13.4 Sync DNS of a single domain
```bash
curl -X POST 'http://super-domains.localities.site/api/v1/dns/101/sync' \
  -H "Authorization: Bearer $TOKEN"
```

### 13.5 Export domains
```bash
curl -L 'http://super-domains.localities.site/api/v1/export/domains?format=csv' \
  -H "Authorization: Bearer $TOKEN" \
  -o domains.csv
```

## 14. Notes and caveats

- Some read endpoints are currently not protected by login in code, even though from a security perspective they may be expected to be protected.
- `POST /api/v1/batch/sync` does not execute full sync; it only marks account status as `syncing`.
- `POST /api/v1/batch/nameservers` updates local database values and does not push nameserver changes to registrar/provider APIs.
- Runtime response shapes of some service-driven endpoints may include additional fields not declared in schema files.
- There are schema files for transfer/report extras in the codebase, but no transfer API routes are currently mounted under `/api/v1`.
