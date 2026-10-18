#!/usr/bin/env bash
# Healthcheck of the PgBouncer sidecar (the healthCheck of modules/ecs-service in ERPlora/aws).
# Sends the protocol's SSLRequest to the loopback listener, waits for its one-byte answer (N, or S
# with TLS) and hangs up before any startup packet. PgBouncer does not log a client that leaves
# before logging in («could be monitoring probe»), so the probe leaves no trace; pg_isready, the
# previous check, logged in as the image's user `app`, which is not in the auth file, and wrote
# «login attempt … no such user: app» every 5 s. A frozen pgbouncer, whose kernel still accepts the
# connection, never answers and fails the check.
#
#   PGBOUNCER_LISTEN_PORT   6432 (the same variable pgbouncer-entrypoint listens on)
set -euo pipefail

port="${PGBOUNCER_LISTEN_PORT:-6432}"
address="127.0.0.1:$port"
# Within the 3 s timeout of the ECS healthcheck.
answer_timeout=2

fail() {
  echo "pgbouncer-healthcheck: $*" >&2
  exit 1
}

[[ "$port" =~ ^[1-9][0-9]*$ ]] || fail "PGBOUNCER_LISTEN_PORT must be a positive integer"

# bash's own connect error is replaced by one naming the address.
{ exec 3<> "/dev/tcp/127.0.0.1/$port"; } 2> /dev/null || fail "nothing listens on $address"

# SSLRequest: length 8, code 80877103 (0x04D2162F).
printf '\x00\x00\x00\x08\x04\xd2\x16\x2f' >&3 2> /dev/null || fail "$address closed the connection"
IFS= read -r -n 1 -t "$answer_timeout" answer <&3 || fail "no answer from $address"
[[ $answer == N || $answer == S ]] || fail "unexpected answer from $address"
