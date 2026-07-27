#!/usr/bin/env bash
set -euo pipefail

# worktree-setup.sh — Create a git worktree with isolated Docker volumes
# for testing PR branches locally without touching the main stack.
#
# Usage:
#   ./scripts/worktree-setup.sh <branch-name> [--from-pr <pr-number>]
#
# Examples:
#   ./scripts/worktree-setup.sh feat/my-feature
#   ./scripts/worktree-setup.sh fix/bug-123 --from-pr 42
#   ./scripts/worktree-setup.sh tmp/test-pr --from-pr origin/fix/eliminate-spof

USAGE="Usage: $0 <branch-name> [--from-pr <pr-number-or-ref>]"

BRANCH=""
FROM_REF=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-pr)
      shift
      FROM_REF="$1"
      shift
      ;;
    -h|--help)
      echo "$USAGE"
      exit 0
      ;;
    *)
      if [[ -z "$BRANCH" ]]; then
        BRANCH="$1"
        shift
      else
        echo "Error: unexpected argument '$1'"
        echo "$USAGE"
        exit 1
      fi
      ;;
  esac
done

if [[ -z "$BRANCH" ]]; then
  echo "Error: branch-name is required"
  echo "$USAGE"
  exit 1
fi

# ── resolve paths ──────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SAFE_BRANCH="${BRANCH//\//-}"
WORKTREE_DIR="${REPO_ROOT}/../thingsboard-wt-${SAFE_BRANCH}"
VOLUMES_DIR="${REPO_ROOT}/.worktrees/${SAFE_BRANCH}"
COMPOSE_DIR="${REPO_ROOT}/docker-compose"
PROJECT="thingsboard-wt-${SAFE_BRANCH}"
BACKUP_DIR="${HOME}/backup"

# ── clone or checkout branch ───────────────────────────────────────────────
echo "==> Setting up worktree for branch: ${BRANCH}"

if [[ -n "$FROM_REF" ]]; then
  if [[ "$FROM_REF" =~ ^[0-9]+$ ]]; then
    echo "==> Fetching PR #${FROM_REF}..."
    git -C "$REPO_ROOT" fetch origin "pull/${FROM_REF}/head:pr-${FROM_REF}" 2>/dev/null || true
    FROM_REF="pr-${FROM_REF}"
  fi
  echo "==> Creating branch '${BRANCH}' from '${FROM_REF}'"
  git -C "$REPO_ROOT" worktree add -b "$BRANCH" "$WORKTREE_DIR" "$FROM_REF"
else
  if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/${BRANCH}" 2>/dev/null; then
    echo "==> Branch '${BRANCH}' exists, creating worktree"
    git -C "$REPO_ROOT" worktree add "$WORKTREE_DIR" "$BRANCH"
  else
    echo "==> Creating new branch '${BRANCH}' from current HEAD"
    git -C "$REPO_ROOT" worktree add -b "$BRANCH" "$WORKTREE_DIR"
  fi
fi

echo "==> Worktree created at: ${WORKTREE_DIR}"

# ── create isolated volume directories ─────────────────────────────────────
echo "==> Creating isolated volume directories at: ${VOLUMES_DIR}"
mkdir -p "${VOLUMES_DIR}"/{psql_data-merge,psql_data-merge-config,redis-data,kafka-data,cassandra-data,tb-config,tb-quarkus-cache,tb_quarkus_dev_cache/gradle,tb_quarkus_dev_cache/runtime,pip-cache,models-cache,go-mod-cache,go-build-cache,.ollama}

# ── restore postgres from backup ───────────────────────────────────────────
# Check if worktree already has postgres data — skip restore if so.
PG_EMPTY=true
if [[ -d "${VOLUMES_DIR}/psql_data-merge" ]]; then
  # Check for PG data files (PG stores data in base/, global/, pg_wal/, etc.)
  if ls "${VOLUMES_DIR}/psql_data-merge"/*/PG_VERSION &>/dev/null 2>&1 || \
     ls "${VOLUMES_DIR}/psql_data-merge"/*/*/PG_VERSION &>/dev/null 2>&1; then
    PG_EMPTY=false
  fi
fi

if [[ "$PG_EMPTY" == "true" ]]; then
  # Find the latest backup
  LATEST_BACKUP=$(ls -t "${BACKUP_DIR}"/thingsboard-postgres-*.sql.gz 2>/dev/null | head -1)

  if [[ -n "$LATEST_BACKUP" ]]; then
    echo "==> Restoring postgres from backup: $(basename "$LATEST_BACKUP")"

    # Start a standalone postgres container for the restore.
    # Using docker run directly avoids compose auto-discovery issues.
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

    # Restore the dump (use host port 15432 to avoid conflicts)
    gunzip -c "$LATEST_BACKUP" | docker exec -i "$PG_CONTAINER" psql -U postgres -d thingsboard

    echo "==> Postgres restored from backup"
    docker stop "$PG_CONTAINER" && docker rm "$PG_CONTAINER"
  else
    echo "==> No postgres backup found in ${BACKUP_DIR}/"
    echo "    The worktree will start with an empty DB."
    echo "    Run 'make wt-install-demo BRANCH=${SAFE_BRANCH}' to seed demo data."
  fi
else
  echo "==> Worktree already has postgres data — skipping restore"
fi

# ── copy tb-config from main stack ────────────────────────────────────────
MAIN_TB_CONFIG="${REPO_ROOT}/tb-config"
if [[ -d "${MAIN_TB_CONFIG}" && -n "$(ls -A "${MAIN_TB_CONFIG}" 2>/dev/null)" ]]; then
  echo "==> Copying tb-config from main stack..."
  cp -a "${MAIN_TB_CONFIG}/." "${VOLUMES_DIR}/tb-config/"
fi

# ── generate .env for the worktree ─────────────────────────────────────────
echo "==> Generating worktree .env"
cat > "${WORKTREE_DIR}/.env" <<EOF
# Auto-generated by worktree-setup.sh — $(date -Iseconds)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=thingsboard
TB_USERNAME=tenant@thingsboard.org
TB_PASSWORD=tenant
OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://100.104.85.95:11434}
EOF

# ── write worktree metadata ────────────────────────────────────────────────
mkdir -p "${VOLUMES_DIR}/.meta"
cat > "${VOLUMES_DIR}/.meta/info.json" <<EOF
{
  "branch": "${BRANCH}",
  "worktree_dir": "${WORKTREE_DIR}",
  "volumes_dir": "${VOLUMES_DIR}",
  "created_at": "$(date -Iseconds)",
  "from_ref": "${FROM_REF:-HEAD}"
}
EOF

# ── summary ────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Worktree ready: ${BRANCH}"
echo "============================================================"
echo ""
echo "  Worktree dir:  ${WORKTREE_DIR}"
echo "  Volumes dir:   ${VOLUMES_DIR}"
echo ""
echo "  To start the dev stack:"
echo "    make wt-up BRANCH=${SAFE_BRANCH}"
echo ""
echo "  To start with demo data:"
echo "    make wt-install-demo BRANCH=${SAFE_BRANCH}"
echo ""
echo "  To tear down:"
echo "    make wt-teardown BRANCH=${SAFE_BRANCH}"
echo ""
echo "  Ports (same as main stack, so stop main first):"
echo "    ThingsBoard:  8080"
echo "    Angular dev:  4200"
echo "    Web UI:       8090"
echo "    Quarkus:      8082/8083"
echo "    Postgres:     5431"
echo "============================================================"
