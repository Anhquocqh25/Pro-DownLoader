#!/usr/bin/env bash
set -euo pipefail

APP_ROOT=/opt/pro-downloader
STATE_ROOT=/var/lib/pro-downloader
SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "Run this script with sudo."
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv ffmpeg

if ! id -u prodownloader >/dev/null 2>&1; then
  useradd --system --home-dir "$STATE_ROOT" --create-home --shell /usr/sbin/nologin prodownloader
fi

install -d -o root -g root -m 0755 "$APP_ROOT/app"
install -d -o prodownloader -g prodownloader -m 0750 "$STATE_ROOT/downloads"
cp -a "$SOURCE_ROOT/." "$APP_ROOT/app/"
rm -rf "$APP_ROOT/app/.git" "$APP_ROOT/app/.venv" "$APP_ROOT/app/build" "$APP_ROOT/app/dist" "$APP_ROOT/app/release"

python3 -m venv "$APP_ROOT/venv"
"$APP_ROOT/venv/bin/python" -m pip install --upgrade pip wheel
"$APP_ROOT/venv/bin/python" -m pip install -r "$APP_ROOT/app/requirements.txt"

if [[ ! -f /etc/pro-downloader.env ]]; then
  umask 077
  cat >/etc/pro-downloader.env <<EOF
PRO_DOWNLOADER_API_KEY=$(openssl rand -hex 24)
PRO_DOWNLOADER_HOST=127.0.0.1
PRO_DOWNLOADER_PORT=8000
PRO_DOWNLOADER_DOWNLOAD_DIR=$STATE_ROOT/downloads
PRO_DOWNLOADER_RETENTION_HOURS=24
HOME=$STATE_ROOT
PYTHONUNBUFFERED=1
EOF
fi

install -o root -g root -m 0644 "$SOURCE_ROOT/deploy/vps/pro-downloader.service" /etc/systemd/system/
install -o root -g root -m 0644 "$SOURCE_ROOT/deploy/vps/pro-downloader-cleanup.service" /etc/systemd/system/
install -o root -g root -m 0644 "$SOURCE_ROOT/deploy/vps/pro-downloader-cleanup.timer" /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now pro-downloader pro-downloader-cleanup.timer

echo "Pro Downloader is running on http://127.0.0.1:8000"
echo "API key: $(sed -n 's/^PRO_DOWNLOADER_API_KEY=//p' /etc/pro-downloader.env)"
echo "Add deploy/vps/Caddyfile.example to your Caddy configuration for HTTPS."
