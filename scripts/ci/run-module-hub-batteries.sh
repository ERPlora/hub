#!/usr/bin/env bash
# Run the module `*.hub.test.py|sh` batteries against a LIVE kernel — one hub per module.
#
# Prints a per-battery report to STDOUT and the verdict to STDERR.
# Exit codes: 0 = every battery ran and passed · 1 = a verdict (a battery failed, a module never
# installed, an exemption went stale) · 2 = environment (no catalogue, no server binary, no
# python3, a hub that never came up). The separation is the one `kernel-e2e-targets.sh` and
# `module-hub-batteries.sh` already draw, and it matters for the same reason: a runner that could
# not start must never read as «the module is broken».
#
# Regression test for ERPlora/hub#1381; cases in `scripts/tests/run-module-hub-batteries.test.sh`.
#
# ── WHY THIS EXISTS ─────────────────────────────────────────────────────────────────────────
# hub#1264 moves the e2e that assert MODULE behaviour out of the hub and into each module's own
# `erplora test` battery. `scripts/ci/module-hub-batteries.sh` proves the battery EXISTS where the
# slice promised; it cannot prove it PASSES. Nothing ran one: on 2026-08-30 hub#1372 deleted
# `services_package_redeem_e2e.rs` — 391 lines this very workflow ran — and its replacement
# battery was executed by NOBODY for four days, both CIs green. The module gate reports a hub
# battery as `⚠ … no se ha corrido` and passes anyway (`run-batteries.mjs`, `notRun`), so the
# warning is real and nothing acts on it. This script is what acts on it.
#
# ── WHY NOT `erplora test --against-hub` ────────────────────────────────────────────────────
# The toolkit already knows how to do this (module-toolkit#110) and cannot be used here, measured
# on 2026-09-01 and re-checked on 2026-09-03 against `module-toolkit@296d017`:
#
#   1. `withHubRuntime` mounts ONE directory (`-v ${dir}:${mountPoint}:ro`) and installs ONE
#      module, so 8 of the 11 modules with a battery come up missing their `depends_on` chain and
#      exit 1 on `_require_installed` (module-toolkit#135, still open).
#   2. `@erplora/module-toolkit` is `"private": true` with `file:../hub/packages/module-sdk`,
#      `file:../hub/packages/module-types` and `file:../outfitkit` dependencies — it cannot be
#      installed from a checkout of `ERPlora/hub`.
#   3. And no secret of `ERPlora/hub` reaches those private checkouts (`GITHUB_TOKEN` and
#      `MODULES_DEPLOY_KEYS`, one deploy key per MODULE repo).
#
# None of the three has to be solved to run a battery, because a battery is a plain script that
# reads `ERPLORA_HUB_BASE_URL` and talks HTTP (`hub_harness.py`). What it needs is a kernel with
# the chain installed, and `HUB_MODULES_DIR` + `HUB_DEV_MODE=1` already installs a whole catalogue
# in `depends_on` order (`install_all_from_dir`, topo-sorted since hub#16). So the runner boots the
# server built from THIS ref — not a published image — which is also what makes the run mean what
# this workflow claims: the kernel under test against the modules as published.
#
# ── ONE HUB PER MODULE, AND WHY IT IS NOT A PREFERENCE ──────────────────────────────────────
# Measured on 2026-09-03 against `origin/develop@34fa7c3c` with the 27 published modules installed:
# all 26 declared batteries against ONE shared hub → 22 pass, 4 fail; the same batteries with a
# hub each → every one of them passes. The failures were not the modules' fault:
# `cash_register/tests/session.hub.test.py` completes real sales, whose auto-F2
# invoices burn TICKET numbers through the outbox asynchronously, and
# `invoice/tests/from_sale.hub.test.py` then reads N+2 where it asserts N+1. A shared hub reports
# failures that belong to nobody, which is worse than not running at all.
set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)

catalogue="${ERPLORA_MODULES_DIR:-}"
manifest="$script_dir/module-hub-batteries.txt"
server="${ERPLORA_HUB_SERVER_BIN:-$repo_root/target/debug/erplora-server}"
database_url="${ERPLORA_BATTERIES_DATABASE_URL:-}"
db_admin_cmd="${ERPLORA_DB_ADMIN_CMD:-}"
pg_container="${ERPLORA_PG_CONTAINER:-}"
pg_user="${ERPLORA_PG_USER:-postgres}"
bind_host="127.0.0.1"
ready_timeout="${ERPLORA_HUB_READY_TIMEOUT:-180}"

