# Analytics — Backup & Restore Guide

This document covers how to back up and restore the `analytics.*` PostgreSQL schema.

---

## Overview

| Item | Detail |
|---|---|
| Tool | `pg_dump` / `pg_restore` (PostgreSQL 16) |
| Format | Custom (`-Fc`) — compressed, supports selective restore |
| Schema | `analytics.*` only (no other schemas touched) |
| Retention | 30 days (configurable via `BACKUP_RETAIN_DAYS`) |
| Schedule | Daily at 02:00 (cron) |
| Storage | `/backups/` inside the container (bind-mounted to host) |

---

## Scripts

| Script | Purpose |
|---|---|
| `analytics/scripts/backup.sh` | Dump `analytics.*` schema to `/backups/analytics_YYYYMMDD_HHMMSS.dump` |
| `analytics/scripts/restore.sh` | Restore from a `.dump` file — drops and recreates the schema |

---

## Environment Variables

Both scripts read from `.env` (project root) if the variable is not already in the shell environment.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | _(required)_ | PostgreSQL connection string, e.g. `postgresql://postgres:postgres@localhost:5432/quantdinger` |
| `BACKUP_DIR` | `/backups` | Directory where dump files are stored |
| `BACKUP_RETAIN_DAYS` | `30` | Delete backups older than this many days |
| `FORCE_RESTORE` | `false` | Set to `true` to skip the interactive confirmation prompt in `restore.sh` |

---

## Manual Backup

### Inside Docker

```bash
docker exec analytics-api /app/scripts/backup.sh
```

### On the host (with pg_dump installed)

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/quantdinger"
export BACKUP_DIR="./backups"
./analytics/scripts/backup.sh
```

The backup file will be written to `$BACKUP_DIR/analytics_YYYYMMDD_HHMMSS.dump`.

---

## Setting Up the Cron Job (Daily 2am)

### Option A — Host cron

Add to the host's crontab (`crontab -e`):

```cron
0 2 * * * docker exec analytics-api /app/scripts/backup.sh >> /var/log/analytics-backup.log 2>&1
```

### Option B — Cron inside the container

If you run a dedicated backup container (see Docker Compose section below), add to its crontab:

```cron
0 2 * * * /app/scripts/backup.sh >> /var/log/analytics-backup.log 2>&1
```

### Option C — Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: analytics-backup
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: analytics:latest
              command: ["/app/scripts/backup.sh"]
              env:
                - name: DATABASE_URL
                  valueFrom:
                    secretKeyRef:
                      name: analytics-secrets
                      key: DATABASE_URL
                - name: BACKUP_DIR
                  value: /backups
              volumeMounts:
                - name: backups
                  mountPath: /backups
          restartPolicy: OnFailure
          volumes:
            - name: backups
              persistentVolumeClaim:
                claimName: analytics-backups-pvc
```

---

## Docker Volume Mount for Backups

Add a named volume and mount it into the `analytics-api` container so backups persist on the host.

In `docker-compose.yml`:

```yaml
services:
  analytics-api:
    # ... existing config ...
    volumes:
      - ../fincept-qt/scripts:/app/scripts:ro
      - analytics_backups:/backups          # ← add this line

  # Optional: dedicated backup/cron container
  analytics-backup:
    image: postgres:16-alpine               # has pg_dump built in
    container_name: analytics-backup
    profiles: ["backup"]                    # only starts with --profile backup
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:-postgres}@postgres:5432/${POSTGRES_DB:-quantdinger}
      BACKUP_DIR: /backups
      BACKUP_RETAIN_DAYS: ${BACKUP_RETAIN_DAYS:-30}
    volumes:
      - ./scripts:/app/scripts:ro
      - analytics_backups:/backups
    entrypoint: >
      sh -c 'echo "0 2 * * * /app/scripts/backup.sh >> /var/log/analytics-backup.log 2>&1" | crontab -
             crond -f -l 2'
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - analytics-net

volumes:
  analytics_backups:    # ← add this named volume
```

To start with the backup service:

```bash
docker-compose --profile backup up -d
```

---

## Restoring from a Backup

### Step 1 — List available backups

