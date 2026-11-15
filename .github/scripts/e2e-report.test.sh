#!/usr/bin/env bash
# Tests for e2e-report.sh with Playwright JSON reports written here and a fake gh CLI that answers
# the open issues (OPEN_ISSUES) and records its calls and the bodies it is given.
#   bash .github/scripts/e2e-report.test.sh
# The expected texts quote markdown: their backticks are literal (SC2016).
# shellcheck disable=SC2016
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

TITLE="Pruebas de navegador del Hub en rojo en la pasada nocturna"
# The night's folder as the nightly passes it: under HOME, which the report writes as ~.
export HOME="$work/home"
RUN_DIR="$HOME/.erplora/hub-nightly-e2e/runs/20261114-021700"
mkdir -p "$RUN_DIR"

mkdir -p "$work/bin"
cat > "$work/bin/gh-fake" <<'FAKE'
#!/usr/bin/env bash
echo "gh $*" >> "$CALLS_LOG"
[ -z "${GH_FAILS:-}" ] || { echo "HTTP 502" >&2; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
    --body-file) cat "$2" >> "$BODIES_LOG"; shift ;;
    --comment|--body) printf '%s\n' "$2" >> "$BODIES_LOG"; shift ;;
  esac
  shift
done
case "$CALL" in *"issue list"*) printf '%s\n' "${OPEN_ISSUES:-[]}" ;; esac
FAKE
# The fake reads its own command line from CALL: a wrapper sets it.
cat > "$work/bin/gh" <<'WRAP'
#!/usr/bin/env bash
CALL="$*" exec "$(dirname "$0")/gh-fake" "$@"
WRAP
chmod +x "$work/bin/gh" "$work/bin/gh-fake"
export CALLS_LOG="$work/calls.log" BODIES_LOG="$work/bodies.log"

# A run with a red test inside a describe, a timed-out test, a passing and a skipped one, as
# Playwright's json reporter writes it (colours in the messages included).
red_report="$work/red.json"
cat > "$red_report" <<'JSON'
{
  "suites": [
    {
      "title": "sale-sales.spec.ts", "file": "sale-sales.spec.ts", "line": 0,
      "specs": [
        {"title": "passes", "file": "sale-sales.spec.ts", "line": 2,
         "tests": [{"projectName": "", "status": "expected", "results": [{"status": "passed"}]}]}
      ],
      "suites": [
        {
          "title": "SALE-F01 the sale", "file": "sale-sales.spec.ts", "line": 3,
          "specs": [
            {"title": "charges in cash", "file": "sale-sales.spec.ts", "line": 4,
             "tests": [{"projectName": "", "status": "unexpected",
                        "results": [{"status": "failed",
                                     "error": {"message": "Error: \u001b[2mexpect(\u001b[22mlocator).toBeVisible()\n\nExpected: visible"}}]}]}
          ]
        }
      ]
    },
    {
      "title": "staff-flows.spec.ts", "file": "staff-flows.spec.ts", "line": 0,
      "specs": [
        {"title": "skipped one", "file": "staff-flows.spec.ts", "line": 2,
         "tests": [{"projectName": "", "status": "skipped", "results": [{"status": "skipped"}]}]},
        {"title": "adds a member", "file": "staff-flows.spec.ts", "line": 9,
         "tests": [{"projectName": "", "status": "unexpected",
                    "results": [{"status": "timedOut", "error": {"message": "Test timeout of 180000ms exceeded."}}]}]}
      ]
    }
  ],
  "errors": [],
  "stats": {"expected": 1, "skipped": 1, "unexpected": 2, "flaky": 0, "duration": 1000}
}
JSON

# A run that stopped in globalSetup: no test ran, the error is the run's.
setup_report="$work/setup.json"
cat > "$setup_report" <<'JSON'
{"suites": [], "errors": [{"message": "Error: unapplied migrations (sale.0042)\n    at globalSetup"}],
 "stats": {"expected": 0, "skipped": 0, "unexpected": 0, "flaky": 0, "duration": 10}}
JSON

