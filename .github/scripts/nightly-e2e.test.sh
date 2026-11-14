#!/usr/bin/env bash
# Tests for nightly-e2e.sh: nights on throwaway clones of a hub and a saas repo (real git), with fake uv, pnpm,
# node, docker, curl, lsof, gh and launchctl on the PATH that log every call to $FAKE_CALLS.
#   bash .github/scripts/nightly-e2e.test.sh
# The expected texts quote markdown: their backticks are literal (SC2016).
# shellcheck disable=SC2016
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failures=0
root="$(mktemp -d)"
# Every fake server any night started, killed at the end in case a night left one behind.
cleanup() {
  if [ -f "$root/all-pids" ]; then
    while read -r pid; do kill "$pid" 2> /dev/null || true; done < "$root/all-pids"
  fi
  rm -rf "$root"
}
trap cleanup EXIT

export FAKE_CALLS="$root/fake.log" FAKE_PIDS="$root/pids" CALLS_LOG="$root/gh.log" BODIES_LOG="$root/bodies.log"
home="$root/home"
nightly="$home/.erplora/hub-nightly-e2e"
mkdir -p "$home" "$root/bin"

g() { git -c user.name=nightly -c user.email=nightly@example.com -c init.defaultBranch=main "$@"; }

# Two "GitHub" repos and their clones beside compose.yaml and blueprints/, as in erplora-next's root.
for repo in hub saas; do
  g init -q "$root/remote/$repo"
  mkdir -p "$root/remote/$repo/.github/scripts"
  for script in nightly-e2e.sh e2e-report.sh; do
    if [ -f "$here/$script" ]; then
      cp "$here/$script" "$root/remote/$repo/.github/scripts/$script"
    else
      echo '#!/usr/bin/env bash' > "$root/remote/$repo/.github/scripts/$script"
    fi
    chmod +x "$root/remote/$repo/.github/scripts/$script"
  done
  g -C "$root/remote/$repo" add -A
  g -C "$root/remote/$repo" commit -q -m "first"
  g clone -q "$root/remote/$repo" "$root/erplora/$repo"
  echo "LOCAL_SETTING=$repo" > "$root/erplora/$repo/.env"
done
touch "$root/erplora/compose.yaml"
mkdir -p "$root/erplora/blueprints/img"
hub_clone="$root/erplora/hub"

# main moves after the clone fetched: the night must test the newest main, not the clone's.
echo moved > "$root/remote/hub/moved.txt"
g -C "$root/remote/hub" add -A
g -C "$root/remote/hub" commit -q -m "moved"
newest_main="$(git -C "$root/remote/hub" rev-parse HEAD)"
clone_head="$(git -C "$hub_clone" rev-parse HEAD)"

# --- the fakes ---------------------------------------------------------------------------------
# uv: `sync`; `run python manage.py runserver <addr>` logs its environment and sleeps like a server (its pid in
# $FAKE_PIDS); `run python tests/e2e/panel/<seed>.py <args>` logs and exits with FAKE_SEED_EXIT.
cat > "$root/bin/uv" <<'EOF'
#!/usr/bin/env bash
where="$(basename "$PWD")"
case "$*" in
  sync | "sync "*) echo "uv $where $*" >> "$FAKE_CALLS"; exit 0 ;;
  "run python manage.py runserver "*)
    echo "runserver $where $5 DB_NAME=${DB_NAME:-} VITE_DEV_PORT=${VITE_DEV_PORT:-} SAAS_URL=${SAAS_URL:-}" \
      "HUB_INTERNAL_URL=${HUB_INTERNAL_URL:-} EMAIL_FILE_PATH=${EMAIL_FILE_PATH:-}" \
      "ASSISTANT_SERVICE_PROVIDER=${ASSISTANT_SERVICE_PROVIDER:-} E2E_RELAX_LOGIN_RATE_LIMIT=${E2E_RELAX_LOGIN_RATE_LIMIT:-}" \
      "DEMO_SPAWN_RATELIMIT=${DEMO_SPAWN_RATELIMIT:-} HUB_CALLBACK_TEMPLATE=${HUB_CALLBACK_TEMPLATE:-}" \
      "HUB_ADMIN_CALLBACK_URL=${HUB_ADMIN_CALLBACK_URL:-} HTTPS_PROXY=${HTTPS_PROXY:-} CATALOG_DIR=${CATALOG_DIR:-}" \
      >> "$FAKE_CALLS"
    echo "$$" >> "$FAKE_PIDS"
    exec sleep 120 ;;
  "run python tests/e2e/panel/"*)
    shift 2
    echo "seed $where $* DB_NAME=${DB_NAME:-} HUB_INTERNAL_URL=${HUB_INTERNAL_URL:-}" >> "$FAKE_CALLS"
    exit "${FAKE_SEED_EXIT:-0}" ;;
