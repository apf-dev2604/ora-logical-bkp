#!/usr/bin/env bash
set -Eeuo pipefail
# Run only on a fresh WRITABLE target Oracle 19c database.
cd "$(dirname "$0")"
trap 'code=$?; python3 dr_manager.py --config config.json --alert "download/impdp failed with exit code ${code}; examine import logs" || true; exit "$code"' ERR
: "${DP_IMPORT_CONNECT:?Set DP_IMPORT_CONNECT to an Oracle wallet alias like /@DPTARGET}"
python3 dr_manager.py --config config.json --download
# Operator must review tablespaces/TZ/patches and destination BEFORE executing import.
if [[ "${PHCAFE_APPROVE_IMPORT:-}" != "YES" ]]; then
  echo 'Downloaded and verified. Set PHCAFE_APPROVE_IMPORT=YES only after reviewing target setup before running impdp.'
  exit 0
fi
impdp "${DP_IMPORT_CONNECT}" parfile=impdp_full.par
