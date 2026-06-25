#!/usr/bin/env bash
# setup.sh — provision shiftsim on a Raspberry Pi (or any Debian host).
#
# Installs nginx, a dedicated service account, and a systemd service that runs
# `python -m shiftsim serve` on localhost, fronted by nginx on port 80.
# Mirrors helmlog's deploy technique (loopback service + nginx reverse proxy).
#
# Usage (run from the cloned repo, as a normal user with sudo):
#   bash scripts/setup.sh
#
# Idempotent — safe to re-run after a `git pull`. Prompts once for your sudo
# password (cached for the run).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PORT="${SHIFTSIM_PORT:-8765}"
SERVICE_USER="shiftsim"
PYTHON="$(command -v python3)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
step() { echo -e "\n${GREEN}==> $*${NC}"; }
warn() { echo -e "${YELLOW}WARN:${NC} $*"; }

step "shiftsim setup — repo at $PROJECT_DIR, port $PORT, python $PYTHON"

# ---------------------------------------------------------------------------
# 1) Packages
# ---------------------------------------------------------------------------
step "Installing nginx (and ensuring python3/git)..."
sudo apt-get update -qq
sudo apt-get install -y nginx git python3

# ---------------------------------------------------------------------------
# 2) Service account
# ---------------------------------------------------------------------------
if id "$SERVICE_USER" >/dev/null 2>&1; then
    echo "    user '$SERVICE_USER' exists"
else
    step "Creating system user '$SERVICE_USER'..."
    sudo useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi
# the service account only needs to read the code (repo lives world-readable
# under /opt); make sure the tree is traversable + readable.
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
# 4) nginx reverse proxy
# ---------------------------------------------------------------------------
step "Configuring nginx reverse proxy..."
sudo install -m 644 "$SCRIPT_DIR/nginx/shiftsim.conf" /etc/nginx/sites-available/shiftsim.conf
sudo ln -sf /etc/nginx/sites-available/shiftsim.conf /etc/nginx/sites-enabled/shiftsim.conf
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

# ---------------------------------------------------------------------------
# 5) Health check
# ---------------------------------------------------------------------------
step "Health check..."
sleep 1
if curl -fsS "http://127.0.0.1:$PORT/web/" >/dev/null; then
    echo "    app responding on 127.0.0.1:$PORT"
else
    warn "app did not respond on port $PORT — check: sudo journalctl -u shiftsim -n 50"
fi
if curl -fsS -o /dev/null "http://127.0.0.1/web/"; then
    echo "    nginx proxying on port 80"
else
    warn "nginx did not proxy — check: sudo nginx -t && sudo journalctl -u nginx -n 50"
fi

HOST="$(hostname)"
step "Done. Open:  http://$HOST/   (redirects to /web/)"
echo "    Update later with:  bash $SCRIPT_DIR/deploy.sh"