# report VAR=value...: runs e2e-report.sh; leaves its calls, bodies and output in the logs.
report() {
  : > "$CALLS_LOG"
  : > "$BODIES_LOG"
  if env PATH="$work/bin:$PATH" GH_REPO=ERPlora/hub SHA=0123456789abcdef RUN_DIR="$RUN_DIR" \
    DAY=2026-11-14 PUBLISH=true RESULT=failure REPORT="$red_report" \
    "$@" bash "$here/e2e-report.sh" > "$work/out" 2>&1; then
    echo 0
  else
    echo 1
  fi
}

# expect <name> <expected> <actual>
expect() {
  if [ "$3" = "$2" ]; then
    echo "ok   - $1"
  else
    echo "FAIL - $1: expected '$2', got '$3'"
    failures=$((failures + 1))
  fi
}
has() { grep -cF -- "$2" "$1" || true; }
writes() { grep -cE '^gh issue (create|comment|close|edit|reopen)' "$CALLS_LOG" || true; }

# --- red, no open issue: one new issue with what came out red ---------------------------------
expect "a red night with no open issue ends well" 0 "$(report)"
expect "it opens one issue, with the title and prio:P1" 1 \
  "$(grep -cF -- "gh issue create --title $TITLE --label prio:P1 --body-file" "$CALLS_LOG" || true)"
expect "it looks for the issue among the open ones only" 1 "$(grep -c '^gh issue list --state open' "$CALLS_LOG" || true)"
expect "it searches the issue by its exact title, not among the latest N issues" 1 \
  "$(grep -cF -- "--search \"$TITLE\" in:title" "$CALLS_LOG" || true)"
expect "the body opens with «## Qué pasa»" "## Qué pasa" "$(head -n 1 "$BODIES_LOG")"
expect "the body lists the red test of a describe: file:line and titles" 1 \
  "$(has "$BODIES_LOG" '- `sale-sales.spec.ts:4` › SALE-F01 the sale › charges in cash — Error: expect(locator).toBeVisible()')"
expect "the body lists the timed-out test with its error" 1 \
  "$(has "$BODIES_LOG" '- `staff-flows.spec.ts:9` › adds a member — Test timeout of 180000ms exceeded.')"
expect "no colour code reaches the body" 0 "$(grep -c $'\033' "$BODIES_LOG" || true)"
expect "passing and skipped tests are not listed" 0 "$(grep -cE 'passes|skipped one' "$BODIES_LOG" || true)"
expect "the body counts the run" 1 "$(has "$BODIES_LOG" '2 en rojo · 1 bien · 1 saltadas')"
expect "the body names the commit of main it ran on" 1 "$(has "$BODIES_LOG" '(commit `0123456`)')"
expect "the body says where the night's log and traces are, from ~" 1 \
  "$(has "$BODIES_LOG" '`~/.erplora/hub-nightly-e2e/runs/20261114-021700`')"
expect "no path of the Mac's user reaches the body" 0 "$(has "$BODIES_LOG" "$HOME")"
expect "the body reproduces with the specs on that commit" 1 \
  "$(grep -cE '^- Test: .*origin/main@0123456' "$BODIES_LOG" || true)"
expect "the body says where it comes from" 1 "$(has "$BODIES_LOG" '- Sale de #877')"
for section in "## Propuesta" "## Detalle técnico" "## Origen" "## Cómo se reproduce" "## Flujo"; do
  expect "the body has «${section}»" 1 "$(grep -cxF -- "${section}" "$BODIES_LOG" || true)"
done
expect "the output lists the red tests too" 1 "$(has "$work/out" 'staff-flows.spec.ts:9')"

# --- red, the issue already open: a comment on it, no second issue -----------------------------
open="[{\"number\": 43, \"title\": \"$TITLE (otra)\"}, {\"number\": 42, \"title\": \"$TITLE\"}]"
expect "a red night with the issue open ends well" 0 "$(report OPEN_ISSUES="$open")"
expect "it comments on the open issue of that exact title" 1 "$(grep -c '^gh issue comment 42 --body-file' "$CALLS_LOG" || true)"
expect "and writes nothing else" 1 "$(writes)"
expect "the comment says the night and the commit" 1 "$(has "$BODIES_LOG" 'La pasada del 2026-11-14 sigue en rojo, sobre `main` (commit `0123456`)')"
expect "the comment lists the red tests" 1 "$(has "$BODIES_LOG" 'staff-flows.spec.ts:9')"

