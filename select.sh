#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

profile="${1:?no folder chosen}"
if [ ! -d "$profile" ]; then
  echo "no such profile"
  exit 1
fi

ln -sfn "$profile" .profile
echo "selected ${profile}"
