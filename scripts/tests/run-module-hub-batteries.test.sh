#!/usr/bin/env bash
# Contract tests for scripts/ci/run-module-hub-batteries.sh — the RUNNER that finally executes the
# module `*.hub.test.py|sh` batteries against a live kernel.
#
# Regression test for ERPlora/hub#1381. What it protects, and why each case is here:
#
#   · hub#1264 moves the e2e that assert MODULE behaviour out of the hub and into each module's
#     own battery. `scripts/ci/module-hub-batteries.sh` (hub#1381, first half) proves the battery
#     EXISTS where the slice promised. It cannot prove it PASSES, and until this runner landed
#     nothing anywhere ran one: `services/tests/package_redeem.hub.test.py` inherited 391 lines of
#     coverage on 2026-08-30 and was executed by nobody for four days, both CIs green.
#
#   · ONE HUB PER MODULE, and that is not a preference — it is measured. Run against a single
#     shared hub, `cash_register/tests/session.hub.test.py` completes real sales whose auto-F2
#     invoices burn TICKET numbers through the outbox, and `invoice/tests/from_sale.hub.test.py`
#     then reads N+2 where it asserts N+1. Both batteries are correct; the sharing is the bug.
#     Measured on 2026-09-03 against `origin/develop@34fa7c3c`: 22/26 green shared, 26/26 green
#     with a hub each (bar the exemption below). A runner that shares the hub reports failures
#     that belong to nobody, which is worse than not running at all.
#
#   · A battery that EXITS 0 WITHOUT TESTING is the failure mode this whole file exists against.
#     `SKIPPED` at the head of a line is a self-skip and it is RED here, wider than the toolkit's
#     own `looksSkipped` (`/^SKIPPED:/`), which misses `SKIPPED (SQL half):` — ten `customers`
#     batteries printed exactly that and read as green (module-toolkit#137).
#
#   · A module in the worklist that did NOT install is RED, never a skip. The dev boot scan is
#     tolerant on purpose (it logs ✗ and carries on) and `/readyz` counts only what reached the
#     database, so a module that never installed is invisible from both ends. That is how
#     `verifactu` came up missing with the hub reporting `missing: []`.
#
#   · And the exemption for that module SELF-EXPIRES: if an exempted module does install, this run
#     goes RED so the line gets deleted. An exemption nobody is forced to revisit is the quiet way
#     the hole comes back.
#
# Everything here is hermetic: fake server, fake batteries, stub database admin. No docker, no
# Postgres, no kernel — the cases that matter are the ones where something did NOT come up.

set -uo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
script="$script_dir/../ci/run-module-hub-batteries.sh"
tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/erplora-run-module-hub-batteries-test.XXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT HUP INT TERM

passed=0
out=""
err=""
rc=0

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    printf '  exit was: %s\n' "$rc" >&2
    [ -n "$out" ] && printf '  stdout was:\n%s\n' "$(printf '%s\n' "$out" | sed 's/^/    /')" >&2
    [ -n "$err" ] && printf '  stderr was:\n%s\n' "$(printf '%s\n' "$err" | sed 's/^/    /')" >&2
    exit 1
}

ok() { passed=$((passed + 1)); }

if [ ! -f "$script" ]; then
    fail "no such script: $script"
fi

# ── Fixtures ────────────────────────────────────────────────────────────────────────────
# A scratch catalogue shaped like the one `materialize-published-modules.sh` leaves behind, plus
# a FAKE server: a python one-liner that answers `/readyz` and `/api/modules` with whatever the
# per-run control file says is installed. That is the whole surface the runner talks to.

