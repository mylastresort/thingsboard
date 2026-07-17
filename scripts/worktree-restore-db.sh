#!/usr/bin/env bash
# worktree-restore-db.sh — Restore postgres data for a worktree using docker compose.
#
# Usage: ./scripts/worktree-restore-db.sh <branch-name> [--from-backup <path>]
#
# Uses `docker compose up postgres` + `docker compose cp` + `docker compose exec`
# to restore. The minimal worktree-restore.yml only defines the postgres service
# so there are no dependency errors from services not in the file list.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BRANCH="${1:?Usage: $0 <branch-name> [--from-backup <path>]}"
BACKUP_FILE=""

shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-backup) BACKUP_FILE="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

SAFE_BRANCH="${BRANCH//\//-}"
VOLUMES_DIR="${REPO_DIR}/.worktrees/${SAFE_BRANCH}"
PROJECT_NAME="thingsboard-wt-${SAFE_BRANCH}"
BACKUP_PATTERN="${BACKUP_PATTERN:-$HOME/backup/thingsboard-postgres-*.sql.gz}"

echo "=== Restoring postgres for worktree: ${BRANCH} ==="

# Find backup
if [[ -z "$BACKUP_FILE" ]]; then
  for f in $BACKUP_PATTERN; do
    if [[ -f "$f" ]]; then
      BACKUP_FILE="$f"
      break
    fi
  done
fi

if [[ -z "$BACKUP_FILE" || ! -f "$BACKUP_FILE" ]]; then
  echo "ERROR: No backup found. Provide one with --from-backup <path>"
  exit 1
fi
echo "  Backup: $(basename "$BACKUP_FILE")"

# Export env vars for compose
export WORKTREE_VOLUMES_DIR="${VOLUMES_DIR}"
export WT_WORKTREE="${REPO_DIR}/../thingsboard-wt-${SAFE_BRANCH}"

# Helper: run docker compose with the right args
dc() {
  docker compose \
    --project-directory "$REPO_DIR" \
    -f docker-compose/docker-compose.base.yml \
    -f docker-compose/docker-compose.worktree-restore.yml \
    -p "$PROJECT_NAME" "$@"
}

# Start just postgres
echo "Starting postgres container..."
dc up -d postgres

# Wait for postgres to be fully ready (may restart after init phase).
echo "Waiting for postgres..."
for i in $(seq 1 120); do
  if dc exec -T postgres pg_isready -U postgres -d thingsboard >/dev/null 2>&1; then
    if dc exec -T postgres psql -U postgres -d thingsboard -c "SELECT 1" >/dev/null 2>&1; then
      echo "  Postgres ready."
      break
    fi
  fi
  if [[ $i -eq 120 ]]; then
    echo "ERROR: Postgres did not become ready within 120s"
    dc logs postgres 2>&1 | tail -20
    exit 1
  fi
  sleep 1
done

# Copy backup into container and restore
echo "Restoring data..."
dc cp "$BACKUP_FILE" postgres:/backup.sql.gz
dc exec -T postgres bash -c 'gunzip -c /backup.sql.gz | psql -U postgres -d thingsboard'

echo ""
echo "=== Restore complete ==="
echo "  Database: thingsboard"
