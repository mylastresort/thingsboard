#!/usr/bin/env bash
set -euo pipefail

# worktree-teardown.sh — Remove a worktree and optionally its volumes
#
# Usage:
#   ./scripts/worktree-teardown.sh <branch-name> [--keep-volumes]

USAGE="Usage: $0 <branch-name> [--keep-volumes]"

BRANCH=""
KEEP_VOLUMES=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-volumes)
      KEEP_VOLUMES=true
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

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKTREE_DIR="${REPO_ROOT}/../thingsboard-wt-${BRANCH}"
VOLUMES_DIR="${REPO_ROOT}/.worktrees/${BRANCH}"
SAFE_BRANCH="${BRANCH//\//-}"

# ── stop containers in the worktree ────────────────────────────────────────
if [[ -d "${WORKTREE_DIR}" ]]; then
  echo "==> Stopping containers in worktree..."
  COMPOSE_DIR="docker-compose"
  CORE_FILES="-f ${COMPOSE_DIR}/docker-compose.base.yml -f ${COMPOSE_DIR}/docker-compose.db.yml -f ${COMPOSE_DIR}/docker-compose.tb.yml -f ${COMPOSE_DIR}/docker-compose.gateway.yml -f ${COMPOSE_DIR}/docker-compose.web.yml -f ${COMPOSE_DIR}/docker-compose.model.yml -f ${COMPOSE_DIR}/docker-compose.config.yml -f ${COMPOSE_DIR}/docker-compose.mcp.yml"
  DEV_FILES="${CORE_FILES} -f ${COMPOSE_DIR}/docker-compose.toolbox.yml -f ${COMPOSE_DIR}/docker-compose.dev.yml"
  WT_FILES="${DEV_FILES} -f ${COMPOSE_DIR}/docker-compose.worktree.yml"

  WORKTREE_VOLUMES_DIR="${REPO_ROOT}/.worktrees/${SAFE_BRANCH}" \
  docker compose --project-directory "${WORKTREE_DIR}" \
    ${WT_FILES} \
    -p "thingsboard-wt-${SAFE_BRANCH}" \
    down -v 2>/dev/null || true
fi

# ── remove worktree ────────────────────────────────────────────────────────
if [[ -d "${WORKTREE_DIR}" ]]; then
  echo "==> Removing worktree: ${WORKTREE_DIR}"
  git -C "$REPO_ROOT" worktree remove --force "$WORKTREE_DIR" 2>/dev/null || rm -rf "$WORKTREE_DIR"
fi

# ── remove volumes ─────────────────────────────────────────────────────────
if [[ -d "${VOLUMES_DIR}" ]]; then
  if [[ "$KEEP_VOLUMES" == "true" ]]; then
    echo "==> Keeping volumes at: ${VOLUMES_DIR}"
  else
    echo "==> Removing volumes: ${VOLUMES_DIR}"
    # Some files may be container-owned (postgres data). Use a lightweight
    # alpine container to force-remove them.
    docker run --rm -v "${VOLUMES_DIR}:/vol" alpine sh -c "rm -rf /vol/*" 2>/dev/null || true
    rm -rf "$VOLUMES_DIR" 2>/dev/null || true
  fi
fi

# ── delete the branch ──────────────────────────────────────────────────────
if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/${BRANCH}" 2>/dev/null; then
  echo "==> Deleting branch: ${BRANCH}"
  git -C "$REPO_ROOT" branch -D "$BRANCH" 2>/dev/null || true
fi

echo "==> Teardown complete for: ${BRANCH}"