make_module() { # $1=catalogue, $2=id, rest=battery relative paths
    local catalogue="$1" id="$2" rel
    shift 2
    mkdir -p "$catalogue/$id"
    printf '{"id": "%s", "version": "1.0.0"}\n' "$id" > "$catalogue/$id/module.json"
    for rel in "$@"; do
        mkdir -p "$catalogue/$id/$(dirname "$rel")"
        {
            printf '#!/usr/bin/env python3\n'
            printf 'import os, sys\n'
            printf 'print("battery %s of %s at", os.environ.get("ERPLORA_HUB_BASE_URL"))\n' "$rel" "$id"
            printf 'open(os.environ["BATTERY_LOG"], "a").write("%s/%s %%s\\n" %% os.environ.get("ERPLORA_HUB_BASE_URL"))\n' "$id" "$rel"
            printf 'open(os.environ["PSQL_LOG"], "a").write("%s/%s\\t%%s\\n" %% os.environ.get("ERPLORA_HUB_PSQL", "<unset>"))\n' "$id" "$rel"
            printf 'sys.exit(int(os.environ.get("BATTERY_EXIT_%s", "0")))\n' "$(printf '%s' "$id" | tr '[:lower:]-' '[:upper:]_')"
        } > "$catalogue/$id/$rel"
    done
}

