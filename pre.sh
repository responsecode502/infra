#!/usr/bin/env bash
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
  echo "root permissions required"
  exit 1
fi

# Move to the directory of this file
cd "$(dirname "$0")"

if [ ! -f ".device" ]; then
  echo ".device file not found"
  exit 1
fi

# Refresh indexies
SSL_NO_VERIFY=1 xbps-install -S --yes

# Self-update
xbps-install -u xbps --yes

# Install deploy dependencies
xbps-install curl --yes
if [ -x "/usr/local/bin/uv" ]; then
    echo "uv already installed"
else
    echo "installing uv"
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh
fi

target_dir="${PWD}/$(echo "$(cat .device)")"

if [ ! -d "$target_dir" ]; then
  echo "'$target_dir' does not exist"
  exit 1
fi

echo "Из файла .device успешно прочитан профиль: $target_dir"