esac
echo "uv unexpected $where $*" >> "$FAKE_CALLS"
exit 2
EOF
# pnpm: `install`; `e2e <args>` logs its arguments, the commit it runs on, its environment and the fake servers
# alive, leaves FAKE_RESULTS as its JSON report and exits with FAKE_E2E_EXIT.
cat > "$root/bin/pnpm" <<'EOF'
#!/usr/bin/env bash
where="$(basename "$PWD")"
case "${1:-}" in
  install) echo "pnpm $where $*" >> "$FAKE_CALLS"; exit 0 ;;
  e2e)
    shift
    echo "e2e $where args=$* HEAD=$(git rev-parse HEAD) E2E_HUB_PORT=${E2E_HUB_PORT:-} VITE_DEV_PORT=${VITE_DEV_PORT:-}" \
      "SAAS_URL=${SAAS_URL:-} DB_NAME=${DB_NAME:-} E2E_SAAS_DB=${E2E_SAAS_DB:-} E2E_SAAS_DIR=${E2E_SAAS_DIR:-}" \
      "E2E_MAIL_DIR=${E2E_MAIL_DIR:-} CI=${CI:-} COMPOSE_FILE=${COMPOSE_FILE:-} CATALOG_DIR=${CATALOG_DIR:-}" \
      "QA_REAL_PROVIDER=${QA_REAL_PROVIDER:-} E2E_OUTPUT_DIR=${E2E_OUTPUT_DIR:-}" >> "$FAKE_CALLS"
    [ -f .env ] && echo "e2e sees .env $(cat .env)" >> "$FAKE_CALLS"
    while read -r pid; do
      kill -0 "$pid" 2> /dev/null && echo "e2e sees a server alive" >> "$FAKE_CALLS"
    done < "$FAKE_PIDS"
    mkdir -p "$E2E_OUTPUT_DIR"
    [ -z "${FAKE_RESULTS:-}" ] || cp "$FAKE_RESULTS" "$E2E_OUTPUT_DIR/results.json"
    exit "${FAKE_E2E_EXIT:-0}" ;;
esac
echo "pnpm unexpected $where $*" >> "$FAKE_CALLS"
exit 2
EOF
# node: tests/e2e/database.ts [--drop] (FAKE_DB_FAILS=hub|saas fails that checkout's creation) and
# tests/e2e/whatsapp-graph.ts <hub port> <saas url>, which prints the SaaS's proxy variables.
cat > "$root/bin/node" <<'EOF'
#!/usr/bin/env bash
where="$(basename "$PWD")"
case "$*" in
  "tests/e2e/database.ts --drop")
    echo "drop $where DB_NAME=${DB_NAME:-} E2E_SAAS_PORT=${E2E_SAAS_PORT:-}" >> "$FAKE_CALLS"; exit 0 ;;
  "tests/e2e/database.ts")
    echo "database $where DB_NAME=${DB_NAME:-} E2E_SAAS_PORT=${E2E_SAAS_PORT:-}" >> "$FAKE_CALLS"
    if [ "${FAKE_DB_FAILS:-}" = "$where" ]; then echo "database.ts: could not migrate" >&2; exit 1; fi
    exit 0 ;;
  "tests/e2e/whatsapp-graph.ts "*)
    echo "graph $where $2 $3" >> "$FAKE_CALLS"
    echo "HTTPS_PROXY=http://127.0.0.1:$(($2 + 9))"
    exit 0 ;;