# The fake kernel. `INSTALLED` (comma separated) is what `GET /api/modules` reports; the runner
# must believe the runtime and nothing else.
make_fake_server() { # $1=path
    cat > "$1" <<'FAKE'
#!/usr/bin/env bash
# Fake erplora-server: records its boot and serves the two endpoints the runner reads.
printf '%s %s %s\n' "${HUB_DATABASE_URL:-}" "${HUB_BIND:-}" "${HUB_MODULES_DIR:-}" >> "$BOOT_LOG"
port=${HUB_BIND##*:}
exec python3 - "$port" <<'PY'
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

installed = [m for m in os.environ.get("INSTALLED", "").split(",") if m]

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/readyz":
            body = {"status": "UP"}
        elif self.path == "/api/modules":
            body = {"data": [{"id": m} for m in installed]}
        elif self.path == "/api/hub/context":
            body = {"hub_id": "00000000-0000-0000-0000-000000000001"}
        else:
            self.send_response(404); self.end_headers(); return
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def log_message(self, *a): pass

HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
PY
FAKE
    chmod +x "$1"
}

catalogue="$tmp_dir/catalogue"
mkdir -p "$catalogue"
make_module "$catalogue" alpha tests/one.hub.test.py tests/two.hub.test.py
make_module "$catalogue" beta tests/only.hub.test.py

manifest="$tmp_dir/manifest.txt"
cat > "$manifest" <<'EOF'
# scratch list
alpha/tests/one.hub.test.py
alpha/tests/two.hub.test.py
beta/tests/only.hub.test.py
EOF

server="$tmp_dir/fake-server"
make_fake_server "$server"

# The database admin stub: records the SQL it is handed instead of talking to Postgres.
db_admin="$tmp_dir/fake-psql"
cat > "$db_admin" <<'PSQL'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$DB_LOG"
PSQL
chmod +x "$db_admin"

# `timeout` is not on every macOS; where it is missing the watchdog is empty and the suite still
# runs — it just loses the hang protection.
watchdog=""
if command -v timeout > /dev/null 2>&1; then
    watchdog="timeout 120"
elif command -v gtimeout > /dev/null 2>&1; then
    watchdog="gtimeout 120"
fi

run_runner() { # rest=extra args; env: INSTALLED, BATTERY_EXIT_*
    : > "$tmp_dir/boot.log"
    : > "$tmp_dir/db.log"
    : > "$tmp_dir/battery.log"
    : > "$tmp_dir/psql.log"
    local stdout_file="$tmp_dir/stdout" stderr_file="$tmp_dir/stderr"
    # Under a watchdog when one is available, and with stdin CLOSED. Case 9 hands the runner a
    # database admin that reads stdin the way `docker exec -i` does: a runner that lets it reach
    # the worklist does not fail here, it HANGS — and a suite that hangs is a suite nobody runs.
    BOOT_LOG="$tmp_dir/boot.log" \
    DB_LOG="$tmp_dir/db.log" \
    BATTERY_LOG="$tmp_dir/battery.log" \
    PSQL_LOG="$tmp_dir/psql.log" \
        $watchdog "${RUNNER_BASH:-bash}" "$script" \
            --catalogue "$catalogue" \
            --manifest "$manifest" \
            --server "$server" \
            --database-url 'postgres://postgres:test@127.0.0.1:5433/hub_test' \
            --db-admin-cmd "$db_admin" \
            --ready-timeout 20 \
            "$@" > "$stdout_file" 2> "$stderr_file"
    rc=$?
    out=$(cat "$stdout_file")
    err=$(cat "$stderr_file")
}

# ── 1 · Happy path: every battery runs, one hub per module ──────────────────────────────
INSTALLED=alpha,beta run_runner
[ "$rc" -eq 0 ] || fail "1: a catalogue whose batteries all pass must exit 0"
ok

boots=$(grep -c . "$tmp_dir/boot.log")
[ "$boots" -eq 2 ] || fail "1: expected ONE hub per module (2 boots), got $boots"
ok

ran=$(sort "$tmp_dir/battery.log" | cut -d' ' -f1)
expected=$(printf 'alpha/tests/one.hub.test.py\nalpha/tests/two.hub.test.py\nbeta/tests/only.hub.test.py\n')
[ "$ran" = "$expected" ] || fail "1: not every battery ran. got:\n$ran"
ok

# The two modules must not share a database, and each database is dropped afterwards.
dbs=$(awk '{print $1}' "$tmp_dir/boot.log" | sort -u | wc -l | tr -d ' ')
[ "$dbs" -eq 2 ] || fail "1: the two modules must get a database each, got $dbs distinct DSN(s)"
ok

grep -q 'CREATE DATABASE' "$tmp_dir/db.log" || fail "1: no CREATE DATABASE was ever issued"
grep -q 'DROP DATABASE' "$tmp_dir/db.log" || fail "1: the scratch database is never dropped"
ok

# And the batteries of the two modules never saw the same base url — the isolation the whole
# design rests on.
urls=$(cut -d' ' -f2 "$tmp_dir/battery.log" | sort -u | wc -l | tr -d ' ')
[ "$urls" -eq 2 ] || fail "1: expected 2 distinct hub urls (one per module), got $urls"
ok

# ── 2 · A battery that FAILS is a red verdict, and it is named ───────────────────────────
INSTALLED=alpha,beta BATTERY_EXIT_BETA=1 run_runner
[ "$rc" -eq 1 ] || fail "2: a failing battery must exit 1 (verdict), got $rc"
ok
grep -q 'beta/tests/only.hub.test.py' <<<"$out$err" \
    || fail "2: the failing battery is not named in the report"
ok

# ── 3 · Exit 0 with a SKIPPED line is NOT a pass ─────────────────────────────────────────
skipper="$catalogue/alpha/tests/two.hub.test.py"
cp "$skipper" "$tmp_dir/two.bak"
cat > "$skipper" <<'PY'
#!/usr/bin/env python3
import os
open(os.environ["BATTERY_LOG"], "a").write("alpha/tests/two.hub.test.py %s\n" % os.environ.get("ERPLORA_HUB_BASE_URL"))
print("SKIPPED (SQL half): no database at the other end")
PY
INSTALLED=alpha,beta run_runner
[ "$rc" -eq 1 ] || fail "3: a battery that skips itself and exits 0 must be RED, got $rc"
ok
grep -qi 'skip' <<<"$out$err" \
    || fail "3: the report does not say the battery skipped itself"
ok
cp "$tmp_dir/two.bak" "$skipper"

# ── 4 · A worklist module that did NOT install is red, never a silent skip ───────────────
INSTALLED=alpha run_runner
[ "$rc" -eq 1 ] || fail "4: a module missing from the runtime must exit 1, got $rc"
ok
grep -q 'beta' <<<"$out$err" \
    || fail "4: the uninstalled module is not named"
ok
grep -q '^beta/' "$tmp_dir/battery.log" \
    && fail "4: a battery ran against a hub that never installed its module"
ok

# ── 5 · An exemption self-expires: an exempt module that DOES install is red ─────────────
INSTALLED=alpha,beta run_runner --exempt 'beta=hub#0 fake reason'
[ "$rc" -eq 1 ] || fail "5: an exemption whose module installs must go RED so it gets deleted"
ok
grep -qi 'exempt' <<<"$out$err" \
    || fail "5: the report does not explain the stale exemption"
ok

# ── 6 · An exemption that still holds: NOT RUN, named with its issue, job stays green ────
INSTALLED=alpha run_runner --exempt 'beta=hub#0 fake reason'
[ "$rc" -eq 0 ] || fail "6: a live exemption must not fail the job, got $rc"
ok
grep -q 'hub#0' <<<"$out$err" \
    || fail "6: the exemption is not reported with its issue"
ok
grep -q '^beta/' "$tmp_dir/battery.log" \
    && fail "6: an exempt module must not have its batteries run"
ok

# ── 7 · No environment, no verdict: exit 2, distinct from a red battery ──────────────────
INSTALLED=alpha,beta run_runner --catalogue "$tmp_dir/does-not-exist"
[ "$rc" -eq 2 ] || fail "7: a missing catalogue is an ENVIRONMENT failure (2), got $rc"
ok

INSTALLED=alpha,beta run_runner --server "$tmp_dir/no-such-binary"
[ "$rc" -eq 2 ] || fail "7: a missing server binary is an ENVIRONMENT failure (2), got $rc"
ok

# ── 8 · Teardown happens on the FAILING path too ─────────────────────────────────────────
INSTALLED=alpha,beta BATTERY_EXIT_ALPHA=1 run_runner
[ "$rc" -eq 1 ] || fail "8: expected the failing verdict"
drops=$(grep -c 'DROP DATABASE' "$tmp_dir/db.log")
[ "$drops" -eq 2 ] || fail "8: every scratch database must be dropped even when a battery fails (got $drops)"
ok
# Nothing of ours may still be listening.
for port in $(grep -o '127.0.0.1:[0-9]*' "$tmp_dir/boot.log" | cut -d: -f2 | sort -u); do
    if curl -s -m 2 "http://127.0.0.1:$port/readyz" > /dev/null 2>&1; then
        fail "8: a hub is still listening on $port after the run"
    fi
done
ok

# ── 9 · A database admin that READS STDIN must not truncate the run (measured) ───────────
# The real one is `docker exec -i <pg> psql`, and `-i` attaches stdin. Called from inside a
# `while read` loop it swallows the rest of the worklist: the first version of the runner did
# `appointments` and then reported «2 batteries passed» and exit 0, having silently skipped ten
# modules. A green that skipped most of the work is the exact failure hub#1381 is about, one
# level in. This stub reproduces it: it consumes stdin the way `docker exec -i` does.
cat > "$db_admin" <<'PSQL'
#!/usr/bin/env bash
cat > /dev/null
printf '%s\n' "$*" >> "$DB_LOG"
PSQL
chmod +x "$db_admin"

INSTALLED=alpha,beta run_runner
[ "$rc" -eq 0 ] || fail "9: a stdin-reading db admin must not break the run, got $rc"
ok
boots=$(grep -c . "$tmp_dir/boot.log")
[ "$boots" -eq 2 ] || fail "9: the run was truncated — $boots of 2 modules booted"
ok
ran=$(grep -c . "$tmp_dir/battery.log")
[ "$ran" -eq 3 ] || fail "9: the run was truncated — $ran of 3 batteries ran"
ok


# ── 10 · An EMPTY exemption table is a normal state, not shell noise ─────────────────────
# The table is data, and hub#1483 emptied it: `verifactu` was the only entry and it installs on
# its own since hub#1477, so the self-expiry fired and the run went red demanding the line go
# (hub#1487, this runner's own alert on `develop`). An empty bash array expanded as `"${arr[@]}"`
# under `set -u` is an
# UNBOUND VARIABLE on bash 3.2 — still `/bin/bash` on macOS — so `exemption_for` would print
# `exemptions[@]: unbound variable` once per module and land on «not exempt» by way of the failed
# subshell rather than by its own logic. STDERR is where this runner writes its verdict; twelve
# spurious error lines around it is how a real red becomes unreadable.
#
# Run under the strictest bash on the box: on macOS `/bin/bash` is 3.2 and this case is sharp,
# on CI it is bash 5 and the case still asserts the happy path is clean.
strict_bash="bash"
[ -x /bin/bash ] && strict_bash="/bin/bash"
INSTALLED=alpha,beta RUNNER_BASH="$strict_bash" run_runner
[ "$rc" -eq 0 ] || fail "10: the happy path with no exemptions must be green under $strict_bash, got $rc"
ok
grep -q 'unbound variable' <<<"$err" \
    && fail "10: the runner leaked a shell error into its verdict channel under $strict_bash:
$(grep -n -m3 'unbound variable' <<<"$err")"
ok
ran=$(grep -c . "$tmp_dir/battery.log")
[ "$ran" -eq 3 ] || fail "10: $ran of 3 batteries ran under $strict_bash"
ok

# ── 11 · Every battery is handed the SQL session of ITS hub's database (module-toolkit#405) ─
# A battery that has to hold a transaction open in the hub's database (the voucher race of
# `services/tests/grant_race.hub.test.py`) used to find it with `docker ps` — the container that
# publishes the hub's port. That exists under `erplora test --against-hub` and NOT here, where the
# hub is a native server on a scratch database of the job's container: `found []`, and a hub
# release went red for a module with no fault (services#130). The contract is ONE variable,
# `ERPLORA_HUB_PSQL`, set by both harnesses with the same shape: the admin psql command plus
# `-d <the database THIS module's hub was booted on>`.
INSTALLED=alpha,beta run_runner
[ "$rc" -eq 0 ] || fail "11: the happy path must stay green, got $rc"
ok
while IFS=$'\t' read -r battery psql; do
    module=${battery%%/*}
    booted_db=$(awk -v m="_${module}_" '{ n = split($1, p, "/"); if (index(p[n], m)) print p[n] }' "$tmp_dir/boot.log")
    [ -n "$booted_db" ] || fail "11: no hub of $module booted on a database of its own"
    [ "$psql" = "$db_admin -d $booted_db" ] \
        || fail "11: $battery got ERPLORA_HUB_PSQL='$psql', expected '$db_admin -d $booted_db' (the database its hub writes to)"
done < "$tmp_dir/psql.log"
[ "$(grep -c . "$tmp_dir/psql.log")" -eq 3 ] || fail "11: not every battery reported its ERPLORA_HUB_PSQL"
ok

# 11b · With `--pg-container` (what the hub's CI passes) the session is word for word the shape the
# toolkit's `hubPsqlCommand` builds under `--against-hub`:
# `docker exec -i <container> psql -U <user> -v ON_ERROR_STOP=1 -d <database>`. A fake `docker`
# on PATH records the admin calls instead of reaching a daemon.
fake_bin="$tmp_dir/bin"
mkdir -p "$fake_bin"
cat > "$fake_bin/docker" <<'DOCKER'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$DB_LOG"
DOCKER
chmod +x "$fake_bin/docker"
PATH="$fake_bin:$PATH" INSTALLED=alpha,beta run_runner --db-admin-cmd '' --pg-container ci-pg --pg-user erplora
[ "$rc" -eq 0 ] || fail "11b: the happy path with --pg-container must be green, got $rc"
ok
beta_db=$(awk '{ n = split($1, p, "/"); if (index(p[n], "_beta_")) print p[n] }' "$tmp_dir/boot.log")
got=$(awk -F'\t' '$1 == "beta/tests/only.hub.test.py" { print $2 }' "$tmp_dir/psql.log")
[ "$got" = "docker exec -i ci-pg psql -U erplora -v ON_ERROR_STOP=1 -d $beta_db" ] \
    || fail "11b: ERPLORA_HUB_PSQL is '$got', not the toolkit's shape for ci-pg/$beta_db"
ok

printf 'run-module-hub-batteries.test.sh: %s checks passed\n' "$passed"
