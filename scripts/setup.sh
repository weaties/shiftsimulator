#!/usr/bin/env bash
# setup.sh — provision shiftsim on a Raspberry Pi (or any Debian host).
#
# Installs a dedicated service account and a hardened systemd service that runs
# `python -m shiftsim serve` on localhost (127.0.0.1:8765).
#
# nginx is NOT installed by default, because the target host (corvopi-live)
# already runs helmlog's nginx. Coexistence is by path: helmlog's nginx proxies
# /sim/ -> 127.0.0.1:8765 (see docs/specs/deploy-corvopi-live.md and the
# matching change in the helmlog repo). The app is subpath-safe.
#
# Usage (run from the cloned repo, as a normal user with sudo):
#   bash scripts/setup.sh                  # service only (coexist behind helmlog nginx)
#   bash scripts/setup.sh --standalone-nginx   # also install our own nginx :80 (dedicated host)
#
# Idempotent — safe to re-run after a `git pull`. Prompts once for sudo.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PORT="${SHIFTSIM_PORT:-8765}"
SERVICE_USER="shiftsim"
PYTHON="$(command -v python3)"
WITH_NGINX=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --standalone-nginx) WITH_NGINX=1; shift ;;
        -h|--help) echo "Usage: setup.sh [--standalone-nginx]"; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
step() { echo -e "\n${GREEN}==> $*${NC}"; }
warn() { echo -e "${YELLOW}WARN:${NC} $*"; }

step "shiftsim setup — repo $PROJECT_DIR, port $PORT, python $PYTHON, nginx=$([ $WITH_NGINX = 1 ] && echo standalone || echo 'helmlog (coexist)')"

# ---------------------------------------------------------------------------
# 1) Packages (no nginx unless standalone)
# ---------------------------------------------------------------------------
step "Ensuring python3 + git..."
sudo apt-get update -qq
sudo apt-get install -y python3 git

# ---------------------------------------------------------------------------
# 2) Service account
# ---------------------------------------------------------------------------
if id "$SERVICE_USER" >/dev/null 2>&1; then
    echo "    user '$SERVICE_USER' exists"
else
    step "Creating system user '$SERVICE_USER'..."
    sudo useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi
# the service account only needs to read the code; keep the tree traversable.
sudo chmod -R a+rX "$PROJECT_DIR"

# ---------------------------------------------------------------------------
# 3) systemd service (rendered from the actual clone path)
# ---------------------------------------------------------------------------
step "Installing systemd service 'shiftsim'..."
sudo tee /etc/systemd/system/shiftsim.service > /dev/null <<EOF
[Unit]
Description=shiftsim sailing-tactics simulator
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
Environment=PYTHONPATH=$PROJECT_DIR/src
ExecStart=$PYTHON -m shiftsim serve --port $PORT --dir $PROJECT_DIR
Restart=always
RestartSec=2
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadOnlyPaths=$PROJECT_DIR

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now shiftsim
sudo systemctl restart shiftsim

# ---------------------------------------------------------------------------
# 3b) Scoped sudo for the web deploy page (web/admin.html)
# ---------------------------------------------------------------------------
# Lets the unprivileged "$SERVICE_USER" service account deploy & restart itself
# from the (UNAUTHENTICATED — see docs/specs/admin-page.md) admin page. Grants are
# deliberately narrow: restart *this* service, and git on *this* checkout only
# (the tree is root-owned, so git writes need root). Mirrors helmlog's
# helmlog-allowed drop-in, scoped tighter with -C "$PROJECT_DIR".
step "Installing scoped sudoers for the deploy page..."
sudo tee /etc/sudoers.d/shiftsim > /dev/null <<EOF
$SERVICE_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart shiftsim
$SERVICE_USER ALL=(root) NOPASSWD: /usr/bin/git -C $PROJECT_DIR *
EOF
sudo chmod 0440 /etc/sudoers.d/shiftsim
# Refuse a malformed file rather than wedge sudo.
if ! sudo visudo -cf /etc/sudoers.d/shiftsim; then
    warn "sudoers drop-in failed validation; removing it (deploy page actions will be disabled)."
    sudo rm -f /etc/sudoers.d/shiftsim
fi

# ---------------------------------------------------------------------------
# 4) nginx — only on a dedicated host (--standalone-nginx)
# ---------------------------------------------------------------------------
if [[ $WITH_NGINX -eq 1 ]]; then
    step "Installing standalone nginx reverse proxy (:80)..."
    sudo apt-get install -y nginx
    sudo install -m 644 "$SCRIPT_DIR/nginx/shiftsim.conf" /etc/nginx/sites-available/shiftsim.conf
    sudo ln -sf /etc/nginx/sites-available/shiftsim.conf /etc/nginx/sites-enabled/shiftsim.conf
    sudo rm -f /etc/nginx/sites-enabled/default
    sudo nginx -t
    sudo systemctl reload nginx
else
    step "Skipping nginx (coexist mode)."
    echo "    The app is on 127.0.0.1:$PORT. Front it from helmlog's nginx:"
    echo "    add the /sim/ location from docs/specs/deploy-corvopi-live.md to"
    echo "    helmlog's scripts/nginx/helmlog.conf, then reload nginx there."
fi

# ---------------------------------------------------------------------------
# 5) Health check
# ---------------------------------------------------------------------------
step "Health check..."
sleep 1
if curl -fsS "http://127.0.0.1:$PORT/web/" >/dev/null; then
    echo "    OK — shiftsim responding on 127.0.0.1:$PORT"
else
    warn "app did not respond — check: sudo journalctl -u shiftsim -n 50"
fi

HOST="$(hostname)"
if [[ $WITH_NGINX -eq 1 ]]; then
    step "Done. Open:  http://$HOST/"
else
    step "Done (service-only). Once helmlog's nginx has the /sim/ location:  http://$HOST/sim/"
fi
echo "    Update later with:  bash $SCRIPT_DIR/deploy.sh   (or the web deploy page: /sim/web/admin.html)"