# ── The exemptions ──────────────────────────────────────────────────────────────────────────
# A module whose battery CANNOT run here yet, each with its issue and its reason. They are
# SELF-EXPIRING: if an exempted module does install, the run goes RED demanding the line be
# deleted. An exemption nobody is forced to revisit is exactly how the hole this script closes
# would come back.
#
# EMPTY since hub#1483, and the self-expiry is what emptied it: `verifactu` was the only entry —
# it could not INSTALL without a Cloud machine token for its `static_files`, the one module of the
# 27 published that declares any. hub#1477 gave the runtime a disk backend for them
# (`ModuleDiskStorage`, `crates/server/src/module_storage.rs`), chosen under `HUB_DEV_MODE=1`,
# which is exactly how this runner boots its hubs — so the module installed, the run went red
# demanding the line go, and it went. Its batteries run like everyone else's now.
#
# An empty table is a normal state, not a special case: see `exemption_for` and case 10 of
# `scripts/tests/run-module-hub-batteries.test.sh` for the shell trap it hides.
exemptions=()

usage() {
    cat <<'USAGE'
usage: run-module-hub-batteries.sh [options]

  --catalogue <dir>       published module catalogue (default: $ERPLORA_MODULES_DIR)
  --manifest <file>       reviewed battery list (default: scripts/ci/module-hub-batteries.txt)
  --server <bin>          erplora-server binary built from this ref
  --database-url <dsn>    admin DSN; its database name is swapped per module
  --db-admin-cmd <cmd>    command that takes `-c <SQL>` (default: docker exec <container> psql -U <user>)
  --pg-container <name>   Postgres container, used to build the default --db-admin-cmd
  --pg-user <user>        Postgres superuser for the default --db-admin-cmd (default: postgres)
  --bind-host <host>      where the hubs listen (default: 127.0.0.1)
  --ready-timeout <secs>  how long a hub gets to answer /readyz UP (default: 180)
  --exempt <id=issue reason>  add an exemption on top of the built-in ones
USAGE
}

extra_exemptions=()
while [ $# -gt 0 ]; do
    case "$1" in
        --catalogue) catalogue="$2"; shift 2 ;;
        --manifest) manifest="$2"; shift 2 ;;
        --server) server="$2"; shift 2 ;;
        --database-url) database_url="$2"; shift 2 ;;
        --db-admin-cmd) db_admin_cmd="$2"; shift 2 ;;
        --pg-container) pg_container="$2"; shift 2 ;;
        --pg-user) pg_user="$2"; shift 2 ;;
        --bind-host) bind_host="$2"; shift 2 ;;
        --ready-timeout) ready_timeout="$2"; shift 2 ;;
        --exempt) extra_exemptions+=("$2"); shift 2 ;;
        -h | --help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done
if [ "${#extra_exemptions[@]}" -gt 0 ]; then
    exemptions+=("${extra_exemptions[@]}")
fi

env_error() { printf 'run-module-hub-batteries: %s\n' "$1" >&2; exit 2; }

# ── The environment, checked before anything is created ─────────────────────────────────────
command -v python3 > /dev/null 2>&1 \
    || env_error 'no python3 on PATH: the batteries ARE python scripts, there is nothing to run'
[ -n "$catalogue" ] \
    || env_error 'no catalogue. Pass --catalogue <dir> or set ERPLORA_MODULES_DIR (the directory
  `scripts/materialize-published-modules.sh --dest` leaves behind)'
[ -d "$catalogue" ] || env_error "no such catalogue directory: $catalogue"
[ -f "$manifest" ] || env_error "no such manifest: $manifest"
[ -x "$server" ] \
    || env_error "no erplora-server binary at $server (build it: \`cargo build -p erplora-server\`)"
[ -n "$database_url" ] \
    || env_error 'no --database-url. It is the ADMIN DSN; the database name is swapped per module'

if [ -z "$db_admin_cmd" ]; then
    [ -n "$pg_container" ] \
        || env_error 'no --db-admin-cmd and no --pg-container: the runner needs a way to create a
  scratch database per module. Pass --pg-container <name> (it shells out to
  `docker exec <name> psql -U <user>`) or --db-admin-cmd "<command taking -c SQL>"'
    command -v docker > /dev/null 2>&1 \
        || env_error 'no docker on PATH and --pg-container was given'
    db_admin_cmd="docker exec -i $pg_container psql -U $pg_user -v ON_ERROR_STOP=1"
fi
read -r -a db_admin <<< "$db_admin_cmd"

