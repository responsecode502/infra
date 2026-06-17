#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
target_dir="${PWD}/$(echo "$(cat .device)")"

if [[ ! -d "${target_dir}" ]]; then
  echo "Error: Profile path '${target_dir}' does not exist." >&2
  exit 1
fi

read -rs -p "Enter pass-phrase for [${target_dir##*/}]: " phrase
echo ""

if [[ -z "${phrase}" ]]; then
  echo "Error: Pass-phrase cannot be empty." >&2
  exit 1
fi

echo "${phrase}" > "${target_dir}/.aes"
echo "Key saved to: ${target_dir}/.aes"
