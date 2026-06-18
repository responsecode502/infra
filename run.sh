#!/usr/bin/env bash
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
  echo "no permissions"
  exit 1
fi

cd "$(dirname "$0")"

SSL_NO_VERIFY=1 xbps-install -S --yes
xbps-install -u xbps --yes
xbps-install curl --yes

if ! command -v uv &> /dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh
fi

cd "$(readlink .profile)"
uv run python crypt.py --decrypt
uv run inv setup-system