esac
echo "node unexpected $where $*" >> "$FAKE_CALLS"
exit 2
EOF
cat > "$root/bin/docker" <<'EOF'
#!/usr/bin/env bash
echo "docker $(basename "$PWD") $*" >> "$FAKE_CALLS"
case "$*" in *"select id from base_hub"*) printf '%s\n' 0190-a 0190-b ;; esac
EOF
cat > "$root/bin/curl" <<'EOF'
#!/usr/bin/env bash
echo "curl $*" >> "$FAKE_CALLS"
exit "${FAKE_CURL_EXIT:-0}"
EOF
cat > "$root/bin/lsof" <<'EOF'
#!/usr/bin/env bash
echo "lsof $*" >> "$FAKE_CALLS"
exit 1
EOF
cat > "$root/bin/launchctl" <<'EOF'
#!/usr/bin/env bash
echo "launchctl $*" >> "$FAKE_CALLS"
EOF
cat > "$root/bin/gh-fake" <<'EOF'
#!/usr/bin/env bash
echo "gh $*" >> "$CALLS_LOG"
while [ $# -gt 0 ]; do
  case "$1" in
    --body-file) cat "$2" >> "$BODIES_LOG"; shift ;;
    --comment | --body) printf '%s\n' "$2" >> "$BODIES_LOG"; shift ;;
  esac
  shift
