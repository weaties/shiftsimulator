#!/usr/bin/env bash
# deploy.sh — update shiftsim on the Pi and restart the service.
#
# Usage (run from the cloned repo on the Pi):
#   bash scripts/deploy.sh            # pull & deploy latest main
#   bash scripts/deploy.sh --pr 12    # deploy the branch for GitHub PR #12
#
# If systemd/nginx config changed (new ports, paths), run setup.sh instead.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PORT="${SHIFTSIM_PORT:-8765}"
PR_NUMBER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pr) PR_NUMBER="$2"; shift 2 ;;
        -h|--help) echo "Usage: deploy.sh [--pr NUMBER]"; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

cd "$PROJECT_DIR"
echo "==> Fetching..."
git fetch --all --prune

if [[ -n "$PR_NUMBER" ]]; then
    echo "==> Deploying PR #$PR_NUMBER"
    git fetch origin "pull/$PR_NUMBER/head:pr-$PR_NUMBER"
    git checkout "pr-$PR_NUMBER"
    git reset --hard "pr-$PR_NUMBER"
else
    echo "==> Deploying latest main"
    git checkout main
    git reset --hard origin/main
fi

# keep the tree readable by the service account
sudo chmod -R a+rX "$PROJECT_DIR"

echo "==> Restarting shiftsim..."
sudo systemctl restart shiftsim
sleep 1

if curl -fsS "http://127.0.0.1:$PORT/web/" >/dev/null; then
    echo "==> OK — http://$(hostname)/  ($(git rev-parse --short HEAD))"
else
    echo "!! app not responding; check: sudo journalctl -u shiftsim -n 50" >&2
    exit 1
fi
