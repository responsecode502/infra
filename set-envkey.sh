#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

envkey="${1:?no envkey}"

cd "$(readlink .profile)"
echo "$envkey" > .envkey
