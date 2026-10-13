#!/usr/bin/env bash
# PgBouncer sidecar of the hub and worker tasks (PLAN-DB §5; aws-next/README.md, «Imagen»): the
# hub_<hex> aliases reach Aurora through it, in transaction mode, on loopback only. Renders the
# config from the task environment under /tmp, the only writable path of the image, and replaces
# itself with pgbouncer, so the container's signals reach it.
#
#   PGBOUNCER_SERVER_HOST           Aurora writer (required)
#   PGBOUNCER_AUTH_USER/_PASSWORD   hub_app, the only role in the auth file (required, secrets)
#   PGBOUNCER_MAX_USER_CONNECTIONS  server connections per task: 40 web, 20 worker (required)
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

for name in PGBOUNCER_MAX_USER_CONNECTIONS PGBOUNCER_SERVER_PORT PGBOUNCER_LISTEN_PORT; do
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

# Constants of PLAN-DB §5. auth_file lives under /tmp (PLAN-DB says /run/pgbouncer, which the
# non-root user of the image cannot write).
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
max_client_conn=300
default_pool_size=3
max_db_connections=3
max_user_connections=$PGBOUNCER_MAX_USER_CONNECTIONS
server_idle_timeout=15
autodb_idle_timeout=300
query_wait_timeout=10
server_tls_sslmode=verify-full
server_tls_ca_file=$ca_file
max_prepared_statements=0
INI

exec pgbouncer "$config"