# ── The worklist ────────────────────────────────────────────────────────────────────────────
# Discovery and the pairing verdict live in ONE place, `module-hub-batteries.sh --batteries`: a
# second copy of the "what is a hub battery" rule is how the two halves drift apart. Its exit code
# is passed straight through — a list that disagrees with the catalogue is already a red with its
# own explanation, and running batteries on top of it would only bury it.
batteries=$("$script_dir/module-hub-batteries.sh" --catalogue "$catalogue" --manifest "$manifest" --batteries)
guard_rc=$?
if [ "$guard_rc" -ne 0 ]; then
    printf 'run-module-hub-batteries: the pairing guard refused the list (exit %s); nothing was run.\n' \
        "$guard_rc" >&2
    exit "$guard_rc"
fi
if [ -z "$batteries" ]; then
    printf 'run-module-hub-batteries: the catalogue carries no `*.hub.test.py|sh` battery at all.\n' >&2
    printf '  That is not a pass: hub#1264 has retired kernel e2e against 25 of them. Check\n' >&2
    printf '  %s and the catalogue in %s.\n' "$manifest" "$catalogue" >&2
    exit 2
fi

modules=$(printf '%s\n' "$batteries" | sed 's|/.*||' | awk '!seen[$0]++')

exemption_for() { # $1=module id → prints "issue reason", empty when not exempt
    local entry
    # The count guard is not style: the table is EMPTY today (hub#1483 deleted the last entry) and
    # `"${arr[@]}"` on an empty array under `set -u` is an unbound variable on bash 3.2 — still
    # `/bin/bash` on macOS. Without it this function printed a shell error per module into STDERR,
    # which is the channel the verdict itself is written to, and reached «not exempt» through the
    # failed subshell instead of through its own logic.
    [ "${#exemptions[@]}" -gt 0 ] || return 1
    for entry in "${exemptions[@]}"; do
        case "$entry" in "$1="*) printf '%s' "${entry#*=}"; return 0 ;; esac
    done
    return 1
}

# ── Small helpers over the runtime, in python3 because it is already a hard requirement ─────
free_port() {
    python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
}

# `GET <path>` → body on stdout, non-zero when it could not be read. Deliberately quiet: the
# caller decides what an unreachable hub means, and it is never the same thing twice.
http_get() { # $1=base url, $2=path
    python3 - "$1$2" <<'PY'
import sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1], timeout=15) as res:
        sys.stdout.write(res.read().decode())
except Exception as err:
    print(err, file=sys.stderr)
    sys.exit(1)
PY
}

# 🔴 These two READ STDIN, so their program cannot come from a heredoc: `python3 - <<EOF`
# makes the heredoc itself stdin and the piped body is gone — the helper then "fails" on every
# valid answer, the readiness loop spins for the whole timeout and the job dies mute. Measured the
# hard way on 2026-09-03.
json_field() { # stdin=json, $1=field name: "status" or "hub_id"
    python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get(sys.argv[1], "") or "")
except Exception:
    sys.exit(1)' "$1"
}

installed_ids() { # stdin=/api/modules body → one id per line
    python3 -c 'import json,sys
try:
    body = json.load(sys.stdin)
except Exception:
    sys.exit(1)
for m in body.get("data", []) or []:
    print(m.get("id", ""))'
}

# A battery that exits 0 without testing is the green this whole file exists to remove. WIDER than
# the toolkit's own `looksSkipped` (`/^SKIPPED:/`), which misses `SKIPPED (SQL half):` — ten
# `customers` batteries printed exactly that and read as green (module-toolkit#137).
looks_skipped() { grep -qE '^[[:space:]]*SKIPPED' <<<"$1"; }

dsn_for() { # $1=database name → the admin DSN with its database swapped
    python3 - "$database_url" "$1" <<'PY'
import sys
from urllib.parse import urlsplit, urlunsplit
u = urlsplit(sys.argv[1])
print(urlunsplit((u.scheme, u.netloc, "/" + sys.argv[2], u.query, u.fragment)))
PY
}

# 🔴 `< /dev/null` is not tidiness. The default admin command is `docker exec -i …`, and `-i`
# attaches stdin: called from inside a `while read` loop it SWALLOWS THE REST OF THE LIST. The
# first version of this script ran `appointments` and then reported «2 batteries passed» and exit
# 0 — a green that had silently skipped ten modules. Every subprocess in the loops below gets the
# same treatment, and the worklist is read on a dedicated fd for the same reason.
db_exec() { # $1=SQL
    "${db_admin[@]}" -c "$1" > /dev/null 2>&1 < /dev/null
}

# ── Per-module state, torn down unconditionally ─────────────────────────────────────────────
server_pid=""
scratch_db=""
server_log=""
work_dir=$(mktemp -d "${TMPDIR:-/tmp}/erplora-hub-batteries.XXXXXX")