done
case "$CALL" in *"issue list"*) printf '%s\n' "${OPEN_ISSUES:-[]}" ;; esac
EOF
cat > "$root/bin/gh" <<'EOF'
#!/usr/bin/env bash
CALL="$*" exec "$(dirname "$0")/gh-fake" "$@"
EOF
chmod +x "$root"/bin/*

red_report="$root/red.json"
cat > "$red_report" <<'JSON'
{"suites": [{"title": "sale-sales.spec.ts", "file": "sale-sales.spec.ts", "line": 0,
  "specs": [{"title": "charges in cash", "file": "sale-sales.spec.ts", "line": 4,
    "tests": [{"projectName": "", "status": "unexpected",
      "results": [{"status": "failed", "error": {"message": "Error: expect(locator).toBeVisible()"}}]}]}]}],
 "errors": [], "stats": {"expected": 360, "skipped": 0, "unexpected": 1, "flaky": 0}}
JSON
green_report="$root/green.json"
echo '{"suites": [], "errors": [], "stats": {"expected": 361, "skipped": 0, "unexpected": 0, "flaky": 0}}' > "$green_report"

# night [VAR=value...] [-- <arguments>]: one run of nightly-e2e.sh on the clones, red by default (the e2e exits 1
# with one red spec), no issue open. Sets status; its output is $root/out, the fakes' calls $FAKE_CALLS.
night() {
  local settings=()
  while [ $# -gt 0 ] && [ "$1" != -- ]; do
    settings+=("$1")
    shift
  done
  [ $# -eq 0 ] || shift
  : > "$FAKE_CALLS"
  : > "$CALLS_LOG"
  : > "$BODIES_LOG"
  : > "$FAKE_PIDS"
  status=0
  env PATH="$root/bin:$PATH" HOME="$home" HUB_REPO="$hub_clone" ERPLORA_ROOT="$root/erplora" GH_REPO=ERPlora/hub \
    NIGHTLY_START_SECONDS=5 FAKE_E2E_EXIT=1 FAKE_RESULTS="$red_report" \
    ${settings[@]+"${settings[@]}"} bash "$here/nightly-e2e.sh" "$@" > "$root/out" 2>&1 || status=$?
  cat "$FAKE_PIDS" >> "$root/all-pids"
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
calls() { grep -cF -- "$1" "$FAKE_CALLS" || true; }
calls_re() { grep -cE -- "$1" "$FAKE_CALLS" || true; }
line_of() { grep -nF -- "$1" "$FAKE_CALLS" | head -n 1 | cut -d: -f1; }
last_line_of() { grep -nF -- "$1" "$FAKE_CALLS" | tail -n 1 | cut -d: -f1; }
creates() { grep -c '^gh issue create' "$CALLS_LOG" || true; }
gh_writes() { grep -cE '^gh issue (create|comment|close|edit|reopen)' "$CALLS_LOG" || true; }
alive_servers() {
  local n=0 pid
  while read -r pid; do
    if kill -0 "$pid" 2> /dev/null; then n=$((n + 1)); fi
  done < "$FAKE_PIDS"
  echo "$n"
}
worktrees() { git -C "$1" worktree list | wc -l | tr -d ' '; }

# --- a red night ------------------------------------------------------------------------------------
night
expect "a red night ends red (1)" 1 "$status"
expect "it runs every spec once, from the night's Hub" 1 "$(calls_re '^e2e hub ')"
expect "on the newest origin/main, fetched that night" 1 "$(calls "HEAD=$newest_main")"
expect "the shared checkout's HEAD does not move" "$clone_head" "$(git -C "$hub_clone" rev-parse HEAD)"
expect "with Playwright's global timeout" 1 "$(calls_re '^e2e hub args=--global-timeout=21600000 HEAD=')"
expect "on its own stack: Hub port" 1 "$(calls 'E2E_HUB_PORT=39000 VITE_DEV_PORT=39005 SAAS_URL=http://localhost:39001 DB_NAME=hub_e2e_39000 E2E_SAAS_DB=saas_e2e_39001')"
expect "the SaaS's checkout and mail folder" 1 \
  "$(calls "E2E_SAAS_DIR=$nightly/saas E2E_MAIL_DIR=$nightly/saas/.mail-39001 CI=1")"
expect "compose.yaml and the blueprints of erplora-next" 1 \
  "$(calls "COMPOSE_FILE=$root/erplora/compose.yaml CATALOG_DIR=$root/erplora/blueprints/img")"
expect "its report in the night's own folder" 1 "$(calls_re "E2E_OUTPUT_DIR=$nightly/runs/[0-9-]+/test-results\$")"
expect "the checkouts' .env goes with them" 1 "$(calls 'e2e sees .env LOCAL_SETTING=hub')"
expect "both servers are up while it runs" 2 "$(calls 'e2e sees a server alive')"
expect "the Hub's database is made with the stack's name" 1 "$(calls 'database hub DB_NAME=hub_e2e_39000 E2E_SAAS_PORT=')"
expect "the SaaS's, without the Hub's DB_NAME" 1 "$(calls 'database saas DB_NAME= E2E_SAAS_PORT=39001')"
expect "the SaaS is seeded with the ids of a and b" 1 \
  "$(calls 'seed saas tests/e2e/panel/whatsapp_hub_seed.py 0190-a 0190-b DB_NAME=saas_e2e_39001 HUB_INTERNAL_URL=http://127.0.0.1:39000')"
expect "those ids come from the Hub's database" 1 "$(calls_re '^docker .* -d hub_e2e_39000 .*select id from base_hub')"
expect "and with the fake assistant provider" 1 \
  "$(calls 'seed saas tests/e2e/panel/assistant_seed.py gateway http://127.0.0.1:39002/v1 DB_NAME=saas_e2e_39001')"
expect "the SaaS runs as the e2e README says" 1 \
  "$(calls "runserver saas 127.0.0.1:39001 DB_NAME=saas_e2e_39001 VITE_DEV_PORT=39006 SAAS_URL= HUB_INTERNAL_URL=http://localhost:39000 EMAIL_FILE_PATH=$nightly/saas/.mail-39001 ASSISTANT_SERVICE_PROVIDER=e2e-local E2E_RELAX_LOGIN_RATE_LIMIT=True DEMO_SPAWN_RATELIMIT=100/h HUB_CALLBACK_TEMPLATE=http://{slug}.localhost:39000/auth/callback HUB_ADMIN_CALLBACK_URL=http://hubs.localhost:39000/auth/callback HTTPS_PROXY=http://127.0.0.1:39009")"
expect "the Hub runs on its port and database" 1 \
  "$(calls "runserver hub 127.0.0.1:39000 DB_NAME=hub_e2e_39000 VITE_DEV_PORT=39005 SAAS_URL=http://localhost:39001")"
expect "the Hub's runserver sees the blueprints" 1 "$(calls_re "^runserver hub .*CATALOG_DIR=$root/erplora/blueprints/img\$")"
expect "the servers are waited for before the specs" 1 \
  "$([ "$(line_of 'curl')" -lt "$(line_of 'e2e hub')" ] && echo 1 || echo 0)"
expect "both databases are dropped before and after the night" 4 \
  "$(calls_re '^drop (hub DB_NAME=hub_e2e_39000|saas DB_NAME= E2E_SAAS_PORT=39001)')"
expect "the first drops clear an earlier night before the databases are made" 1 \
  "$([ "$(line_of 'drop saas')" -lt "$(line_of 'database hub')" ] && echo 1 || echo 0)"
expect "the last drops come after the specs" 1 \
  "$([ "$(last_line_of 'drop saas')" -gt "$(line_of 'e2e hub')" ] && echo 1 || echo 0)"
expect "no server is left running" 0 "$(alive_servers)"
expect "the night's worktrees are removed" "absent absent" \
  "$([ -e "$nightly/hub" ] && echo present || echo absent) $([ -e "$nightly/saas" ] && echo present || echo absent)"
expect "and unregistered from the clones" "1 1" "$(worktrees "$hub_clone") $(worktrees "$root/erplora/saas")"
expect "it opens the issue of the red night" 1 "$(creates)"
expect "listing the red spec" 1 "$(grep -cF '`sale-sales.spec.ts:4` › charges in cash' "$BODIES_LOG" || true)"
expect "on the commit it ran on" 1 "$(grep -cF "(commit \`${newest_main:0:7}\`)" "$BODIES_LOG" || true)"
expect "pointing at the night's folder from ~" 1 "$(grep -cE '`~/\.erplora/hub-nightly-e2e/runs/[0-9-]+`' "$BODIES_LOG" || true)"
expect "the night leaves its log in its folder" 1 "$(find "$nightly/runs" -name night.log | wc -l | tr -d ' ')"
expect "and that log has what the night did" 1 "$(grep -lF 'Pruebas de navegador del Hub: en rojo' "$nightly"/runs/*/night.log | wc -l | tr -d ' ')"

