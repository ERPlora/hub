#!/usr/bin/env bash
# The Hub's nightly browser run: every spec of tests/e2e, once a night, on the newest origin/main, on the Mac.
# Never a check: a red night stops no PR and no deploy. It keeps ONE open issue instead (e2e-report.sh): a red
# night opens it or comments on it, and the first green night closes it.
#
#   nightly-e2e.sh [--no-publish] [--spec tests/e2e/<name>.spec.ts]...   one night: every spec, or the ones named
#   nightly-e2e.sh install-launchd [--at HH:MM]                           launchd runs it every night (02:17)
#   nightly-e2e.sh uninstall-launchd
#
# A night builds the stack of tests/e2e/README.md («Varias ejecuciones a la vez») by itself: detached worktrees of
# origin/main of the Hub and the SaaS in NIGHTLY_DIR (the shared checkouts only get a fetch), their e2e databases,
# the SaaS seeded with the ids of `a` and `b` and the fake assistant provider, both runservers and `pnpm e2e`.
# Whatever happens, it then stops what listens on the stack's ports, drops both databases and removes the worktrees.
# A step before the specs that fails is a red night too, and the issue names it. Each night's log and Playwright's
# output (results.json, traces, failure screenshots) stay in NIGHTLY_DIR/runs/<night>/, the newest NIGHTLY_KEEP_RUNS.
#
# Environment (default): NIGHTLY_DIR (~/.erplora/hub-nightly-e2e) · HUB_REPO (the clone this script is in) ·
# ERPLORA_ROOT (the folder above it: compose.yaml, blueprints/) · SAAS_REPO ($ERPLORA_ROOT/saas) ·
# NIGHTLY_HUB_PORT (39000; the SaaS on +1, the fake assistant provider on +2, the two Vites on +5 and +6, Meta's
# proxy on +9) · NIGHTLY_MAX_MINUTES (360, Playwright's global timeout) · NIGHTLY_START_SECONDS (300, for the
# servers to answer) · NIGHTLY_KEEP_RUNS (7) · GH_REPO (ERPlora/hub).
# Exit: 0 green · 1 red · 2 usage · 3 another night is running · 4 install-launchd without the script in HUB_REPO.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
LABEL=com.erplora.hub.nightly-e2e
USAGE='usage: nightly-e2e.sh [--no-publish] [--spec tests/e2e/<name>.spec.ts]... | install-launchd [--at HH:MM] | uninstall-launchd'

say() { printf '%s nightly-e2e: %s\n' "$(date '+%F %T')" "$*"; }
usage_error() {
  echo "nightly-e2e: $* (exit 2)" >&2
  echo "$USAGE" >&2
  exit 2
}
number() { case "$2" in '' | *[!0-9]*) usage_error "$1 must be a whole number, not «${2}»" ;; esac }

HUB_REPO="${HUB_REPO:-$(git -C "$here" rev-parse --show-toplevel)}"
ERPLORA_ROOT="${ERPLORA_ROOT:-$(dirname "$HUB_REPO")}"
SAAS_REPO="${SAAS_REPO:-$ERPLORA_ROOT/saas}"
NIGHTLY_DIR="${NIGHTLY_DIR:-$HOME/.erplora/hub-nightly-e2e}"
PORT="${NIGHTLY_HUB_PORT:-39000}"
MAX_MINUTES="${NIGHTLY_MAX_MINUTES:-360}"
START_SECONDS="${NIGHTLY_START_SECONDS:-300}"
KEEP_RUNS="${NIGHTLY_KEEP_RUNS:-7}"
GH_REPO="${GH_REPO:-ERPlora/hub}"
export GH_REPO
number NIGHTLY_HUB_PORT "$PORT"
number NIGHTLY_MAX_MINUTES "$MAX_MINUTES"
number NIGHTLY_START_SECONDS "$START_SECONDS"
number NIGHTLY_KEEP_RUNS "$KEEP_RUNS"
[ "$PORT" -ge 1024 ] && [ "$PORT" -le 65526 ] || usage_error "NIGHTLY_HUB_PORT must be a port from 1024 to 65526"
[ "$KEEP_RUNS" -ge 1 ] || usage_error "NIGHTLY_KEEP_RUNS must keep at least this night"