teardown_module() {
    if [ -n "$server_pid" ] && kill -0 "$server_pid" 2> /dev/null; then
        kill "$server_pid" 2> /dev/null
        # A hub left listening poisons the next module's port scan and keeps a connection on the
        # database that is about to be dropped.
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            kill -0 "$server_pid" 2> /dev/null || break
            sleep 0.5
        done
        kill -9 "$server_pid" 2> /dev/null
        wait "$server_pid" 2> /dev/null
    fi
    server_pid=""
    if [ -n "$scratch_db" ]; then
        db_exec "DROP DATABASE IF EXISTS \"$scratch_db\" WITH (FORCE)" \
            || db_exec "DROP DATABASE IF EXISTS \"$scratch_db\""
    fi
    scratch_db=""
}

cleanup() {
    teardown_module
    rm -rf "$work_dir"
}
trap cleanup EXIT HUP INT TERM

failures=""
env_failures=""
not_run=""
ran_ok=0
run_stamp="$$_$(date +%s)"

# ── The run ─────────────────────────────────────────────────────────────────────────────────
printf '%s\n' "$modules" > "$work_dir/modules.list"
printf '%s\n' "$batteries" > "$work_dir/batteries.list"
expected_modules=$(grep -c . "$work_dir/modules.list")
seen_modules=0