# --- green -----------------------------------------------------------------------------------------
night FAKE_E2E_EXIT=0 FAKE_RESULTS="$green_report"
expect "a green night ends green (0)" 0 "$status"
expect "and writes no issue" 0 "$(gh_writes)"
night FAKE_E2E_EXIT=0 FAKE_RESULTS="$green_report" \
  OPEN_ISSUES='[{"number": 9, "title": "Pruebas de navegador del Hub en rojo en la pasada nocturna"}]'
expect "a green night with the issue open closes it" 1 "$(grep -c '^gh issue close 9 --reason completed' "$CALLS_LOG" || true)"
night OPEN_ISSUES='[{"number": 9, "title": "Pruebas de navegador del Hub en rojo en la pasada nocturna"}]'
expect "a red night with the issue open comments on it" 1 "$(grep -c '^gh issue comment 9 ' "$CALLS_LOG" || true)"
expect "and opens no second one" 0 "$(creates)"

# --- a night that never reaches the specs --------------------------------------------------------------
night FAKE_DB_FAILS=saas
expect "a night whose SaaS database fails ends red" 1 "$status"
expect "no spec runs" 0 "$(calls_re '^e2e ')"
expect "no server starts" 0 "$(calls_re '^runserver ')"
expect "it opens the issue naming the step" 1 "$(grep -cF 'La pasada no llegó a las specs: falló «la BD del SaaS».' "$BODIES_LOG" || true)"
expect "the Hub's database is still dropped after the failure" 1 \
  "$([ "$(last_line_of 'drop hub')" -gt "$(line_of 'database saas')" ] && echo 1 || echo 0)"
