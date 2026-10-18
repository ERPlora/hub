#!/usr/bin/env bash
# PgBouncer sidecar of the hub and worker tasks (PLAN-DB §5; aws-next/README.md, «Imagen»): the
# hub_<hex> aliases reach Aurora through it, in transaction mode, on loopback only. Renders the
# config from the task environment under /tmp, the only writable path of the image, and replaces
# itself with pgbouncer, so the container's signals reach it.
#
#   PGBOUNCER_SERVER_HOST           Aurora writer (required)
#   PGBOUNCER_AUTH_USER/_PASSWORD   hub_app, the only role in the auth file (required, secrets)
#   PGBOUNCER_MAX_USER_CONNECTIONS  server connections per task, all hub databases together
#                                   (required; the task definition's budget, PLAN-DB «Conexiones»)
#   PGBOUNCER_MAX_DB_CONNECTIONS    3: server connections per hub database, also its pool size
#   PGBOUNCER_SERVER_IDLE_TIMEOUT   10: seconds an unused server connection stays open
#   PGBOUNCER_MAX_CLIENT_CONN       300: client connections from the app
#   PGBOUNCER_SERVER_PORT           5432
#   PGBOUNCER_LISTEN_PORT           6432
#   PGBOUNCER_SERVER_TLS_CA_FILE    /etc/ssl/certs/rds-global-bundle.pem (verify-full)
#   PGBOUNCER_CONFIG_DIR            /tmp/pgbouncer (tests only)
set -euo pipefail

fail() {
  echo "pgbouncer-entrypoint: $*" >&2
  exit 1
}

# `bash -x` must not print the credentials: tracing pauses while they are checked and written.
case $- in *x*) trace=1 ;; *) trace=0 ;; esac
{ set +x; } 2>/dev/null

for name in PGBOUNCER_SERVER_HOST PGBOUNCER_AUTH_USER PGBOUNCER_AUTH_PASSWORD PGBOUNCER_MAX_USER_CONNECTIONS; do
  [[ -n "${!name:-}" ]] || fail "$name is required"
done

server_port="${PGBOUNCER_SERVER_PORT:-5432}"
listen_port="${PGBOUNCER_LISTEN_PORT:-6432}"
ca_file="${PGBOUNCER_SERVER_TLS_CA_FILE:-/etc/ssl/certs/rds-global-bundle.pem}"
config_dir="${PGBOUNCER_CONFIG_DIR:-/tmp/pgbouncer}"
max_db_connections="${PGBOUNCER_MAX_DB_CONNECTIONS:-3}"
server_idle_timeout="${PGBOUNCER_SERVER_IDLE_TIMEOUT:-10}"
max_client_conn="${PGBOUNCER_MAX_CLIENT_CONN:-300}"

# Positive integers only: to pgbouncer a 0 lifts the cap or never closes an idle connection.
for name in PGBOUNCER_MAX_USER_CONNECTIONS PGBOUNCER_SERVER_PORT PGBOUNCER_LISTEN_PORT \
  PGBOUNCER_MAX_DB_CONNECTIONS PGBOUNCER_SERVER_IDLE_TIMEOUT PGBOUNCER_MAX_CLIENT_CONN; do
  value="${!name:-1}"
  [[ "$value" =~ ^[1-9][0-9]*$ ]] || fail "$name must be a positive integer"
done

# One value per line in both files: a line break would inject settings or users.
for name in PGBOUNCER_SERVER_HOST PGBOUNCER_AUTH_USER PGBOUNCER_AUTH_PASSWORD PGBOUNCER_SERVER_TLS_CA_FILE; do
  [[ "${!name:-}" != *[$'\n\r']* ]] || fail "$name must not contain a line break"
done

umask 077
mkdir -p "$config_dir"

# auth_file format: "user" "password", a double quote inside doubled.
quote() { printf '"%s"' "${1//\"/\"\"}"; }
userlist="$config_dir/userlist.txt"
printf '%s %s\n' "$(quote "$PGBOUNCER_AUTH_USER")" "$(quote "$PGBOUNCER_AUTH_PASSWORD")" > "$userlist"
chmod 600 "$userlist"

if [[ $trace -eq 1 ]]; then set -x; fi

# PLAN-DB «Conexiones» (round 2026-10-18). One pool per hub database, all as hub_app: a hub
# without activity costs no server connection (min_pool_size and reserve_pool_size 0, closed after
# server_idle_timeout), and at max_user_connections pgbouncer evicts another hub's oldest idle
# connection before it makes a client wait, so the task never holds more than its budget.
# default_pool_size equals max_db_connections: with a single user they are the same cap. auth_file
# lives under /tmp (PLAN-DB says /run/pgbouncer, which the non-root user of the image cannot
# write). log_stats keeps its default: the line it writes every minute carries the average wait for
# a server connection, the only sign of a saturated pool without a metrics exporter.
config="$config_dir/pgbouncer.ini"
cat > "$config" <<INI
[databases]
* = host=$PGBOUNCER_SERVER_HOST port=$server_port

[pgbouncer]
listen_addr=127.0.0.1
listen_port=$listen_port
unix_socket_dir=
auth_type=scram-sha-256
auth_file=$userlist
pool_mode=transaction
max_client_conn=$max_client_conn
default_pool_size=$max_db_connections
min_pool_size=0
reserve_pool_size=0
max_db_connections=$max_db_connections
max_user_connections=$PGBOUNCER_MAX_USER_CONNECTIONS
server_idle_timeout=$server_idle_timeout
autodb_idle_timeout=300
query_wait_timeout=10
server_tls_sslmode=verify-full
server_tls_ca_file=$ca_file
max_prepared_statements=0
INI

exec pgbouncer "$config"
