# CCR — Claude Code Remote

## Table of Contents

1. [Overview](#overview)
2. [System Topology](#system-topology)
3. [Resource Model](#resource-model)
4. [Shared Storage](#shared-storage)
5. [Auth & Security](#auth--security)
6. [CLAUDE.md Layering](#claudemd-layering)
7. [Components](#components)
   - [CC Session Docker Image](#1-cc-session-docker-image)
   - [CCR Agent](#2-ccr-agent)
   - [CCR CLI](#3-ccr-cli)
   - [Monitoring Service](#4-monitoring-service)
8. [Fail-Safe Design](#fail-safe-design)
9. [Developer Workflow](#developer-workflow)
10. [Infrastructure](#infrastructure)
11. [Build Plan](#build-plan)

---

## Overview

CCR (Claude Code Remote) is a system for running Claude Code on dedicated servers while developers work from any device. It solves the problem of multi-device development without triggering account-sharing detection, while providing team-level resource management, usage tracking, and access control.

### Problem Statement

- Developers work from multiple devices (laptop, desktop, remote machines)
- Running Claude Code from each device appears as account sharing to Anthropic
- Teams need to share a pool of Claude Code subscriptions across members
- No existing solution provides legitimate multi-device/multi-user CC management

### Design Principles

1. **Legitimate usage** — One CC auth per server, one server per account. No OAuth proxying or API spoofing.
2. **Fail-safe** — Every component can go down without stopping active work. Degrade gracefully, never hard-fail.
3. **Simple servers** — CC servers are thin: Docker + shared filesystem mount + agent container. All logic is in Docker images.
4. **Auth never leaks** — Credentials exist only in ephemeral tmpfs inside containers. Never persisted to shared storage.
5. **Developer-friendly** — `ccr up proj-foo` and you're working. Everything else is automatic.

---

## System Topology

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Monitoring Service                                  │
│                (standalone, any host/cloud)                            │
│                                                                       │
│  Go binary + SQLite + embedded web dashboard                          │
│  Receives heartbeats, assigns servers, tracks usage                   │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
  ┌─────────────────────────────┼──────────────────────────────┐
  │                             │                               │
  ▼                             ▼                               ▼
┌──────────────────┐  ┌──────────────────┐           ┌──────────────────┐
│ Server 1         │  │ Server 2         │           │ Server N         │
│                  │  │                  │           │                  │
│ Docker engine    │  │ Docker engine    │    ...    │ Docker engine    │
│ NFS at /home     │  │ NFS at /home     │           │ NFS at /home     │
│                  │  │                  │           │                  │
│ ┌──────────────┐ │  │ ┌──────────────┐ │           │ ┌──────────────┐ │
│ │ ccr-agent    │ │  │ │ ccr-agent    │ │           │ │ ccr-agent    │ │
│ │ (always-on)  │ │  │ │ (always-on)  │ │           │ │ (always-on)  │ │
│ └──────────────┘ │  │ └──────────────┘ │           │ └──────────────┘ │
│                  │  │                  │           │                  │
│ ┌──────────────┐ │  │ ┌──────────────┐ │           │                  │
│ │ CC session   │ │  │ │ CC session   │ │           │                  │
│ │ (on-demand)  │ │  │ │ (on-demand)  │ │           │                  │
│ └──────────────┘ │  │ └──────────────┘ │           │                  │
│ ┌──────────────┐ │  │                  │           │                  │
│ │ CC session   │ │  │                  │           │                  │
│ │ (on-demand)  │ │  │                  │           │                  │
│ └──────────────┘ │  │                  │           │                  │
└──────────────────┘  └──────────────────┘           └──────────────────┘

Developer laptops:
  ccr CLI → monitoring API → SSH to assigned server → tmux → Claude Code
```

---

## Resource Model

| Resource | Quantity | Mapping |
|----------|----------|---------|
| Claude accounts | N (e.g. 10) | 1 account per server |
| CC servers | N (matches accounts) | Always-on, not auto-scaled |
| Concurrent sessions per account | ~10 | Based on Claude rate limits |
| Total concurrent sessions | N × 10 (e.g. 100) | Shared across all developers |
| Developers | M (e.g. 5) | Each has Unix user on all servers via shared FS |
| Projects | Unlimited | Stored on shared FS, accessible from any server |

Servers are not auto-scaled because each server is bound to a specific Claude account. Adding capacity means adding a new subscription + server pair.

---

## Shared Storage

All developer home directories and project code live on a shared network filesystem mounted on every CC server. This is required because a developer may be assigned to any server — their code and CC history must be accessible everywhere.

### Why NFS (EFS), not block storage (EBS)?

| | EBS (block storage) | EFS (NFS file system) |
|---|---|---|
| **Multi-attach** | No — one instance at a time | Yes — unlimited instances |
| **What it is** | Virtual hard drive for one machine | Shared network drive |
| **Analogy** | USB drive plugged into one computer | Google Drive / NAS |
| **For CCR** | Won't work — need 10 servers sharing one filesystem | Exactly what we need |

EBS is fast but single-attach. EFS is slightly slower (~milliseconds) but mountable by all servers simultaneously. For source code I/O this latency is negligible.

### Cloud Provider Equivalents

| Provider | Service | Protocol | Multi-attach |
|----------|---------|----------|-------------|
| AWS | EFS | NFS 4.1 | Unlimited |
| GCP | Filestore | NFS | Unlimited |
| Azure | Azure Files | NFS/SMB | Unlimited |

### Directory Layout

```
/home/
├── alice/
│   ├── .ccr/
│   │   ├── settings.json       # CC user preferences
│   │   ├── CLAUDE.md           # personal CC instructions
│   │   └── projects/           # CC conversation history
│   │       └── <hash>/
│   │           └── conversations/
│   └── projects/
│       ├── proj-a/             # git clone
│       ├── proj-b/
│       └── ...
├── bob/
│   ├── .ccr/
│   └── projects/
└── ...
```

### What Lives Where

| Data | Location | Why |
|------|----------|-----|
| Source code | NFS `/home/<user>/projects/` | Accessible from any server |
| CC conversation history | NFS `/home/<user>/.ccr/projects/` | Persists across server failover |
| CC user settings | NFS `/home/<user>/.ccr/settings.json` | Consistent across servers |
| Personal CLAUDE.md | NFS `/home/<user>/.ccr/CLAUDE.md` | Consistent across servers |
| CC auth credentials | Local `/opt/ccr/auth/` per server | **Never on shared storage** |
| Team CLAUDE.md | Local `/opt/ccr/shared/CLAUDE.md` | Same on all servers (provisioned) |
| node_modules, .venv, build artifacts | Container-local tmpfs or volume | Too slow over NFS, not portable |
| Docker images | Local | Pulled from registry |

### Performance Note

NFS is fast enough for source code reads/writes and git operations. However, dependency directories (`node_modules`, `.venv`, `target/`) perform poorly over NFS due to many small file accesses. The CC session container should use a local volume or tmpfs for these, with the project's lockfile driving installs inside the container.

---

## Auth & Security

### The Problem

Claude Code expects its auth at `~/.claude/credentials.json`. In CCR:
- `~/.claude/` is on shared NFS — credentials must NOT live there
- Multiple developers share the same CC account on a server — credentials must be isolated from users
- Credentials must not persist after a session ends

### Solution: Ephemeral Tmpfs + Docker Mounts

Each CC session container gets credentials injected via a protected Docker mount, assembled into a tmpfs directory that exists only for the container's lifetime.

```
Container startup:

  /run/secrets/credentials.json     ← Docker bind mount, RO, from /opt/ccr/auth/
        │
        │ entrypoint.sh copies to:
        ▼
  /tmp/claude-config-<pid>/         ← tmpfs, ephemeral
  ├── credentials.json              ← copied from secret, 400 perms
  ├── settings.json                 ← from user's NFS home
  ├── projects/                     ← symlink → user's NFS .ccr/projects/
  └── CLAUDE.md                     ← merged (team + personal)

  CLAUDE_CONFIG_DIR=/tmp/claude-config-<pid>/
        │
        ▼
  claude starts, reads credentials, works normally

Container stops:
  tmpfs destroyed, credentials gone
```

### Host-Level Protection

On each CC server:

```
/opt/ccr/auth/
└── credentials.json        # 600 root:root
```

- Owned by root, mode 600
- Only the Docker daemon (running as root) can mount it into containers
- No developer Unix user can read it directly on the host
- Inside the container, the entrypoint runs briefly as root to copy the credential, then drops to the developer's UID

### Credential Rotation

1. Re-authenticate Claude Code on the server (one-time interactive OAuth)
2. Copy new `credentials.json` to `/opt/ccr/auth/`
3. Restart active session containers (they pick up new credentials on next start)
4. No developer action needed

### What Developers CAN See

Inside a running session container, the developer can technically `cat $CLAUDE_CONFIG_DIR/credentials.json`. This is acceptable because:

1. These are team members with legitimate access
2. The credentials are for a shared team account, not personal
3. The credentials are ephemeral (gone when container stops)
4. Audit trail tracks who ran which session
5. If this is a concern, the container can run CC via a wrapper that unlinks the credentials file after CC reads it on startup (CC caches auth in memory)

### What Developers CANNOT Do

- Read credentials on the host filesystem (root-only)
- Access credentials from NFS (never stored there)
- Access another server's credentials (different host, different account)
- Persist credentials beyond their session lifetime

### SSH Access

Developers SSH to CC servers using their personal SSH keys. The `ccr` CLI automates this — developers don't need to know which server they're on.

```
~/.ssh/authorized_keys on NFS → available on all servers
```

### Teammate Sharing

Temporary access to another developer's CC session uses tmux socket permissions:

```bash
# Owner grants access
ccr share proj-foo bob 2h

# What happens:
# 1. tmux session socket: /tmp/ccr-alice-proj-foo.sock
# 2. setfacl -m u:bob:rwx /tmp/ccr-alice-proj-foo.sock
# 3. at now + 2h: setfacl -x u:bob /tmp/ccr-alice-proj-foo.sock

# Bob connects (from any device)
ccr attach proj-foo  # SSH to same server, attach to shared tmux

# After 2h: access automatically revoked
```

### Network Security

- CC servers in a private subnet (VPC)
- SSH access via bastion host or VPN (Tailscale/WireGuard)
- Monitoring service accessible from private network only (or behind auth if exposed)
- NFS mount uses encryption in transit (TLS)
- No CC server has a public IP

---

## CLAUDE.md Layering

Three layers merged at session start:

### Layer 1: Team-Wide (`/opt/ccr/shared/CLAUDE.md`)

Managed centrally, provisioned to all servers. Sets team standards.

```markdown
# Team Standards

## Code Quality
- Run tests before committing. If no tests exist for changed code, write them.
- Use conventional commits: feat/fix/refactor/docs/test/chore
- No commented-out code. Delete it; git has history.

## Languages
- Python: use uv for package management. Type hints required.
- TypeScript: strict mode. No any unless justified.
- Go: go vet + staticcheck must pass.

## Security
- Never commit secrets, .env files, or credentials.
- Validate all external input at system boundaries.
- Use parameterized queries for SQL.

## Git
- Scope commits tightly. One concern per commit.
- Don't push to main directly. Use feature branches.

## Claude Code Behavior
- Don't add features beyond what was asked.
- Read existing code before modifying.
- Prefer editing existing files over creating new ones.
```

### Layer 2: Per-Developer (`/home/<user>/.ccr/CLAUDE.md`)

Each developer maintains their own preferences on NFS.

```markdown
# Alice — Preferences
- Concise output. Skip obvious explanations.
- I work primarily on backend (Go + Python).
- When I say "test it", run the specific test file, not the full suite.
```

### Layer 3: Per-Project (`/home/<user>/projects/<project>/CLAUDE.md`)

Lives in the git repo. CC reads this natively — no merging needed.

```markdown
# proj-foo
## Stack
Go 1.24, Gin, Ent ORM, Postgres 17
## Commands
- Test: go test ./...
- Lint: golangci-lint run
- Dev: go run ./cmd/server
```

### Merge Logic (entrypoint.sh)

```bash
{
  cat /opt/ccr/shared/CLAUDE.md
  echo ""
  echo "# ─── Personal Preferences ───"
  cat "/home/$CCR_USER/.ccr/CLAUDE.md" 2>/dev/null || true
} > "$CLAUDE_CONFIG_DIR/CLAUDE.md"
```

Layer 3 is not merged — CC discovers it automatically from the project working directory.

---

## Components

CCR has four components: a Docker image, a server agent, a CLI, and a monitoring service.

### 1. CC Session Docker Image

A Docker image containing Claude Code, common dev tools, and an entrypoint that handles auth setup and CLAUDE.md merging.

**Contents:**

```dockerfile
Base: node:24-slim

Installed:
  - Claude Code (@anthropic-ai/claude-code, pinned version)
  - git, tmux, openssh-client
  - build-essential, python3, python3-venv
  - ripgrep, fd-find, jq
  - Go toolchain (if team uses Go)
  - uv (Python package manager)
  - fnm (Node version manager)

Custom:
  - /usr/local/bin/entrypoint.sh
```

**Entrypoint flow:**

```
1. Create tmpfs config dir: /tmp/claude-config-$$/
2. Copy /run/secrets/credentials.json → config dir (400 perms)
3. Symlink projects/ → /home/$CCR_USER/.ccr/projects/
4. Copy user settings.json from NFS if exists
5. Merge CLAUDE.md (team + personal layers)
6. Set CLAUDE_CONFIG_DIR
7. cd /home/$CCR_USER/projects/$CCR_PROJECT
8. git pull --ff-only (if .git exists) or git clone (if CCR_GIT_URL set)
9. exec claude "$@"
```

**Container lifecycle:**

```
Created by:   ccr-agent on the host, via Docker API
Runs as:      developer's UID:GID (--user flag)
Mounts:
  /home/<user>              → NFS (user's home dir)
  /run/secrets/creds.json   → /opt/ccr/auth/credentials.json:ro (host local)
  /opt/ccr/shared           → /opt/ccr/shared:ro (team CLAUDE.md)
Environment:
  CCR_USER=alice
  CCR_PROJECT=proj-foo
  CCR_GIT_URL=git@github.com:team/proj-foo.git  (optional, for first clone)
  CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
Resources:
  --cpus=4 --memory=8g (configurable)
Destroyed by: ccr-agent (on ccr down, or idle timeout)
```

**Image versioning:**

- Images tagged with CC version: `ccr:cc-2.1.90`, `ccr:latest`
- Pushed to ECR/GCR, pulled by all servers
- Upgrading CC across the fleet = push new image, restart active sessions

### 2. CCR Agent

A Go binary running as an always-on Docker container on each CC server. Manages session containers, reports status, and parses usage data.

**Responsibilities:**

| Function | How |
|----------|-----|
| Session lifecycle | Start/stop CC session containers via Docker API |
| Heartbeat | POST server status to monitoring service every 30s |
| Heartbeat buffering | Write to /var/ccr/buffer/ when monitoring is unreachable, flush on reconnect |
| Usage parsing | Watch CC conversation files on NFS, extract token counts |
| Idle detection | Track last activity per session, stop containers after idle timeout |
| tmux management | Create tmux sessions on host, manage socket permissions for sharing |

**Container configuration:**

```yaml
image: ccr-agent:latest
restart: always
volumes:
  - /var/run/docker.sock:/var/run/docker.sock   # manage CC containers
  - /home:/home:ro                               # read CC conversation data
  - /opt/ccr:/opt/ccr:ro                         # server config + auth
  - /var/ccr:/var/ccr                             # buffer storage (local disk)
environment:
  - CCR_SERVER_ID=s1
  - CCR_MONITORING_URL=http://monitoring:8080
  - CCR_MAX_CONCURRENT=10
  - CCR_IDLE_TIMEOUT=4h
  - CCR_IMAGE=ccr:latest
```

**Agent API (Unix Socket at `/var/ccr/agent.sock`):**

```
POST /session/start   {user, project, git_url?}  → {container_id, tmux_socket}
POST /session/stop    {user, project}
GET  /session/list    → [{user, project, status, usage}]
POST /session/share   {project, target_user, ttl}
POST /session/revoke  {project, target_user}
```

**Heartbeat payload:**

```json
{
  "server_id": "s1",
  "timestamp": "2026-04-08T10:30:00Z",
  "health": {
    "cpu_pct": 34,
    "mem_used_gb": 12.4,
    "mem_total_gb": 32,
    "efs_healthy": true,
    "docker_healthy": true
  },
  "account": {
    "id": "acct-1",
    "max_concurrent": 10
  },
  "sessions": [
    {
      "user": "alice",
      "project": "proj-a",
      "container": "ccr-session-alice-proj-a",
      "status": "active",
      "started_at": "2026-04-08T09:15:00Z",
      "last_activity": "2026-04-08T10:29:45Z",
      "usage": {
        "input_tokens": 142300,
        "output_tokens": 89100,
        "cache_read_tokens": 52000,
        "cache_write_tokens": 18000,
        "models_used": ["claude-opus-4-6", "claude-sonnet-4-6"],
        "tool_calls": 234,
        "cost_estimate_usd": 4.82
      }
    }
  ]
}
```

**Heartbeat buffering:**

When monitoring is unreachable, heartbeats are written to `/var/ccr/buffer/<timestamp>.json`. On reconnect, buffered heartbeats are flushed oldest-first. Buffer retention: 24h max, 100MB max.

### 3. CCR CLI

A Go binary installed on developer laptops. Talks to the monitoring service for server assignment, then SSHes to the assigned server.

**Commands:**

```
Session management:
  ccr up <project> [--git=<url>]     Start a session (assign server, start container, attach)
  ccr down <project>                  Stop a session
  ccr attach <project>                Reconnect to a running session
  ccr ls                              List my active sessions
  ccr ls --all                        List all team sessions

Sharing:
  ccr share <project> <user> [ttl]    Grant teammate tmux access (default: 2h)
  ccr revoke <project> <user>         Revoke access

Sync:
  ccr sync <project> [local-path]     Start mutagen sync to local machine
  ccr sync-stop <project>             Stop mutagen sync
  ccr sync-status                     Show sync status

Monitoring:
  ccr usage                           My token usage (today)
  ccr usage --week                    My usage this week
  ccr usage --team                    Team usage
  ccr status                          Server pool status
  ccr dashboard                       Open web dashboard in browser

Admin:
  ccr config                          Show/edit CLI config
```

**CLI flow — `ccr up proj-foo`:**

```
1. POST monitoring:8080/session/start {user: alice, project: proj-foo}
   Response: {server: s3, host: 10.0.1.13} (or {queued: true, position: 2})

2. SSH to s3:
   ssh -t 10.0.1.13 "ccr-agent-ctl session start --user=alice --project=proj-foo"
   
   On s3, the agent:
   a. Creates container ccr-session-alice-proj-foo
   b. Creates tmux session with socket at /tmp/ccr-alice-proj-foo.sock
   c. Container runs entrypoint → claude starts

3. Attach to tmux:
   ssh -t 10.0.1.13 "tmux -S /tmp/ccr-alice-proj-foo.sock attach"

4. Developer is now in Claude Code.
```

**Offline / fallback mode:**

When the monitoring service is unreachable:

1. Read `~/.ccr/cache/last_assignments.json` for last-known server mapping
2. SSH to the cached server for the requested project
3. If that fails, try servers from `~/.ccr/cache/server_list.json` in order
4. Log warning: "operating in offline mode, usage not tracked"
5. On next successful monitoring contact, sync state

**CLI config (`~/.ccr/config.yaml`):**

```yaml
monitoring_url: http://monitoring.internal:8080
ssh_user: alice
ssh_key: ~/.ssh/id_ed25519
ssh_bastion: bastion.internal       # optional jump host
default_git_org: git@github.com:myteam
mutagen_ignores:
  - ".DS_Store"
  - "*.pyc"
```

### 4. Monitoring Service

A Go binary with embedded SQLite and HTML dashboard. Single instance, runs anywhere.

**Responsibilities:**

| Function | Description |
|----------|-------------|
| Server assignment | Sticky-preferred, least-loaded fallback |
| Session tracking | Who is using what, where, since when |
| Usage aggregation | Token counts per user/project/server/time period |
| Health monitoring | Server health from heartbeats, stale detection |
| Web dashboard | Real-time view of the fleet |
| Heartbeat buffering | Accept out-of-order and buffered heartbeats |

**API:**

```
Session management:
  POST /api/session/start    {user, project}        → {server, host}
  POST /api/session/end      {user, project, server}
  GET  /api/session/find     ?user=&project=        → {server, host, status}
  GET  /api/session/list     ?user= (optional)      → [{user, project, server, status, usage}]

Server status:
  POST /api/heartbeat        (from agents)
  GET  /api/servers           → [{id, host, health, sessions, capacity}]

Usage:
  GET  /api/usage             ?user=&period=day|week|month  → {totals, breakdown}
  GET  /api/usage/team        ?period=day|week|month        → [{user, totals}]

Dashboard:
  GET  /dashboard             HTML dashboard
```

**Database schema (SQLite):**

```sql
CREATE TABLE servers (
    id          TEXT PRIMARY KEY,
    host        TEXT NOT NULL,
    account_id  TEXT NOT NULL,
    max_concurrent INTEGER DEFAULT 10,
    last_heartbeat DATETIME,
    health_json TEXT,
    status      TEXT DEFAULT 'healthy'  -- healthy, degraded, unreachable
);

CREATE TABLE sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user        TEXT NOT NULL,
    project     TEXT NOT NULL,
    server_id   TEXT NOT NULL REFERENCES servers(id),
    status      TEXT NOT NULL,      -- active, idle, stopped
    started_at  DATETIME NOT NULL,
    last_activity DATETIME,
    stopped_at  DATETIME,
    UNIQUE(user, project, server_id, started_at)
);

CREATE TABLE sticky_affinity (
    user        TEXT PRIMARY KEY,
    server_id   TEXT NOT NULL REFERENCES servers(id),
    last_used   DATETIME NOT NULL
);

CREATE TABLE usage_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER REFERENCES sessions(id),
    user        TEXT NOT NULL,
    project     TEXT NOT NULL,
    server_id   TEXT NOT NULL,
    recorded_at DATETIME NOT NULL,
    input_tokens    INTEGER DEFAULT 0,
    output_tokens   INTEGER DEFAULT 0,
    cache_read_tokens  INTEGER DEFAULT 0,
    cache_write_tokens INTEGER DEFAULT 0,
    models_used TEXT,               -- JSON array
    tool_calls  INTEGER DEFAULT 0,
    cost_estimate_usd REAL DEFAULT 0
);

CREATE TABLE heartbeat_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id   TEXT NOT NULL,
    received_at DATETIME NOT NULL,
    payload     TEXT NOT NULL
);
```

**Assignment algorithm:**

```
assign(user, project):

  # 1. Reconnect: existing active session for this user+project?
  session = find_active_session(user, project)
  if session and server_healthy(session.server):
    return session.server

  # 2. Sticky: user has preferred server with capacity?
  affinity = get_sticky_affinity(user)
  if affinity and server_healthy(affinity.server) and has_capacity(affinity.server):
    return affinity.server

  # 3. Co-locate: user has other sessions on a server with capacity?
  servers_with_user = find_servers_with_active_sessions(user)
  for s in servers_with_user:
    if server_healthy(s) and has_capacity(s):
      return s

  # 4. Least loaded: pick healthiest server with most free slots
  candidates = all_healthy_servers()
    .filter(has_capacity)
    .sort_by(available_slots DESC, cpu_pct ASC)
  if candidates:
    return candidates[0]

  # 5. No capacity
  return {queued: true, position: queue_length + 1}
```

After assignment, update `sticky_affinity` table.

**Health detection:**

```
healthy → (no heartbeat for 60s) → degraded → (no heartbeat for 90s) → unreachable
heartbeat received at any point → healthy
```

Unreachable servers are skipped during assignment.

**Dashboard mockup:**

```
┌─────────────────────────────────────────────────────────────┐
│ CCR Dashboard                                     [refresh] │
├──────────┬────────┬──────────┬──────────────────────────────┤
│ Server   │ Load   │ Sessions │ Users                        │
├──────────┼────────┼──────────┼──────────────────────────────┤
│ s1  ●    │ 3/10   │ ██░░░░░░ │ alice(2) bob(1)             │
│ s2  ●    │ 7/10   │ ██████░░ │ carol(4) dave(3)            │
│ s3  ●    │ 1/10   │ █░░░░░░░ │ alice(1)                    │
│ s4  ○    │ 0/10   │ ░░░░░░░░ │ —                           │
│ s5  ◉    │ ???    │ ???????? │ unreachable since 10:42      │
├──────────┴────────┴──────────┴──────────────────────────────┤
│ Token Usage (today)                                          │
│ ┌──────────┬──────────┬───────────┬────────────┬───────────┐│
│ │ User     │ In       │ Out       │ Cache      │ Est. Cost ││
│ ├──────────┼──────────┼───────────┼────────────┼───────────┤│
│ │ alice    │ 142.3K   │ 89.1K     │ 52.0K      │ $4.82    ││
│ │ bob      │ 38.0K    │ 21.4K     │ 12.1K      │ $1.24    ││
│ │ carol    │ 210.5K   │ 156.2K    │ 88.3K      │ $8.41    ││
│ │ dave     │ 15.2K    │ 8.7K      │ 3.1K       │ $0.52    ││
│ │ eve      │ 0        │ 0         │ 0          │ $0.00    ││
│ └──────────┴──────────┴───────────┴────────────┴───────────┘│
│ Active Sessions                                              │
│ ┌───────┬──────────┬────────┬─────────┬────────┬───────────┐│
│ │ User  │ Project  │ Server │ Status  │ Age    │ Tokens    ││
│ ├───────┼──────────┼────────┼─────────┼────────┼───────────┤│
│ │ alice │ proj-a   │ s1     │ active  │ 1h15m  │ 89K      ││
│ │ alice │ proj-b   │ s1     │ idle 5m │ 3h02m  │ 142K     ││
│ │ alice │ proj-c   │ s3     │ active  │ 12m    │ 23K      ││
│ │ bob   │ proj-d   │ s1     │ active  │ 45m    │ 38K      ││
│ │ carol │ proj-e   │ s2     │ active  │ 2h30m  │ 210K     ││
│ └───────┴──────────┴────────┴─────────┴────────┴───────────┘│
└─────────────────────────────────────────────────────────────┘
```

---

## Fail-Safe Design

Every component can fail independently without stopping active work.

### Failure Matrix

| Component | Failure Mode | Impact | Recovery |
|-----------|-------------|--------|----------|
| Monitoring service | Down | No new session assignment. No dashboard. | CLI uses cached state. Agents buffer heartbeats. |
| CC server | Crash/reboot | Active sessions on that server lost. | Users re-run `ccr up`. Files safe on NFS. Sessions restart on another server. |
| CC server | Overloaded | Slow CC responses, high CPU. | Agent reports health. Monitoring routes new sessions elsewhere. |
| NFS (EFS) | Down | Everything stops. | Cloud provider SLA (99.99%). Accept as infrastructure risk. |
| Docker on a server | Daemon crash | All containers on that server die. | Docker restart policy recovers agent. Users re-attach sessions. |
| Network (server↔monitoring) | Partitioned | Agent can't send heartbeats. | Agent buffers locally. Monitoring marks server degraded after 60s. |
| Network (dev↔server) | SSH drops | tmux session persists. Work in progress safe. | Dev reconnects with `ccr attach`. |
| CC session container | OOM / crash | That one session dies. | User runs `ccr up` again. Conversation history on NFS is safe. |

### Monitoring Service Failure

**What breaks:** `ccr up` can't get a server assignment. Dashboard unavailable. Usage stops aggregating (but heartbeats are buffered).

**What keeps working:** All active CC sessions. Reconnection to existing sessions. Agents buffer heartbeats to local disk.

**CLI fallback:**

```
ccr up proj-foo:
  1. Try POST monitoring/api/session/start
  2. Timeout after 3s → enter offline mode
  3. Read ~/.ccr/cache/last_assignments.json
  4. SSH to cached server, start session directly via agent socket
  5. If cached server unreachable, try servers from ~/.ccr/cache/server_list.json
  6. Log warning: "offline mode — session not tracked in monitoring"
```

**Cache files (updated on every successful monitoring interaction):**

```
~/.ccr/cache/
├── last_assignments.json     # {project: {server, host, last_used}}
├── server_list.json          # [{id, host, last_known_status}]
└── cache_updated_at          # timestamp
```

### CC Server Failure

**Detection:** Agent misses 3 heartbeats (90s) → monitoring marks server `unreachable`. New assignments skip it.

**Impact:** Active sessions lost (tmux gone, containers gone). Conversation history safe (NFS). Source code safe (NFS). No credential exposure (tmpfs gone).

**Recovery:** Developer runs `ccr up proj-foo` again → gets assigned to a different healthy server → new container starts → CC picks up conversation history from NFS.

### Agent Heartbeat Buffering

```
Normal:     collect_status() → POST /heartbeat → prune old buffer files
Monitoring unreachable: collect_status() → write /var/ccr/buffer/{timestamp}.json
Monitoring recovers:    POST current heartbeat → flush buffered files oldest-first
```

Buffer limits: 24h max age, 100MB max size, local disk only (not NFS).

### SSH Connection Drops

tmux is the key resilience mechanism. When SSH drops:
1. tmux session continues on the server
2. CC session continues inside the container
3. In-progress Claude response completes normally
4. Developer reconnects: `ccr attach proj-foo` → tmux attach

No work is lost.

### Graceful Degradation Summary

```
Full system healthy:
  CLI → monitoring → best server → SSH → agent → container → CC
  Agent → heartbeat → monitoring → dashboard + usage tracking

Monitoring down:
  CLI → cached server → SSH → agent → container → CC
  Agent → buffer heartbeats locally
  Dashboard unavailable, usage tracking paused (not lost)

One server down:
  CLI → monitoring → different server → SSH → agent → container → CC
  NFS data safe, conversation history safe

Network partition (dev ↔ server):
  tmux keeps session alive, CC keeps running
  Developer reconnects when network recovers

Agent down on a server:
  Active CC sessions keep running (containers are independent)
  No new sessions on that server, no heartbeats
  Monitoring marks degraded after 60s
  Docker restart policy restarts agent container
```

---

## Developer Workflow

### First-Time Setup

**1. Install the CLI:**

```bash
curl -fsSL https://your-registry/ccr/install.sh | bash
# or: go install github.com/yourteam/ccr/cmd/ccr@latest
```

**2. Configure:**

```bash
ccr config init
```

Creates `~/.ccr/config.yaml`:

```yaml
monitoring_url: http://monitoring.internal:8080
ssh_user: alice
ssh_key: ~/.ssh/id_ed25519
ssh_bastion: bastion.internal       # optional
default_git_org: git@github.com:myteam
mutagen_ignores:
  - ".DS_Store"
  - "*.pyc"
```

**3. Set personal CLAUDE.md (optional):**

Create `~/.ccr/CLAUDE.md` with your preferences. This syncs to NFS on first `ccr up`.

### Daily Usage

```bash
# Start working (first time — with git URL)
ccr up proj-foo --git=git@github.com:myteam/proj-foo.git

# Start working (subsequent — already cloned)
ccr up proj-foo

# Work on multiple projects simultaneously
ccr up proj-bar    # in another terminal
ccr up proj-baz    # in another terminal

# Check sessions
ccr ls

# Reconnect (after SSH drop or device switch)
ccr attach proj-foo

# Sync to local IDE (optional, uses Mutagen)
ccr sync proj-foo ~/Projects/proj-foo

# Share with teammate
ccr share proj-foo bob 2h

# Check usage
ccr usage
ccr usage --team

# Stop
ccr down proj-foo
```

### Git Workflow

Projects on NFS are normal git repos. Three options:

- **From CC session:** Claude Code commits directly. Push from inside the container.
- **From local via sync:** `ccr sync`, review in local IDE, commit and push locally.
- **From server directly:** SSH to server, `cd ~/projects/proj-foo`, commit and push.

### Switching Devices

1. Close laptop (SSH drops, tmux persists)
2. Open desktop
3. `ccr attach proj-foo` — back where you left off

### Edge Cases

**All servers full:**

```
$ ccr up proj-new
All servers at capacity (50/50 sessions active).
Queue position: 1. Estimated wait: ~15min.
Hint: close idle sessions with 'ccr down <project>'
```

**Server goes down while working:**

```
Connection to 10.0.1.13 closed.
$ ccr attach proj-foo
Session for proj-foo was on s3 (unreachable).
Starting new session on s1...
Note: previous conversation continues (history on NFS).
```

**Monitoring unreachable:**

```
$ ccr up proj-foo
Warning: monitoring unreachable. Using cached server assignment.
Connecting to s3 (last known)...
[works normally, usage not tracked]
```

---

## Infrastructure

### Server Requirements

**CC Servers (N servers, one per Claude account):**

| Resource | Minimum | Recommended | Notes |
|----------|---------|-------------|-------|
| CPU | 4 vCPU | 8 vCPU | CC sessions are CPU-light (waiting on API) |
| Memory | 8 GB | 16 GB | ~1GB per active CC session container |
| Disk | 50 GB | 100 GB | Docker images, buffer storage |
| Network | 1 Gbps | 1 Gbps | NFS traffic + API calls |

AWS example: `t3.xlarge` (4 vCPU, 16 GB).

**Monitoring Service:** 1 vCPU, 1 GB RAM, 10 GB disk. AWS example: `t3.micro`.

**Shared Storage (EFS):** General Purpose, Bursting throughput, encryption at rest + in transit, daily backups. ~1 GB per developer per 10 projects.

### AWS Reference Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ VPC (10.0.0.0/16)                                            │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Private Subnet A (10.0.1.0/24)                         │  │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐        │  │
│  │  │ S1   │ │ S2   │ │ S3   │ │ S4   │ │ S5   │        │  │
│  │  └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘        │  │
│  │     └────────┴────────┴────────┴────────┘              │  │
│  │              │ NFS mount                                │  │
│  │     ┌────────▼────────┐                                │  │
│  │     │     EFS         │                                │  │
│  │     │  /home/*        │                                │  │
│  │     └─────────────────┘                                │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Private Subnet B (10.0.2.0/24)                         │  │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐        │  │
│  │  │ S6   │ │ S7   │ │ S8   │ │ S9   │ │ S10  │        │  │
│  │  └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘        │  │
│  │     └────────┴────────┴────────┴────────┘              │  │
│  │              │ NFS mount (same EFS)                     │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Private Subnet C (10.0.3.0/24)                         │  │
│  │  ┌──────────────┐     ┌──────────────┐                 │  │
│  │  │ Monitoring   │     │ Bastion      │◄── Public IP    │  │
│  │  └──────────────┘     └──────────────┘                 │  │
│  └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Alternative: Tailscale Mesh

Instead of bastion + VPC complexity:
1. Install Tailscale on all servers + monitoring + developer laptops
2. Each server gets a stable Tailscale IP
3. Developers SSH directly — no bastion, no VPN config
4. ACL policies in Tailscale admin console

### Server Provisioning

Each CC server needs:

```
Base OS: Ubuntu 24.04 LTS
Packages: docker.io, nfs-common, acl, at, tmux

/opt/ccr/
├── auth/credentials.json     # CC account auth (600 root:root)
├── shared/CLAUDE.md           # team-wide CC instructions
└── agent.conf                 # server ID, monitoring URL

/var/ccr/buffer/               # heartbeat buffer (local disk)
/home/                         # NFS mount point
```

**CC account setup (one-time per server):**

```bash
docker run -it --rm -v /opt/ccr/auth:/root/.claude ccr:latest claude --login
chmod 600 /opt/ccr/auth/credentials.json
chown root:root /opt/ccr/auth/credentials.json
```

### Developer Onboarding

```bash
# 1. Create Unix user (on any server — NFS makes it visible everywhere)
sudo useradd -m -s /bin/bash alice
sudo -u alice mkdir -p /home/alice/.ccr /home/alice/projects /home/alice/.ssh

# 2. Add SSH key
echo "ssh-ed25519 AAAA... alice@laptop" | sudo tee -a /home/alice/.ssh/authorized_keys

# 3. Developer installs CLI on their laptop
curl -fsSL https://your-registry/ccr/install.sh | bash
ccr config init
```

### Cost Estimate (AWS, 10 servers)

| Component | Instance | Monthly Cost |
|-----------|----------|-------------|
| 10× CC servers | t3.xlarge (4 vCPU, 16 GB) | ~$1,200 |
| 1× Monitoring | t3.micro | ~$8 |
| 1× Bastion | t3.micro (or Tailscale, $0) | ~$8 |
| EFS | 50 GB, General Purpose | ~$15 |
| **Total infra** | | **~$1,230/mo** |
| 10× Claude Max subscriptions | $100/mo each | **$1,000/mo** |
| **Grand total** | | **~$2,230/mo** |

### Scaling

**Add capacity:** Purchase new Claude subscription → launch new EC2 → run CC OAuth → register in monitoring.

**Add developers:** Create Unix user on NFS → add SSH key → give them the CLI.

**Remove a server:** `ccr admin drain s5` → wait for sessions to finish → terminate instance → cancel subscription.

---

## Build Plan

Components listed in dependency order. Each phase is independently useful.

### Phase 1: Minimum Viable (manual server assignment)

No monitoring service. Developers SSH to a specific server and run CC.

**Deliverables:**
1. Dockerfile + entrypoint.sh — CC session image with auth setup, CLAUDE.md merging
2. Server setup script — cloud-init or Ansible
3. `ccr-agent-ctl` — shell script on each server for session lifecycle

**What you get:** Dockerized CC sessions, auth isolation, CLAUDE.md layering, teammate sharing via tmux, NFS-backed code and history.

**What's missing:** No automatic server assignment, no usage tracking, no dashboard.

### Phase 2: CLI + Monitoring

**Deliverables:**
4. `ccr-agent` (Go) — always-on container per server: heartbeat, usage parsing, session lifecycle via Docker API
5. `ccr-monitor` (Go) — monitoring service: heartbeat receiver, sticky assignment, SQLite, REST API
6. `ccr` CLI (Go) — developer laptop tool: `up/down/attach/ls`, monitoring client, SSH automation, offline cache

**What you get:** Automatic server assignment with sticky sessions, full CLI workflow, session tracking, offline fallback.

### Phase 3: Dashboard + Usage

**Deliverables:**
7. Web dashboard (embedded in `ccr-monitor`) — fleet overview, sessions, token usage, health
8. Usage reporting in CLI — `ccr usage` / `ccr usage --team`
9. Usage data pipeline — agent parses CC conversation files, sends with heartbeat, monitoring aggregates

### Phase 4: Sync + Polish

**Deliverables:**
10. Mutagen integration — `ccr sync` / `ccr sync-stop` / `ccr sync-status`
11. Auto-reconnect on server failure — `ccr attach` detects dead server, starts on new one
12. Session idle timeout — agent monitors activity, stops containers after idle period
13. Queue system — position/ETA when all servers full, notification when slot opens
14. Admin commands — `ccr admin add-server`, `drain`, `add-user`, `rotate-auth`

### Tech Stack

| Component | Language | Key Libraries |
|-----------|----------|--------------|
| CC session image | Dockerfile | node:24-slim |
| entrypoint.sh | Bash | — |
| ccr-agent | Go | Docker SDK, net/http |
| ccr-monitor | Go | net/http, SQLite (modernc), html/template |
| ccr CLI | Go | net/http, x/crypto/ssh, cobra |
| Dashboard | HTML | htmx (optional) |

All Go components compile to single static binaries.

### Repository Structure

```
ccr/
├── cmd/
│   ├── ccr/              # CLI binary
│   ├── ccr-agent/        # Server agent binary
│   └── ccr-monitor/      # Monitoring service binary
├── internal/
│   ├── agent/            # heartbeat, session, usage, docker
│   ├── monitor/          # assign, api, db, dashboard
│   ├── cli/              # up, attach, sync, cache
│   └── shared/           # types, config
├── docker/
│   ├── session/          # Dockerfile, entrypoint.sh
│   └── agent/            # Dockerfile
├── deploy/
│   ├── cloud-init.yaml
│   ├── terraform/
│   └── team-claude.md
├── web/templates/
├── docs/
├── go.mod
├── Makefile
└── README.md
```

### Estimated Effort

| Phase | Scope | Notes |
|-------|-------|-------|
| Phase 1 | Dockerfile, entrypoint, server script, agent-ctl | Usable immediately |
| Phase 2 | Agent, monitor, CLI | Makes it a real product |
| Phase 3 | Dashboard, usage pipeline | Visibility |
| Phase 4 | Sync, auto-reconnect, queue, admin | Polish |