expect "and the worktrees removed" "1 1" "$(worktrees "$hub_clone") $(worktrees "$root/erplora/saas")"

night FAKE_CURL_EXIT=7 NIGHTLY_START_SECONDS=1
expect "a night whose servers never answer ends red" 1 "$status"
expect "no spec runs" 0 "$(calls_re '^e2e ')"
expect "the issue names the start of the servers" 1 "$(grep -cF 'falló «arrancar los servidores»' "$BODIES_LOG" || true)"
expect "the servers it started are stopped" 0 "$(alive_servers)"

# --- not published, on other ports, some specs ----------------------------------------------------
night -- --no-publish
expect "an unpublished red night still ends red" 1 "$status"
expect "and calls no gh at all" 0 "$(grep -c '^gh ' "$CALLS_LOG" || true)"
night NIGHTLY_HUB_PORT=28770 FAKE_E2E_EXIT=0 FAKE_RESULTS="$green_report" -- --spec tests/e2e/sale-sales.spec.ts
expect "NIGHTLY_HUB_PORT moves the whole stack" 1 \
  "$(calls 'E2E_HUB_PORT=28770 VITE_DEV_PORT=28775 SAAS_URL=http://localhost:28771 DB_NAME=hub_e2e_28770 E2E_SAAS_DB=saas_e2e_28771')"
expect "and the SaaS's Vite with it" 1 "$(calls_re '^runserver saas 127\.0\.0\.1:28771 DB_NAME=saas_e2e_28771 VITE_DEV_PORT=28776 ')"
expect "--spec runs only that spec" 1 "$(calls_re '^e2e hub args=--global-timeout=[0-9]+ tests/e2e/sale-sales\.spec\.ts HEAD=')"
night QA_REAL_PROVIDER=1 E2E_HEADED=1
expect "the specs that spend real tokens stay off" 1 "$(calls_re 'QA_REAL_PROVIDER= E2E_OUTPUT_DIR=')"

for arguments in "--bogus" "--spec" "--spec ../../etc/passwd" "--spec tests/e2e/a b.spec.ts" "--spec tests/e2e/x.ts"; do
  # shellcheck disable=SC2086 # the words of $arguments are the script's arguments
  night -- $arguments
  expect "the arguments '$arguments' are refused (2)" 2 "$status"
  expect "and nothing runs" 0 "$(calls_re '^(uv|pnpm|node|e2e|runserver) ')"
done
night NIGHTLY_HUB_PORT=80x
expect "a port that is no port is refused (2)" 2 "$status"
for port in 1023 65527; do
  night NIGHTLY_HUB_PORT="$port"
  expect "port $port, out of 1024–65526, is refused (2)" 2 "$status"
  expect "and nothing runs" 0 "$(calls_re '^(uv|pnpm|node|e2e|runserver) ')"
done

# --- one night at a time --------------------------------------------------------------------------
mkdir -p "$nightly/lock"
sleep 60 &
holder=$!
echo "$holder" >> "$root/all-pids"
echo "$holder" > "$nightly/lock/pid"
night
expect "a night while another runs stops at once (3)" 3 "$status"
expect "and touches nothing" 0 "$(calls_re '^(uv|pnpm|node|e2e|runserver|database|drop) ')"
expect "it leaves the other night's lock" "$holder" "$(cat "$nightly/lock/pid")"
kill "$holder" 2> /dev/null || true
wait "$holder" 2> /dev/null || true
night FAKE_E2E_EXIT=0 FAKE_RESULTS="$green_report"
expect "a lock whose night is gone is taken over" 0 "$status"
expect "and the night runs" 1 "$(calls_re '^e2e hub ')"
expect "the lock is released at the end" absent "$([ -e "$nightly/lock" ] && echo present || echo absent)"