```bash
# Inside container
docker exec analytics-api ls -lh /backups/

# On host (if volume is bind-mounted)
ls -lh ./backups/
```

### Step 2 — Run the restore script

```bash
# Interactive (prompts for confirmation)
docker exec -it analytics-api /app/scripts/restore.sh /backups/analytics_20240115_020001.dump

# Non-interactive (CI/automation)
docker exec -e FORCE_RESTORE=true analytics-api \
    /app/scripts/restore.sh /backups/analytics_20240115_020001.dump
```

### Step 3 — Verify

The script automatically prints a table count and row counts per table after restore. Check the output for:

```
[analytics-restore][...] SUCCESS: Verification passed — 6 table(s) found in analytics schema.
```

### Step 4 — Restart dependent services

After a restore, restart the API and workers to clear any in-memory state:

```bash
docker-compose restart analytics-api analytics-news-fetcher analytics-news-nlp
```

---

## Restore Drill Procedure

Run this drill at least once before going to production, and repeat quarterly.

### Prerequisites

- A recent backup file in `/backups/`
- Access to the Docker host or a staging environment
- `DATABASE_URL` pointing to the **staging** database (never drill on production)

### Step-by-step

```bash
# 1. Confirm you are on STAGING, not production
echo $DATABASE_URL   # must NOT contain prod hostname

# 2. Take a fresh backup of current state (safety net)
docker exec analytics-api /app/scripts/backup.sh
LATEST=$(docker exec analytics-api ls -t /backups/analytics_*.dump | head -1)
echo "Safety backup: $LATEST"

# 3. Pick the backup to restore (use the safety backup or a specific date)
RESTORE_FILE="/backups/analytics_20240115_020001.dump"

# 4. Run restore (interactive — type 'yes' when prompted)
docker exec -it analytics-api /app/scripts/restore.sh "$RESTORE_FILE"

# 5. Verify table counts match expected values
docker exec analytics-api psql "$DATABASE_URL" -c \
    "SELECT table_name, (SELECT COUNT(*) FROM analytics.news_articles) FROM information_schema.tables WHERE table_schema='analytics' LIMIT 1;"

# 6. Run smoke tests against the restored data
docker exec analytics-api python -m pytest tests/ -v -k "not integration" --tb=short

# 7. Check application health
curl -s http://localhost:8000/health | python -m json.tool

# 8. Document the drill result
echo "Restore drill completed: $(date)" >> docs/restore-drill-log.txt
echo "  Backup file: $RESTORE_FILE" >> docs/restore-drill-log.txt
echo "  Result: SUCCESS" >> docs/restore-drill-log.txt
```

### Expected outcomes

| Check | Expected |
|---|---|
| Script exit code | `0` |
| Schema exists | `analytics` schema present |
| Table count | ≥ 6 tables (news_sources, news_articles, chat_sessions, chat_messages, agent_runs, audit_log) |
| Health endpoint | `{"status": "ok"}` |
| Unit tests | All pass |

### Drill log

Record each drill in `analytics/docs/restore-drill-log.txt`:

```
2024-01-15  Restore drill — analytics_20240114_020001.dump → SUCCESS (6 tables, 1,234 articles)
```

---

## Backup File Naming

```
analytics_YYYYMMDD_HHMMSS.dump
         │        │
         │        └── Time: HH=hour, MM=minute, SS=second (UTC)
         └──────────── Date: YYYY=year, MM=month, DD=day
```

Example: `analytics_20240115_020001.dump` = backup taken on 2024-01-15 at 02:00:01 UTC.

---

## Troubleshooting

### `pg_dump: error: connection to server failed`

- Check `DATABASE_URL` is correct and the Postgres container is running.
- From inside the container: `pg_isready -d "$DATABASE_URL"`

### `No space left on device`

- Check disk space: `df -h /backups`
- Reduce `BACKUP_RETAIN_DAYS` or move the backup volume to a larger disk.

### `pg_restore: error: schema "analytics" does not exist`

- The restore script creates the schema before restoring. If this error appears, check that the `psql` command in `restore.sh` ran successfully (look for the `Creating analytics schema` log line).

### Backup file is 0 bytes

- `pg_dump` failed silently. Check the log for the `ERROR` line and verify `DATABASE_URL` and schema name.