cmd=night
publish=true
at=02:17
specs=()
case "${1:-}" in install-launchd | uninstall-launchd) cmd="$1" && shift ;; esac
while [ $# -gt 0 ]; do
  case "$cmd:$1" in
    night:--no-publish) publish=false ;;
    night:--spec)
      [ $# -ge 2 ] || usage_error "--spec needs a spec"
      case "$2" in tests/e2e/*.spec.ts) ;; *) usage_error "--spec takes tests/e2e/<name>.spec.ts, not «${2}»" ;; esac
      case "$2" in *..* | *[!A-Za-z0-9._/-]*) usage_error "--spec takes a plain path inside tests/e2e, not «${2}»" ;; esac
      specs+=("$2")
      shift
      ;;
    install-launchd:--at)
      [ $# -ge 2 ] || usage_error "--at needs HH:MM"
      at="$2"
      shift
      ;;
    *) usage_error "unknown argument «${1}»" ;;
  esac
  shift
done

# ── install-launchd / uninstall-launchd: the Mac's timer ──────────────────────────────────────────────────
xml() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }

if [ "$cmd" != night ]; then
  plist="$HOME/Library/LaunchAgents/$LABEL.plist"
  uid="$(id -u)"
  if [ "$cmd" = uninstall-launchd ]; then
    launchctl bootout "gui/$uid/$LABEL" > /dev/null 2>&1 || true
    rm -f "$plist"
    say "$LABEL unloaded, $plist removed"
    exit 0
  fi
  case "$at" in [01][0-9]:[0-5][0-9] | 2[0-3]:[0-5][0-9]) ;; *) usage_error "--at takes HH:MM from 00:00 to 23:59, not «${at}»" ;; esac
  # A linked worktree goes away with its branch, and the agent would then run nothing, every night, unseen.
  git_dir="$(cd "$HUB_REPO" && cd "$(git rev-parse --git-dir)" && pwd)"
  common_dir="$(cd "$HUB_REPO" && cd "$(git rev-parse --git-common-dir)" && pwd)"
  [ "$git_dir" = "$common_dir" ] ||
    usage_error "$HUB_REPO is a linked worktree: run install-launchd from the main checkout of the Hub"
  script="$HUB_REPO/.github/scripts/nightly-e2e.sh"
  [ -x "$script" ] || { echo "nightly-e2e: $script is missing or not executable (exit 4)" >&2; exit 4; }
  mkdir -p "$(dirname "$plist")" "$NIGHTLY_DIR"
  tmp="$plist.tmp.$$"
  write_plist() {
    printf '<?xml version="1.0" encoding="UTF-8"?>\n'
    printf '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    printf '<!-- Written by nightly-e2e.sh install-launchd: run it again instead of editing this file. -->\n'
    printf '<plist version="1.0">\n<dict>\n'
    printf '\t<key>Label</key>\n\t<string>%s</string>\n' "$LABEL"
    printf '\t<key>ProgramArguments</key>\n\t<array>\n\t\t<string>%s</string>\n\t</array>\n' "$(xml "$script")"
    printf '\t<key>EnvironmentVariables</key>\n\t<dict>\n'
    for pair in "PATH=$PATH" "HOME=$HOME" "HUB_REPO=$HUB_REPO" "ERPLORA_ROOT=$ERPLORA_ROOT" "SAAS_REPO=$SAAS_REPO" \
      "NIGHTLY_DIR=$NIGHTLY_DIR" "NIGHTLY_HUB_PORT=$PORT" "GH_REPO=$GH_REPO"; do
      printf '\t\t<key>%s</key>\n\t\t<string>%s</string>\n' "${pair%%=*}" "$(xml "${pair#*=}")"
    done
    printf '\t</dict>\n'
    printf '\t<key>StartCalendarInterval</key>\n\t<dict>\n'
    printf '\t\t<key>Hour</key>\n\t\t<integer>%d</integer>\n' "$((10#${at%%:*}))"
    printf '\t\t<key>Minute</key>\n\t\t<integer>%d</integer>\n' "$((10#${at##*:}))"
    printf '\t</dict>\n'
    printf '\t<key>RunAtLoad</key>\n\t<false/>\n'
    printf '\t<key>StandardOutPath</key>\n\t<string>%s</string>\n' "$(xml "$NIGHTLY_DIR/launchd.log")"
    printf '\t<key>StandardErrorPath</key>\n\t<string>%s</string>\n' "$(xml "$NIGHTLY_DIR/launchd.log")"
    printf '</dict>\n</plist>\n'
  }
  if ! write_plist > "$tmp" || ! mv -f "$tmp" "$plist"; then
    rm -f "$tmp"
    echo "nightly-e2e: cannot write $plist (exit 1)" >&2
    exit 1
  fi
  launchctl bootout "gui/$uid/$LABEL" > /dev/null 2>&1 || true
  launchctl bootstrap "gui/$uid" "$plist" || { echo "nightly-e2e: launchctl bootstrap gui/$uid $plist failed (exit 1)" >&2; exit 1; }
  say "$LABEL loaded: every night at $at ($plist; what launchd sees, in $NIGHTLY_DIR/launchd.log)"
  exit 0
fi

# ── one night ───────────────────────────────────────────────────────────────────────────────────────────
mkdir -p "$NIGHTLY_DIR/runs"
lock="$NIGHTLY_DIR/lock"
if ! mkdir "$lock" 2> /dev/null; then
  holder="$(cat "$lock/pid" 2> /dev/null || true)"
  if [ -n "$holder" ] && kill -0 "$holder" 2> /dev/null; then
    say "another night is running (pid $holder): nothing to do (exit 3)"
    exit 3
  fi
  say "the night of pid ${holder:-?} is gone: taking its lock over"
  rm -rf "$lock"
  mkdir "$lock"
fi
echo "$$" > "$lock/pid"

run="$NIGHTLY_DIR/runs/$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$run"
log="$run/night.log"
if [ -t 1 ]; then exec > >(tee -a "$log") 2>&1; else exec >> "$log" 2>&1; fi

HUB_PORT="$PORT"
SAAS_PORT=$((PORT + 1))
PROVIDER_PORT=$((PORT + 2))
HUB_VITE=$((PORT + 5))
SAAS_VITE=$((PORT + 6))
GRAPH_PORT=$((PORT + 9))
HUB_DB="hub_e2e_$HUB_PORT"
SAAS_DB="saas_e2e_$SAAS_PORT"
hub_wt="$NIGHTLY_DIR/hub"
saas_wt="$NIGHTLY_DIR/saas"
mail="$saas_wt/.mail-$SAAS_PORT"
export COMPOSE_FILE="$ERPLORA_ROOT/compose.yaml"
# Each command gets its stack's variables explicitly: none may come from the shell that started the night (a
# worker's DB_NAME would point the SaaS at a Hub database), and the specs that spend real tokens or open a
# visible browser stay off.
unset DB_NAME SAAS_URL E2E_HUB_PORT VITE_DEV_PORT E2E_SAAS_DB E2E_SAAS_DIR E2E_MAIL_DIR E2E_SAAS_PORT \
  HUB_INTERNAL_URL EMAIL_FILE_PATH E2E_OUTPUT_DIR CATALOG_DIR QA_REAL_PROVIDER E2E_HEADED
hub_env=(E2E_HUB_PORT="$HUB_PORT" VITE_DEV_PORT="$HUB_VITE" SAAS_URL="http://localhost:$SAAS_PORT" DB_NAME="$HUB_DB"
  E2E_SAAS_DB="$SAAS_DB" E2E_SAAS_DIR="$saas_wt" E2E_MAIL_DIR="$mail" CATALOG_DIR="$ERPLORA_ROOT/blueprints/img")
saas_env=(DB_NAME="$SAAS_DB" VITE_DEV_PORT="$SAAS_VITE" HUB_INTERNAL_URL="http://localhost:$HUB_PORT"
  EMAIL_FILE_PATH="$mail" ASSISTANT_SERVICE_PROVIDER=e2e-local E2E_RELAX_LOGIN_RATE_LIMIT=True
  DEMO_SPAWN_RATELIMIT=100/h HUB_CALLBACK_TEMPLATE="http://{slug}.localhost:$HUB_PORT/auth/callback"
  HUB_ADMIN_CALLBACK_URL="http://hubs.localhost:$HUB_PORT/auth/callback")
own_pgid="$(ps -o pgid= -p $$ | tr -d ' ')"
started=()
current_step=""
cleaned=0

# step <label>: what the night is doing, so a failure names it in the issue.
step() {
  current_step="$1"
  say "step: $1"
}

fetch_main() { git -C "$HUB_REPO" fetch --quiet origin && git -C "$SAAS_REPO" fetch --quiet origin; }

remove_worktree() { # <repo> <dir>: the night's own, so --force (it has submodules and untracked dependencies)
  if [ -e "$2" ]; then git -C "$1" worktree remove --force "$2" 2> /dev/null || rm -rf "$2"; fi
  git -C "$1" worktree prune
}

make_worktree() { # <repo> <dir>
  remove_worktree "$1" "$2" &&
    git -C "$1" worktree add --quiet --detach "$2" origin/main &&
    git -C "$2" submodule update --init --quiet &&
    { [ ! -f "$1/.env" ] || cp "$1/.env" "$2/.env"; }
}

make_worktrees() { make_worktree "$HUB_REPO" "$hub_wt" && make_worktree "$SAAS_REPO" "$saas_wt"; }

dependencies() { (cd "$1" && uv sync && pnpm install --frozen-lockfile); }

drop_hub_database() { (cd "$hub_wt" && env "${hub_env[@]}" node tests/e2e/database.ts --drop); }
drop_saas_database() { (cd "$saas_wt" && env E2E_SAAS_PORT="$SAAS_PORT" node tests/e2e/database.ts --drop); }

# What an earlier night left when it was cut (the Mac switched off): its servers and its databases.
clear_earlier_night() { stop_stack && drop_hub_database && drop_saas_database; }

hub_database() { (cd "$hub_wt" && env "${hub_env[@]}" node tests/e2e/database.ts); }
saas_database() { (cd "$saas_wt" && env E2E_SAAS_PORT="$SAAS_PORT" node tests/e2e/database.ts); }

seed_saas() {
  local ids
  ids="$(cd "$hub_wt" && docker compose exec -T postgres psql -U hub -d "$HUB_DB" -At \
    -c "select id from base_hub where slug in ('a', 'b') order by slug")" || return 1
  [ "$(printf '%s\n' "$ids" | grep -c .)" = 2 ] || {
    say "the Hub's database should hold a and b, and holds «${ids}»"
    return 1
  }
  # shellcheck disable=SC2086 # the two ids, a's first, are two arguments
  (cd "$saas_wt" && env DB_NAME="$SAAS_DB" HUB_INTERNAL_URL="http://127.0.0.1:$HUB_PORT" \
    uv run python tests/e2e/panel/whatsapp_hub_seed.py $ids) &&
    (cd "$saas_wt" && env DB_NAME="$SAAS_DB" \
      uv run python tests/e2e/panel/assistant_seed.py gateway "http://127.0.0.1:$PROVIDER_PORT/v1")
}

start_server() { # <dir> <log> <env and command...>: its own process group, so stopping it stops its Vite too
  local dir="$1" out="$2"
  shift 2
  set -m
  (cd "$dir" && exec env "$@") >> "$out" 2>&1 &
  started+=("$!")
  set +m
}

answers() { curl -fsS -o /dev/null --max-time 5 "$1" 2> /dev/null; }

start_stack() {
  local graph deadline=$((SECONDS + START_SECONDS)) pid
  graph="$(cd "$hub_wt" && node tests/e2e/whatsapp-graph.ts "$HUB_PORT" "http://localhost:$SAAS_PORT")" || {
    say "whatsapp-graph.ts failed: the SaaS starts without Meta's proxy and the WhatsApp specs will say what is missing"
    graph=""
  }
  # shellcheck disable=SC2086 # whatsapp-graph.ts prints VAR=value words for env
  start_server "$saas_wt" "$run/saas.log" "${saas_env[@]}" $graph uv run python manage.py runserver "127.0.0.1:$SAAS_PORT"
  start_server "$hub_wt" "$run/hub.log" "${hub_env[@]}" uv run python manage.py runserver "127.0.0.1:$HUB_PORT"
  while ! { answers "http://127.0.0.1:$HUB_PORT/healthz" &&
    answers "http://localhost:$HUB_VITE/static/spa/@vite/client" &&
    answers "http://127.0.0.1:$SAAS_PORT/healthz"; }; do
    for pid in "${started[@]}"; do
      kill -0 "$pid" 2> /dev/null || { say "a server exited before answering: see hub.log and saas.log"; return 1; }
    done
    [ "$SECONDS" -lt "$deadline" ] || { say "the servers did not answer within $START_SECONDS s"; return 1; }
    sleep 2
  done
}

listeners() { # the pids listening on the stack's ports (a spec may restart the Hub's runserver on its own)
  local port
  for port in "$HUB_PORT" "$SAAS_PORT" "$PROVIDER_PORT" "$HUB_VITE" "$SAAS_VITE" "$GRAPH_PORT"; do
    lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2> /dev/null || true
  done
}

signal_all() { # <signal>
  local pid pgid
  for pid in ${started[@]+"${started[@]}"}; do kill "-$1" -- "-$pid" 2> /dev/null || true; done
  for pid in $(listeners); do
    pgid="$(ps -o pgid= -p "$pid" 2> /dev/null | tr -d ' ')"
    if [ -n "$pgid" ] && [ "$pgid" != "$own_pgid" ]; then
      kill "-$1" -- "-$pgid" 2> /dev/null || true
    else
      kill "-$1" "$pid" 2> /dev/null || true
    fi
  done
}

anything_left() {
  local pid
  for pid in ${started[@]+"${started[@]}"}; do kill -0 "$pid" 2> /dev/null && return 0; done
  [ -n "$(listeners)" ]
}

stop_stack() {
  local waited=0
  signal_all TERM
  while anything_left && [ "$waited" -lt 20 ]; do
    sleep 1
    waited=$((waited + 1))
  done
  if anything_left; then
    say "still running after 20 s: killing it"
    signal_all KILL
  fi
  started=()
  return 0
}

run_specs() {
  (cd "$hub_wt" && env "${hub_env[@]}" CI=1 E2E_OUTPUT_DIR="$run/test-results" \
    pnpm e2e --global-timeout=$((MAX_MINUTES * 60000)) ${specs[@]+"${specs[@]}"})
}

# Never stops half way: a drop or a removal that fails is said here and tried again by the next night.
clean_up() {
  [ "$cleaned" = 0 ] || return 0
  cleaned=1
  say "clean-up: servers, databases and worktrees"
  stop_stack
  if [ -d "$hub_wt" ]; then drop_hub_database || say "could not drop $HUB_DB: the next night tries again"; fi
  if [ -d "$saas_wt" ]; then drop_saas_database || say "could not drop $SAAS_DB: the next night tries again"; fi
  remove_worktree "$HUB_REPO" "$hub_wt" || say "could not remove $hub_wt"
  remove_worktree "$SAAS_REPO" "$saas_wt" || say "could not remove $saas_wt"
}

prune_runs() {
  local all count
  all="$(find "$NIGHTLY_DIR/runs" -mindepth 1 -maxdepth 1 -type d | sort)"
  count="$(printf '%s\n' "$all" | grep -c . || true)"
  [ "$count" -gt "$KEEP_RUNS" ] || return 0
  printf '%s\n' "$all" | head -n "$((count - KEEP_RUNS))" | while read -r old; do rm -rf "$old"; done
}

# Without an `exit` of its own the trap keeps the night's exit status.
trap 'clean_up || true; rm -rf "$lock"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

say "night in $run, Hub on $HUB_PORT, SaaS on $SAAS_PORT, databases $HUB_DB and $SAAS_DB"
result=failure
failed_step=""
if step "traer origin/main" && fetch_main &&
  step "los worktrees de origin/main" && make_worktrees &&
  step "las dependencias del Hub" && dependencies "$hub_wt" &&
  step "las dependencias del SaaS" && dependencies "$saas_wt" &&
  step "borrar lo que dejó una noche anterior" && clear_earlier_night &&
  step "la BD del Hub" && hub_database &&
  step "la BD del SaaS" && saas_database &&
  step "la siembra del SaaS" && seed_saas &&
  step "arrancar los servidores" && start_stack; then
  step "las specs"
  if run_specs; then result=success; fi
else
  failed_step="$current_step"
  say "failed: $failed_step"
fi
sha="$(git -C "$HUB_REPO" rev-parse origin/main 2> /dev/null || echo unknown)"
clean_up

status=0
[ "$result" = success ] || status=1
RESULT="$result" REPORT="$run/test-results/results.json" STEP="$failed_step" SHA="$sha" RUN_DIR="$run" \
  PUBLISH="$publish" bash "$here/e2e-report.sh" || {
  say "the report failed: the night's result did not reach GitHub"
  status=1
}
prune_runs
say "night over: $result"
exit "$status"