# --- the old nights are pruned -----------------------------------------------------------------------
rm -rf "$nightly/runs"
mkdir -p "$nightly/runs/20200101-000000-1" "$nightly/runs/20200102-000000-1" "$nightly/runs/20200103-000000-1"
night NIGHTLY_KEEP_RUNS=2 FAKE_E2E_EXIT=0 FAKE_RESULTS="$green_report"
expect "only the newest NIGHTLY_KEEP_RUNS nights are kept" 2 "$(find "$nightly/runs" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"
expect "the night before this one is among them" present "$([ -d "$nightly/runs/20200103-000000-1" ] && echo present || echo absent)"

# --- install-launchd ---------------------------------------------------------------------------------
plist="$home/Library/LaunchAgents/com.erplora.hub.nightly-e2e.plist"
# plist_get <key> [<subkey>]: the value in the plist, through Python's plistlib (on macOS and on Linux).
plist_get() {
  python3 - "$plist" "$@" <<'PY'
import plistlib, sys
with open(sys.argv[1], "rb") as f:
    value = plistlib.load(f)
for key in sys.argv[2:]:
    value = value[int(key)] if isinstance(value, list) else value.get(key, "")
print(value)
PY
}
night -- install-launchd
expect "install-launchd ends well" 0 "$status"
expect "it writes the agent's plist" present "$([ -f "$plist" ] && echo present || echo absent)"
expect "with its label" com.erplora.hub.nightly-e2e "$(plist_get Label)"
expect "running the clone's own script" "$hub_clone/.github/scripts/nightly-e2e.sh" "$(plist_get ProgramArguments 0)"
expect "every night at 02:17 by default" "2 17" "$(plist_get StartCalendarInterval Hour) $(plist_get StartCalendarInterval Minute)"
expect "not at load" False "$(plist_get RunAtLoad)"
expect "with the PATH it was installed from" "$root/bin:$PATH" "$(plist_get EnvironmentVariables PATH)"
expect "and the stack's settings" "$hub_clone $root/erplora" \
  "$(plist_get EnvironmentVariables HUB_REPO) $(plist_get EnvironmentVariables ERPLORA_ROOT)"
expect "its output in the nightly folder" "$nightly/launchd.log" "$(plist_get StandardOutPath)"
expect "it reloads the agent" 1 "$(calls_re "^launchctl bootout gui/$(id -u)/com\.erplora\.hub\.nightly-e2e\$")"
expect "and loads it" 1 "$(calls "launchctl bootstrap gui/$(id -u) $plist")"
expect "installing runs no night" 0 "$(calls_re '^(uv|pnpm|node|e2e) ')"
night -- install-launchd --at 04:05
expect "--at sets the hour" "4 5" "$(plist_get StartCalendarInterval Hour) $(plist_get StartCalendarInterval Minute)"
for at in 25:00 4 04:60 x; do
  night -- install-launchd --at "$at"
  expect "--at $at is refused (2)" 2 "$status"
done
g -C "$hub_clone" worktree add -q --detach "$root/linked" 2> /dev/null
night HUB_REPO="$root/linked" -- install-launchd
expect "install-launchd from a linked worktree is refused (2)" 2 "$status"
expect "and says to run it from the main checkout" 1 "$(grep -c 'main checkout' "$root/out" || true)"
expect "the agent still runs the main checkout's script" "$hub_clone/.github/scripts/nightly-e2e.sh" "$(plist_get ProgramArguments 0)"
night HUB_REPO="$root/linked" FAKE_E2E_EXIT=0 FAKE_RESULTS="$green_report"
expect "a night started from a linked worktree runs" 0 "$status"
expect "with the .env of the main checkout, which a linked worktree lacks" 1 "$(calls 'e2e sees .env LOCAL_SETTING=hub')"
night -- uninstall-launchd
expect "uninstall-launchd ends well" 0 "$status"
expect "it unloads the agent" 1 "$(calls_re "^launchctl bootout gui/$(id -u)/com\.erplora\.hub\.nightly-e2e\$")"
expect "and removes its plist" absent "$([ -f "$plist" ] && echo present || echo absent)"

echo
if [ "$failures" -gt 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi
echo "all tests passed"
