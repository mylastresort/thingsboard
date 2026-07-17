#!/usr/bin/env bash
set -euo pipefail

# worktree-switch.sh — Switch a worktree to a different PR's code
# Stops containers, wipes volumes, re-restores postgres from backup,
# checks out the new ref, and reports.
#
# Usage:
#   ./scripts/worktree-switch.sh <branch-name> <pr-number-or-ref>
#
# Examples:
#   ./scripts/worktree-switch.sh feat/test 42
#   ./scripts/worktree-switch.sh feat/test origin/fix/eliminate-spof
#   ./scripts/worktree-switch.sh feat/test HEAD~3

USAGE="Usage: $0 <branch-name> <pr-number-or-ref>"

BRANCH=""
NEW_REF=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      echo "$USAGE"
      exit 0
      ;;
    *)
      if [[ -z "$BRANCH" ]]; then
        BRANCH="$1"
        shift
      elif [[ -z "$NEW_REF" ]]; then
        NEW_REF="$1"
        shift
      else
        echo "Error: unexpected argument '$1'"
        echo "$USAGE"
        exit 1
      fi
      ;;
  esac
done

if [[ -z "$BRANCH" || -z "$NEW_REF" ]]; then
  echo "Error: branch-name and pr-number-or-ref are required"
  echo "$USAGE"
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SAFE_BRANCH="${BRANCH//\//-}"
WORKTREE_DIR="${REPO_ROOT}/../thingsboard-wt-${SAFE_BRANCH}"
VOLUMES_DIR="${REPO_ROOT}/.worktrees/${SAFE_BRANCH}"
COMPOSE_DIR="${REPO_ROOT}/docker-compose"
PROJECT="thingsboard-wt-${SAFE_BRANCH}"
BACKUP_DIR="${HOME}/backup"

WT_COMPOSE="-f ${COMPOSE_DIR}/docker-compose.base.yml -f ${COMPOSE_DIR}/docker-compose.db.yml -f ${COMPOSE_DIR}/docker-compose.tb.yml -f ${COMPOSE_DIR}/docker-compose.gateway.yml -f ${COMPOSE_DIR}/docker-compose.web.yml -f ${COMPOSE_DIR}/docker-compose.model.yml -f ${COMPOSE_DIR}/docker-compose.config.yml -f ${COMPOSE_DIR}/docker-compose.mcp.yml -f ${COMPOSE_DIR}/docker-compose.toolbox.yml -f ${COMPOSE_DIR}/docker-compose.dev.yml -f ${COMPOSE_DIR}/docker-compose.worktree.yml"

if [[ ! -d "${WORKTREE_DIR}" ]]; then
  echo "Error: worktree not found at ${WORKTREE_DIR}"
  echo "Run worktree-setup.sh first."
  exit 1
fi

# ── stop containers ────────────────────────────────────────────────────────
echo "==> Stopping worktree containers..."
WORKTREE_VOLUMES_DIR="${VOLUMES_DIR}" \
  docker compose --project-directory "${REPO_ROOT}" \
  ${WT_COMPOSE} \
  -p "${PROJECT}" \
  down -v 2>/dev/null || true

# ── fetch the PR ref ──────────────────────────────────────────────────────
if [[ "$NEW_REF" =~ ^[0-9]+$ ]]; then
  echo "==> Fetching PR #${NEW_REF}..."
  git -C "$REPO_ROOT" fetch origin "pull/${NEW_REF}/head:pr-${NEW_REF}" 2>/dev/null || true
  NEW_REF="pr-${NEW_REF}"
fi

# ── reset volumes ─────────────────────────────────────────────────────────
echo "==> Resetting volumes..."
rm -rf "${VOLUMES_DIR:?}"/*/  2>/dev/null || true
mkdir -p "${VOLUMES_DIR}"/{psql_data-merge,psql_data-merge-config,redis-data,kafka-data,cassandra-data,tb-config,tb-quarkus-cache,tb_quarkus_dev_cache/gradle,tb_quarkus_dev_cache/runtime,pip-cache,models-cache,go-mod-cache,go-build-cache,.ollama}

# ── restore postgres from backup ───────────────────────────────────────────
LATEST_BACKUP=$(ls -t "${BACKUP_DIR}"/thingsboard-postgres-*.sql.gz 2>/dev/null | head -1)

if [[ -n "$LATEST_BACKUP" ]]; then
  echo "==> Restoring postgres from backup: $(basename "$LATEST_BACKUP")"

  PG_CONTAINER="wt-restore-${SAFE_BRANCH}"
  docker rm -f "$PG_CONTAINER" 2>/dev/null || true
  docker run -d --name "$PG_CONTAINER" \
    -e POSTGRES_DB=thingsboard \
    -e POSTGRES_PASSWORD=postgres \
    -e POSTGRES_USER=postgres \
    -v "${VOLUMES_DIR}/psql_data-merge:/var/lib/postgresql" \
    -p 15432:5432 \
    postgres:18

  echo "==> Waiting for postgres to be ready..."
  until docker exec "$PG_CONTAINER" pg_isready -U postgres -d thingsboard; do
    sleep 2
  done

  gunzip -c "$LATEST_BACKUP" | docker exec -i "$PG_CONTAINER" psql -U postgres -d thingsboard

  echo "==> Postgres restored from backup"
  docker stop "$PG_CONTAINER" && docker rm "$PG_CONTAINER"
else
  echo "==> No postgres backup found — worktree will start with empty DB"
fi

# ── copy tb-config from main stack ────────────────────────────────────────
MAIN_TB_CONFIG="${REPO_ROOT}/tb-config"
if [[ -d "${MAIN_TB_CONFIG}" && -n "$(ls -A "${MAIN_TB_CONFIG}" 2>/dev/null)" ]]; then
  echo "==> Copying tb-config from main stack..."
  cp -a "${MAIN_TB_CONFIG}/." "${VOLUMES_DIR}/tb-config/"
fi

# ── checkout new ref ──────────────────────────────────────────────────────
echo "==> Checking out ${NEW_REF} in worktree..."
git -C "$WORKTREE_DIR" fetch origin 2>/dev/null || true
git -C "$WORKTREE_DIR" checkout "$NEW_REF" 2>/dev/null || git -C "$WORKTREE_DIR" checkout "origin/${NEW_REF}" 2>/dev/null

echo ""
echo "==> Switched worktree '${BRANCH}' to: ${NEW_REF}"
echo "    Latest commits:"
git -C "$WORKTREE_DIR" log --oneline -5
echo ""
echo "    To start: make wt-up BRANCH=${SAFE_BRANCH}"
