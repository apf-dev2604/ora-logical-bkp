#!/usr/bin/env bash
set -Eeuo pipefail
# Run on writable STAGING Oracle 19c server, NEVER on source PHCAFE.
cd "$(dirname "$0")"
trap 'code=$?; python3 dr_manager.py --config config.json --alert "expdp/export/upload stopped with exit code ${code}; examine export logs" || true; exit "$code"' ERR
: "${DP_STAGE_CONNECT:?Set DP_STAGE_CONNECT to an Oracle wallet alias such as /@DPSTAGE (do not include password)}"
: "${PHCAFE_DUMP_DIR:=/backup/ora-datapump-backup}"
mkdir -p "$PHCAFE_DUMP_DIR"
if find "$PHCAFE_DUMP_DIR" -maxdepth 1 -name 'PHCAFE_FULL_*.dmp' | grep -q .; then
  echo 'Existing dump files detected; refusing overwrite. Use a new dated run directory and adjust the Oracle DIRECTORY first.' >&2
  exit 2
fi
expdp "${DP_STAGE_CONNECT}" parfile=expdp_full.par
# Also verify log in Python upload step before advertising completion.
python3 dr_manager.py --config config.json --upload
