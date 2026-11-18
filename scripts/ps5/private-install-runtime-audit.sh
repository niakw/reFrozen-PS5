#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Local/private Warcraft install audit. Never uploads game files.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ $# -lt 3 || $# -gt 4 ]]; then
  echo "usage: $0 <warcraft-install> <win64-runtime-root> <compile-results.tsv> [output-dir]" >&2
  echo "set REFROZEN_EXTERNAL_ROUTES=wgl_egl only after that route has separate evidence" >&2
  exit 2
fi

INSTALL=$1
WIN64_RUNTIME=$2
COMPILE_RESULTS=$3
OUT=${4:-"$ROOT/private/warcraft-runtime-audit"}
mkdir -p "$OUT"

CENSUS="$OUT/pe-census.json"
GAPS="$OUT/runtime-gaps.json"
GATE="$OUT/first-launch-gate.json"

python3 -B "$ROOT/scripts/ps5/scan_install.py" "$INSTALL" --output "$CENSUS"
python3 -B "$ROOT/scripts/ps5/runtime_gap_report.py" "$CENSUS" \
  --root "$ROOT" --win64-runtime-root "$WIN64_RUNTIME" --output "$GAPS"

routes=()
IFS=',' read -r -a requested <<< "${REFROZEN_EXTERNAL_ROUTES:-}"
for route in "${requested[@]}"; do
  [[ -z "$route" ]] && continue
  case "$route" in
    wgl_egl) routes+=(--external-route "$route") ;;
    *)
      echo "unsupported external route: $route" >&2
      exit 2
      ;;
  esac
done

set +e
python3 -B "$ROOT/scripts/ps5/first_launch_runtime_gate.py" "$GAPS" "$COMPILE_RESULTS" \
  "${routes[@]}" --output "$GATE"
status=$?
set -e

python3 - "$CENSUS" "$GAPS" "$GATE" "$status" <<'PY'
import json, pathlib, sys
census=json.loads(pathlib.Path(sys.argv[1]).read_text())
gaps=json.loads(pathlib.Path(sys.argv[2]).read_text())
gate=json.loads(pathlib.Path(sys.argv[3]).read_text())
print("modules:", census.get("module_count", len(census.get("results", []))))
print("gap summary:", json.dumps(gaps.get("summary", {}), sort_keys=True))
print("first-launch gate:", "PASS" if gate.get("passed") else "BLOCKED")
print("missing compile/routes:", len(gate.get("missing_compile_routes", [])))
print("unresolved imports:", len(gate.get("unresolved_imports", [])))
print("unknown DLLs for triage:", len(gate.get("unknown_dlls_for_triage", [])))
print("reports:", pathlib.Path(sys.argv[1]).parent)
raise SystemExit(int(sys.argv[4]))
PY