while IFS= read -r module <&9; do
    [ -n "$module" ] || continue
    seen_modules=$((seen_modules + 1))
    exempt_note=$(exemption_for "$module") && is_exempt=1 || is_exempt=0

    scratch_db="hubbat_${module}_${run_stamp}"
    scratch_db=$(printf '%s' "$scratch_db" | tr -c 'a-zA-Z0-9_' '_')
    if ! db_exec "CREATE DATABASE \"$scratch_db\""; then
        scratch_db=""
        env_failures="$env_failures
  - $module: could not create the scratch database (\`${db_admin[*]} -c 'CREATE DATABASE …'\`)"
        teardown_module
        continue
    fi

    port=$(free_port)
    base_url="http://$bind_host:$port"
    server_log="$work_dir/$module.log"
    # `CI` + an explicit closed loopback `HUB_CLOUD_API_URL`: with `HUB_DEV_MODE=1` and no explicit
    # cloud url the server REFUSES to boot under CI rather than default to production (hub#1279).
    HUB_DEV_MODE=1 \
    HUB_AUTH=dev \
    HUB_CLOUD_API_URL="http://127.0.0.1:9" \
    HUB_DATABASE_URL="$(dsn_for "$scratch_db")" \
    HUB_MODULES_DIR="$catalogue" \
    HUB_MEDIA_DIR="$work_dir/$module-media" \
    HUB_BIND="$bind_host:$port" \
        "$server" > "$server_log" 2>&1 < /dev/null &
    server_pid=$!

    ready=0
    deadline=$(( $(date +%s) + ready_timeout ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if ! kill -0 "$server_pid" 2> /dev/null; then break; fi
        body=$(http_get "$base_url" /readyz 2> /dev/null < /dev/null) || { sleep 1; continue; }
        status=$(printf '%s' "$body" | json_field status 2> /dev/null)
        # `UP` is the only answer that counts; `DEGRADED` means a check failed and the batteries
        # below would blame the module for it.
        if [ "$status" = "UP" ]; then ready=1; break; fi
        sleep 1
    done
    if [ "$ready" -ne 1 ]; then
        env_failures="$env_failures
  - $module: the hub never answered /readyz UP within ${ready_timeout}s. Its own log tail:
$(tail -20 "$server_log" 2> /dev/null | sed 's/^/      /')"
        teardown_module
        continue
    fi

    # What the RUNTIME says is installed — not what the catalogue holds, and not what /readyz
    # counts. The dev boot scan is tolerant on purpose (`install_all_from_dir` logs ✗ and carries
    # on) and /readyz counts only what reached the database, so a module that never installed is
    # invisible from both ends. That is how `verifactu` came up missing with `missing: []`.
    installed=$(http_get "$base_url" /api/modules < /dev/null | installed_ids)
    if grep -qx "$module" <<<"$installed"; then
        module_installed=1
    else
        module_installed=0
    fi

    if [ "$is_exempt" -eq 1 ]; then
        if [ "$module_installed" -eq 1 ]; then
            failures="$failures
  - $module is EXEMPT ($exempt_note) but it installed just fine. The exemption is stale: delete
    its line from \`exemptions\` in $0 and let its batteries run."
        else
            reason=$(grep -m1 -F "✗ módulo" "$server_log" 2> /dev/null | sed 's/^/      /')
            not_run="$not_run
  - $module: NOT RUN — $exempt_note
${reason:-      (the runtime never reported why; see $server_log)}"
        fi
        teardown_module
        continue
    fi

    if [ "$module_installed" -ne 1 ]; then
        failures="$failures
  - $module is in the reviewed list but the runtime does NOT have it installed, so its batteries
    assert nothing. This is never a skip. Installed: $(printf '%s' "$installed" | tr '\n' ' ')
$(grep -m1 -F "✗ módulo" "$server_log" 2> /dev/null | sed 's/^/      /')"
        teardown_module
        continue
    fi

    hub_id=$(http_get "$base_url" /api/hub/context < /dev/null | json_field hub_id 2> /dev/null)
    upper=$(printf '%s' "$module" | tr '[:lower:]-' '[:upper:]_')

    while IFS= read -r entry <&8; do
        [ -n "$entry" ] || continue
        case "$entry" in "$module/"*) ;; *) continue ;; esac
        rel=${entry#*/}
        file="$catalogue/$module/$rel"
        if [ ! -f "$file" ]; then
            failures="$failures
  - $entry: the battery is not in the published module"
            continue
        fi
        case "$rel" in *.sh) interpreter=bash ;; *) interpreter=python3 ;; esac
        output=$(cd "$catalogue/$module" && env \
            ERPLORA_HUB_BASE_URL="$base_url" \
            "${upper}_HUB_BASE_URL=$base_url" \
            ERPLORA_HUB_ID="$hub_id" \
            ERPLORA_MODULE_ID="$module" \
            ERPLORA_HUB_IMAGE="$server" \
            "$interpreter" "$rel" 2>&1 < /dev/null)
        code=$?
        if [ "$code" -ne 0 ]; then
            failures="$failures
  - $entry: the battery FAILED (exit $code)
$(printf '%s\n' "$output" | tail -25 | sed 's/^/      /')"
        elif looks_skipped "$output"; then
            failures="$failures
  - $entry: the battery SKIPPED ITSELF and still exited 0 — a green that proves nothing, with a
    live hub at $base_url and $module installed
$(printf '%s\n' "$output" | tail -15 | sed 's/^/      /')"
        else
            ran_ok=$((ran_ok + 1))
            printf '  ✓ %s\n' "$entry"
        fi
    done 8< "$work_dir/batteries.list"

    teardown_module
done 9< "$work_dir/modules.list"

# The runner's own guard against the failure it exists to expose: a loop that ends early reports
# «N passed» and exit 0 exactly like a complete run. Measured, not hypothetical — see `db_exec`.
if [ "$seen_modules" -ne "$expected_modules" ]; then
    env_failures="$env_failures
  - the run ended after $seen_modules of $expected_modules modules. Whatever stopped it, the
    batteries of the rest were NOT run and this is not a pass."
fi

# ── The verdict ─────────────────────────────────────────────────────────────────────────────
if [ -n "$not_run" ]; then
    {
        printf 'run-module-hub-batteries: NOT RUN, by declared exemption:\n'
        printf '%s\n' "$not_run"
    } >&2
fi

# The environment verdict wins, same as in the pairing guard: with a hub that never came up there
# is nothing to conclude about the modules.
if [ -n "$env_failures" ]; then
    {
        printf 'run-module-hub-batteries: the RUNNER could not run (%s battery/ies did pass first).\n' "$ran_ok"
        printf '%s\n\n' "$env_failures"
        printf 'This is an environment failure, not a verdict on the modules.\n'
    } >&2
    exit 2
fi

if [ -n "$failures" ]; then
    {
        printf 'run-module-hub-batteries: %s battery/ies passed, and:\n' "$ran_ok"
        printf '%s\n\n' "$failures"
        printf 'A battery here asserts MODULE behaviour that the hub used to assert itself and no\n'
        printf 'longer does (hub#1264). A red is the module and the kernel disagreeing about the\n'
        printf 'contract between them: fix it in the module repo, or in the kernel if the kernel\n'
        printf 'moved. Reproduce it locally with:\n'
        printf '  cargo build -p erplora-server\n'
        printf '  scripts/ci/run-module-hub-batteries.sh --catalogue <dir> \\\n'
        printf '      --database-url postgres://postgres:test@localhost:5433/hub_test \\\n'
        printf '      --pg-container erplora-test-pg-5433\n'
    } >&2
    exit 1
fi

printf 'run-module-hub-batteries: %s battery/ies ran and passed, one hub per module.\n' "$ran_ok" >&2
exit 0
