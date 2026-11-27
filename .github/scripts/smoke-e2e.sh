#!/usr/bin/env bash
# The Hub's browser smoke: only the tests tagged @smoke in their title, on the commit checked out here (committed
# changes only, pushed or not), in the stack scripts/nightly_e2e.py builds and always cleans up. It is red when a
# test fails or when the tests take longer than CAP_MINUTES, Playwright's global timeout, measured on the Mac's loaded
# stack.
# It never writes to the nightly issue. --spec narrows it to the @smoke tests of the specs named; it never widens it.
#
#   smoke-e2e.sh [--spec tests/e2e/<name>.spec.ts]...
#
# Environment (default): NIGHTLY_DIR (~/.erplora/hub-smoke-e2e, apart from the night's, so one never waits for the
# other) · NIGHTLY_HUB_PORT (9780, beside the night's 9770; a worker gives its own) · the rest as nightly_e2e.py.
# Exit: nightly_e2e.py's (0 green · 1 red · 3 another smoke runs in NIGHTLY_DIR) · 2 usage.
set -euo pipefail

CAP_MINUTES=20

here="$(cd "$(dirname "$0")" && pwd)"
specs=()
while [ $# -gt 0 ]; do
  case "$1:${2:-}" in
    --spec:tests/e2e/*.spec.ts) specs+=(--spec "$2") && shift 2 ;;
    *) echo "smoke-e2e: takes only --spec tests/e2e/<name>.spec.ts, not «$*» (exit 2)" >&2 && exit 2 ;;
  esac
done
commit="$(git -C "$here" rev-parse HEAD)"
export NIGHTLY_DIR="${NIGHTLY_DIR:-$HOME/.erplora/hub-smoke-e2e}" NIGHTLY_HUB_PORT="${NIGHTLY_HUB_PORT:-9780}"
NIGHTLY_GREP=@smoke NIGHTLY_HUB_REF="$commit" NIGHTLY_MAX_MINUTES="$CAP_MINUTES" \
  exec python3 "$here/../../scripts/nightly_e2e.py" ${specs[@]+"${specs[@]}"}
