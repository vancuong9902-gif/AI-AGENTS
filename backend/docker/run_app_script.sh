#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <script-path>" >&2
  exit 1
fi

script_path="$1"
if [ ! -f "$script_path" ]; then
  echo "Script not found: $script_path" >&2
  exit 1
fi

tmp_script="$(mktemp)"
trap 'rm -f "$tmp_script"' EXIT
tr -d '\r' <"$script_path" >"$tmp_script"
exec bash "$tmp_script"
