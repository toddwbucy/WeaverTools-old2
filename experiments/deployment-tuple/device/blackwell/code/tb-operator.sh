#!/usr/bin/env bash
# conforms: blackwell-probe-one-command-one-seat-per-step
set -euo pipefail
TB_SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 "$TB_SCRIPT_DIR/tb_order.py" --state "$TB_SCRIPT_DIR/../tb-evidence/tb-state.json" "${@:-next}"
