#!/usr/bin/env bash
# =============================================================================
# analytics/scripts/restore.sh
# Restore the analytics.* schema from a pg_dump custom-format backup.
#
# Usage:
#   ./restore.sh <backup_file>
#
# Example:
#   ./restore.sh /backups/analytics_20240115_020001.dump
#
# Environment variables (read from .env if present, else from shell env):
#   DATABASE_URL   — PostgreSQL connection string (required)
#
# WARNING: This script drops and recreates the analytics schema.
#          All existing data in analytics.* will be LOST.
#          Run a fresh backup before restoring if needed.
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

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_PREFIX="[analytics-restore][${TIMESTAMP}]"

# ── Argument validation ───────────────────────────────────────────────────────

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <backup_file>" >&2
    echo "Example: $0 /backups/analytics_20240115_020001.dump" >&2
    exit 1
fi

BACKUP_FILE="$1"

if [[ ! -f "${BACKUP_FILE}" ]]; then
    echo "${LOG_PREFIX} ERROR: Backup file not found: ${BACKUP_FILE}" >&2
    exit 1
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "${LOG_PREFIX} ERROR: DATABASE_URL is not set. Aborting." >&2
    exit 1
fi

# ── Confirm destructive operation ─────────────────────────────────────────────

echo "============================================================"
echo "  ANALYTICS SCHEMA RESTORE"
echo "============================================================"
echo "  Backup file : ${BACKUP_FILE}"
echo "  Database    : ${DATABASE_URL%%@*}@***"
echo "  Schema      : analytics"
echo ""
echo "  WARNING: This will DROP and RECREATE the analytics schema."
echo "           All existing data in analytics.* will be LOST."
echo "============================================================"

if [[ "${FORCE_RESTORE:-false}" != "true" ]]; then
    read -r -p "Type 'yes' to confirm restore: " CONFIRM
    if [[ "${CONFIRM}" != "yes" ]]; then
        echo "${LOG_PREFIX} INFO: Restore cancelled by user."
        exit 0
    fi
fi

# ── Drop and recreate analytics schema ───────────────────────────────────────

echo "${LOG_PREFIX} INFO: Dropping analytics schema..."

psql "${DATABASE_URL}" --no-password -c "DROP SCHEMA IF EXISTS analytics CASCADE;" || {
    echo "${LOG_PREFIX} ERROR: Failed to drop analytics schema." >&2
    exit 1
}

echo "${LOG_PREFIX} INFO: Creating analytics schema..."

psql "${DATABASE_URL}" --no-password -c "CREATE SCHEMA IF NOT EXISTS analytics;" || {
    echo "${LOG_PREFIX} ERROR: Failed to create analytics schema." >&2
    exit 1
}

# ── Run pg_restore ────────────────────────────────────────────────────────────

echo "${LOG_PREFIX} INFO: Restoring from ${BACKUP_FILE}..."

if pg_restore \
    --schema=analytics \
    --no-password \
    --no-owner \
    --no-privileges \
    --exit-on-error \
    --dbname="${DATABASE_URL}" \
    "${BACKUP_FILE}"; then

    echo "${LOG_PREFIX} SUCCESS: pg_restore completed."
else
    EXIT_CODE=$?
    echo "${LOG_PREFIX} ERROR: pg_restore failed with exit code ${EXIT_CODE}." >&2
    exit "${EXIT_CODE}"
fi

# ── Verify restore ────────────────────────────────────────────────────────────

echo "${LOG_PREFIX} INFO: Verifying restore..."

TABLE_COUNT="$(psql "${DATABASE_URL}" --no-password --tuples-only --no-align \
    -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'analytics';" 2>/dev/null | tr -d '[:space:]')"

if [[ -z "${TABLE_COUNT}" || "${TABLE_COUNT}" -eq 0 ]]; then
    echo "${LOG_PREFIX} ERROR: Verification failed — no tables found in analytics schema after restore." >&2
    exit 1
fi

echo "${LOG_PREFIX} SUCCESS: Verification passed — ${TABLE_COUNT} table(s) found in analytics schema."

# ── Row counts per table ──────────────────────────────────────────────────────

echo "${LOG_PREFIX} INFO: Row counts per table:"
psql "${DATABASE_URL}" --no-password --tuples-only \
    -c "SELECT table_name, (xpath('/row/c/text()', query_to_xml(format('SELECT COUNT(*) AS c FROM analytics.%I', table_name), false, true, '')))[1]::text::int AS row_count FROM information_schema.tables WHERE table_schema = 'analytics' ORDER BY table_name;" \
    2>/dev/null | while IFS='|' read -r tbl cnt; do
        tbl="$(echo "${tbl}" | tr -d '[:space:]')"
        cnt="$(echo "${cnt}" | tr -d '[:space:]')"
        [[ -n "${tbl}" ]] && echo "  analytics.${tbl}: ${cnt} rows"
    done

echo "${LOG_PREFIX} INFO: Restore completed successfully."
exit 0