# --- green: the open issue is closed; nothing to do without one -------------------------------
expect "a green night with the issue open ends well" 0 "$(report OPEN_ISSUES="$open" RESULT=success REPORT=/nonexistent)"
expect "it closes the issue as completed" 1 \
  "$(grep -c '^gh issue close 42 --reason completed --comment' "$CALLS_LOG" || true)"
expect "the closing comment names the night and the commit" 1 \
  "$(has "$BODIES_LOG" 'La pasada del 2026-11-14 ha salido entera en verde sobre `main` (commit `0123456`)')"
expect "and writes nothing else" 1 "$(writes)"
expect "a green night with no open issue ends well" 0 "$(report RESULT=success REPORT=/nonexistent)"
expect "and writes no issue" 0 "$(writes)"

# --- red without a usable report: said, not hidden ---------------------------------------------
expect "a red night without its report ends well" 0 "$(report REPORT=/nonexistent)"
expect "it still opens the issue" 1 "$(grep -c '^gh issue create' "$CALLS_LOG" || true)"
expect "the body says the run left no report" 1 "$(has "$BODIES_LOG" 'sin informe de las pruebas')"
printf 'not json' > "$work/broken.json"
expect "a red night with a broken report ends well" 0 "$(report REPORT="$work/broken.json")"
expect "the body says the run left no report" 1 "$(has "$BODIES_LOG" 'sin informe de las pruebas')"
expect "a red night stopped in globalSetup ends well" 0 "$(report REPORT="$setup_report")"
expect "the body lists the run's own error" 1 \
  "$(has "$BODIES_LOG" '- Error de la ejecución: Error: unapplied migrations (sale.0042)')"
# A run whose tests all passed but that still ended red (cut by its global timeout).
green_report="$work/green.json"
printf '%s\n' '{"suites": [], "errors": [], "stats": {"expected": 3, "skipped": 0, "unexpected": 0, "flaky": 0}}' \
  > "$green_report"
expect "a red night whose report has nothing red ends well" 0 \
  "$(report REPORT="$green_report" RESULT=timedout)"
expect "the body says the run ended red anyway" 1 "$(has "$BODIES_LOG" 'terminó en `timedout`')"

# --- red before the specs: the step that failed is named ----------------------------------------
expect "a night that never reached the specs ends well" 0 "$(report REPORT=/nonexistent STEP='la BD del SaaS')"
expect "it opens the issue" 1 "$(grep -c '^gh issue create' "$CALLS_LOG" || true)"
expect "the body names the step that failed" 1 \
  "$(has "$BODIES_LOG" 'La pasada no llegó a las specs: falló «la BD del SaaS».')"
expect "the body points at the night's log" 1 "$(has "$BODIES_LOG" '`~/.erplora/hub-nightly-e2e/runs/20261114-021700/night.log`')"

# --- PUBLISH=false: the output only ------------------------------------------------------------
expect "an unpublished red night ends well" 0 "$(report PUBLISH=false)"
expect "and calls no gh at all" 0 "$(grep -c '^gh ' "$CALLS_LOG" || true)"
expect "its output lists the red tests" 1 "$(has "$work/out" 'sale-sales.spec.ts:4')"
expect "and says no issue was written" 1 "$(has "$work/out" 'no se escribe ninguna issue')"
expect "an unpublished green night ends well" 0 "$(report PUBLISH=false RESULT=success REPORT=/nonexistent)"
expect "and calls no gh either" 0 "$(grep -c '^gh ' "$CALLS_LOG" || true)"

# --- a failing gh fails the report ---------------------------------------------------------------
expect "a gh that fails makes the report fail" 1 "$(report GH_FAILS=1)"

# --- what it needs ---------------------------------------------------------------------------------
for var in RESULT SHA RUN_DIR; do
  expect "without $var it refuses" 1 "$(report "$var=")"
  expect "and calls no gh" 0 "$(grep -c '^gh ' "$CALLS_LOG" || true)"
done

echo
if [ "$failures" -gt 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
