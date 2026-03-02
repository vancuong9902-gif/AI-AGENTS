#!/bin/bash
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

# Guard against Windows checkout issues when files are bind-mounted from host:
# - CRLF can make `set -o pipefail` become `pipefail\r` (invalid option name)
# - UTF-8 BOM can break shebang / first-token parsing in shell scripts
tr -d '\r' <"$script_path" | sed '1s/^\xEF\xBB\xBF//' >"$tmp_script"
exec bash "$tmp_script"
