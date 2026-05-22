#!/usr/bin/env bash
# =============================================================================
# analytics/scripts/backup.sh
# Backup the analytics.* schema using pg_dump (custom format, compressed).
#
# Usage:
#   ./backup.sh
#
# Environment variables (read from .env if present, else from shell env):
#   DATABASE_URL   — PostgreSQL connection string (required)
#   BACKUP_DIR     — Directory to store backups (default: /backups)
#   BACKUP_RETAIN_DAYS — Days to keep old backups (default: 30)
#
# Cron (daily 2am):
#   0 2 * * * /app/scripts/backup.sh >> /var/log/analytics-backup.log 2>&1
# =============================================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Load .env if it exists and DATABASE_URL is not already set
if [[ -z "${DATABASE_URL:-}" && -f "${PROJECT_ROOT}/.env" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_RETAIN_DAYS="${BACKUP_RETAIN_DAYS:-30}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/analytics_${TIMESTAMP}.dump"
LOG_PREFIX="[analytics-backup][${TIMESTAMP}]"

# ── Validation ────────────────────────────────────────────────────────────────

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "${LOG_PREFIX} ERROR: DATABASE_URL is not set. Aborting." >&2
    exit 1
fi

# ── Ensure backup directory exists ───────────────────────────────────────────

if [[ ! -d "${BACKUP_DIR}" ]]; then
    echo "${LOG_PREFIX} INFO: Creating backup directory: ${BACKUP_DIR}"
    mkdir -p "${BACKUP_DIR}" || {
        echo "${LOG_PREFIX} ERROR: Cannot create backup directory ${BACKUP_DIR}" >&2
        exit 1
    }
fi

# ── Run pg_dump ───────────────────────────────────────────────────────────────

echo "${LOG_PREFIX} INFO: Starting backup → ${BACKUP_FILE}"

if pg_dump \
    --schema=analytics \
    --format=custom \
    --compress=9 \
    --no-password \
    --file="${BACKUP_FILE}" \
    "${DATABASE_URL}"; then

    BACKUP_SIZE="$(du -sh "${BACKUP_FILE}" 2>/dev/null | cut -f1)"
    echo "${LOG_PREFIX} SUCCESS: Backup completed. File: ${BACKUP_FILE} (${BACKUP_SIZE})"
else
    EXIT_CODE=$?
    echo "${LOG_PREFIX} ERROR: pg_dump failed with exit code ${EXIT_CODE}. Removing partial file." >&2
    rm -f "${BACKUP_FILE}"
    exit "${EXIT_CODE}"
fi

# ── Rotate old backups ────────────────────────────────────────────────────────

echo "${LOG_PREFIX} INFO: Removing backups older than ${BACKUP_RETAIN_DAYS} days from ${BACKUP_DIR}"

DELETED_COUNT=0
while IFS= read -r -d '' old_file; do
    echo "${LOG_PREFIX} INFO: Deleting old backup: ${old_file}"
    rm -f "${old_file}"
    DELETED_COUNT=$((DELETED_COUNT + 1))
done < <(find "${BACKUP_DIR}" -maxdepth 1 -name "analytics_*.dump" \
    -mtime "+${BACKUP_RETAIN_DAYS}" -print0 2>/dev/null)

if [[ "${DELETED_COUNT}" -gt 0 ]]; then
    echo "${LOG_PREFIX} INFO: Deleted ${DELETED_COUNT} old backup(s)."
else
    echo "${LOG_PREFIX} INFO: No old backups to delete."
fi

# ── Summary ───────────────────────────────────────────────────────────────────

TOTAL_BACKUPS="$(find "${BACKUP_DIR}" -maxdepth 1 -name "analytics_*.dump" 2>/dev/null | wc -l)"
echo "${LOG_PREFIX} INFO: Total backups retained: ${TOTAL_BACKUPS}"
echo "${LOG_PREFIX} INFO: Backup script finished successfully."

exit 0
