#!/usr/bin/env bash
# Tests for pgbouncer-healthcheck.sh against a fake listener (python3) that records the bytes it
# receives and answers as told.
#   bash docker/pgbouncer-healthcheck.test.sh
# Conditions are single-quoted on purpose: check() evaluates them later (SC2016, SC2034).
# shellcheck disable=SC2016,SC2034
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
script="$here/pgbouncer-healthcheck.sh"
failures=0

# The protocol's SSLRequest: length 8, code 80877103. Nothing else may reach PgBouncer: a startup
# packet carries a user, and an unknown one is logged as «no such user» on every probe.
ssl_request=0000000804d2162f

setup() {
  work="$(mktemp -d)"
  cat > "$work/listener.py" <<'PY'
import os
import socket
import sys

mode, port_file, received_file = sys.argv[1:4]
server = socket.socket()
server.bind(("127.0.0.1", 0))
server.listen(1)
with open(port_file + ".tmp", "w") as f:
    f.write(str(server.getsockname()[1]))
os.rename(port_file + ".tmp", port_file)
server.settimeout(10)
conn, _ = server.accept()
conn.settimeout(10)
received = b""
if mode != "hang-up":
    while len(received) < 8:
        chunk = conn.recv(8 - len(received))
        if not chunk:
            break
        received += chunk
    if mode != "mute":
        conn.sendall(mode.encode())
    # Whatever else the client sends, until it hangs up.
    while chunk := conn.recv(4096):
        received += chunk
conn.close()
with open(received_file, "w") as f:
    f.write(received.hex())
PY
}

teardown() {
  if [[ -n ${listener:-} ]]; then kill "$listener" 2> /dev/null || true; fi
  listener=""
  rm -rf "$work"
}

# start_listener <answer | mute | hang-up>: a one-connection listener on a free loopback port.
start_listener() {
  python3 -I "$work/listener.py" "$1" "$work/port" "$work/received" 2> "$work/listener.log" &
  listener=$!
  for _ in $(seq 1 50); do
    [[ -s $work/port ]] && break
    sleep 0.1
  done
  port="$(cat "$work/port")"
}

# run_probe [VAR=value ...]: the probe with the sidecar's environment, timed in whole seconds.
run_probe() {
  local start=$SECONDS
  status=0
  env "$@" bash "$script" > "$work/out.log" 2>&1 || status=$?
  elapsed=$((SECONDS - start))
}

# received: the listener's record, once it has seen the client hang up.
received() {
  wait "$listener" 2> /dev/null || true
  listener=""
  cat "$work/received" 2> /dev/null || true
}

check() {
  local name="$1" condition="$2"
  if (eval "$condition"); then
    echo "ok   - $name"
  else
    echo "FAIL - $name"
    sed 's/^/       | /' "$work/out.log"
    failures=$((failures + 1))
  fi
}

setup
start_listener N
run_probe PGBOUNCER_LISTEN_PORT="$port"
check "healthy when PgBouncer answers the SSLRequest with N (no TLS)" '[[ $status -eq 0 ]]'
check "sends only the SSLRequest: no startup packet, so no user to log" '[[ $(received) == "$ssl_request" ]]'
teardown

setup
start_listener S
run_probe PGBOUNCER_LISTEN_PORT="$port"
check "healthy when it answers S (TLS on)" '[[ $status -eq 0 ]]'
teardown

setup
start_listener E
run_probe PGBOUNCER_LISTEN_PORT="$port"
check "unhealthy on any other answer" '[[ $status -ne 0 ]]'
teardown

setup
start_listener mute
run_probe PGBOUNCER_LISTEN_PORT="$port"
check "unhealthy when the listener accepts but never answers (a frozen pgbouncer)" '[[ $status -ne 0 ]]'
check "gives up within the 3 s timeout of the ECS healthcheck" '[[ $elapsed -le 2 ]]'
teardown

setup
start_listener hang-up
run_probe PGBOUNCER_LISTEN_PORT="$port"
check "unhealthy when the listener hangs up without answering" '[[ $status -ne 0 ]]'
teardown

setup
start_listener N
port_closed="$port"
run_probe PGBOUNCER_LISTEN_PORT="$port"
received > /dev/null
run_probe PGBOUNCER_LISTEN_PORT="$port_closed"
check "unhealthy when nothing listens, naming the address" \
  '[[ $status -ne 0 ]] && grep -q "127.0.0.1:$port_closed" "$work/out.log"'
teardown

for value in forty "6432/x" 0; do
  setup
  run_probe PGBOUNCER_LISTEN_PORT="$value"
  check "PGBOUNCER_LISTEN_PORT=\"$value\": unhealthy, naming the variable" \
    '[[ $status -ne 0 ]] && grep -q PGBOUNCER_LISTEN_PORT "$work/out.log"'
  teardown
done

if [[ $failures -gt 0 ]]; then
  echo "$failures failure(s)"
  exit 1
fi
echo "all passed"
