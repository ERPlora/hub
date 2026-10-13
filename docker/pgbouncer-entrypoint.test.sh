#!/usr/bin/env bash
# Tests for pgbouncer-entrypoint.sh with a fake pgbouncer that records its call and returns at once.
#   bash docker/pgbouncer-entrypoint.test.sh
# Conditions are single-quoted on purpose: check() evaluates them later (SC2016, SC2034); overrides
# are exported by their `VAR=value` text (SC2163).
# shellcheck disable=SC2016,SC2034,SC2163
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
script="$here/pgbouncer-entrypoint.sh"
failures=0

setup() {
  work="$(mktemp -d)"
  mkdir -p "$work/bin"
  cat > "$work/bin/pgbouncer" <<'FAKE'
#!/usr/bin/env bash
echo "$$ $*" >> "$CALLS_LOG"
FAKE
  chmod +x "$work/bin/pgbouncer"
  export CALLS_LOG="$work/calls.log"
  : > "$CALLS_LOG"
  ini="$work/pgbouncer/pgbouncer.ini"
  userlist="$work/pgbouncer/userlist.txt"
}

teardown() { rm -rf "$work"; }

# run_entrypoint [VAR=value | -VAR ...]: the sidecar's task environment, with overrides
# (`-VAR` unsets one). Records the PID it starts: when the script execs pgbouncer, the fake
# reports that same PID. TRACED=1 runs it under `bash -x`, as a debugging operator would.
run_entrypoint() {
  (
    export PATH="$work/bin:$PATH" PGBOUNCER_CONFIG_DIR="$work/pgbouncer" \
      PGBOUNCER_SERVER_HOST=writer.cluster.example PGBOUNCER_AUTH_USER=hub_app \
      PGBOUNCER_AUTH_PASSWORD=s3cret PGBOUNCER_MAX_USER_CONNECTIONS=40
    unset PGBOUNCER_SERVER_PORT PGBOUNCER_LISTEN_PORT PGBOUNCER_SERVER_TLS_CA_FILE
    for arg in "$@"; do
      case $arg in
        -*) unset "${arg#-}" ;;
        *) export "$arg" ;;
      esac
    done
    exec bash ${TRACED:+-x} "$script"
  ) > "$work/out.log" 2>&1 &
  pid=$!
  status=0
  wait "$pid" || status=$?
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

has_line() { grep -qxF -- "$1" "$ini"; }

for var in PGBOUNCER_SERVER_HOST PGBOUNCER_AUTH_USER PGBOUNCER_AUTH_PASSWORD PGBOUNCER_MAX_USER_CONNECTIONS; do
  setup
  run_entrypoint "-$var"
  check "missing $var: fails naming it, pgbouncer never runs" \
    '[[ $status -ne 0 ]] && grep -q "$var" "$work/out.log" && [[ ! -s $CALLS_LOG ]]'
  teardown

  setup
  run_entrypoint "$var="
  check "empty $var counts as missing" \
    '[[ $status -ne 0 ]] && grep -q "$var" "$work/out.log" && [[ ! -s $CALLS_LOG ]]'
  teardown
done

for var in PGBOUNCER_MAX_USER_CONNECTIONS PGBOUNCER_SERVER_PORT PGBOUNCER_LISTEN_PORT; do
  setup
  run_entrypoint "$var=forty"
  check "non-numeric $var: fails naming it" \
    '[[ $status -ne 0 ]] && grep -q "$var" "$work/out.log" && [[ ! -s $CALLS_LOG ]]'
  teardown
done

setup
run_entrypoint "PGBOUNCER_AUTH_PASSWORD=pass
[pgbouncer]"
check "a line break in a credential is refused (no injected config)" \
  '[[ $status -ne 0 ]] && grep -q PGBOUNCER_AUTH_PASSWORD "$work/out.log" && [[ ! -s $CALLS_LOG ]]'
teardown

setup
run_entrypoint
check "writes the PLAN-DB settings" '
  [[ $status -eq 0 ]] &&
  has_line "pool_mode=transaction" && has_line "auth_type=scram-sha-256" &&
  has_line "default_pool_size=3" && has_line "max_db_connections=3" &&
  has_line "max_client_conn=300" && has_line "server_idle_timeout=15" &&
  has_line "autodb_idle_timeout=300" && has_line "query_wait_timeout=10" &&
  has_line "server_tls_sslmode=verify-full" && has_line "max_prepared_statements=0"'
check "listens on loopback only, without a unix socket" \
  'has_line "listen_addr=127.0.0.1" && has_line "unix_socket_dir=" && [[ $(grep -c "^listen_addr=" "$ini") -eq 1 ]]'
check "max_user_connections comes from the task" 'has_line "max_user_connections=40"'
check "defaults: listens on 6432, the writer on 5432, the RDS bundle as CA" '
  has_line "listen_port=6432" &&
  has_line "* = host=writer.cluster.example port=5432" &&
  has_line "server_tls_ca_file=/etc/ssl/certs/rds-global-bundle.pem"'
check "the auth file sits next to the config, under the writable dir" \
  'has_line "auth_file=$work/pgbouncer/userlist.txt"'
check "every database goes to the writer, under [databases]" \
  '[[ $(sed -n "1p" "$ini") == "[databases]" ]] && grep -q "^\[pgbouncer\]$" "$ini"'
check "the userlist holds only the auth user, mode 600" '
  [[ $(cat "$userlist") == "\"hub_app\" \"s3cret\"" ]] &&
  [[ $(stat -c %a "$userlist" 2>/dev/null || stat -f %Lp "$userlist") == 600 ]]'
check "execs pgbouncer with the config (same PID, no wrapper left)" \
  '[[ $(cat "$CALLS_LOG") == "$pid $work/pgbouncer/pgbouncer.ini" ]]'
check "never prints the password" '! grep -q s3cret "$work/out.log"'
teardown

setup
run_entrypoint PGBOUNCER_SERVER_PORT=5433 PGBOUNCER_LISTEN_PORT=6433 \
  PGBOUNCER_SERVER_TLS_CA_FILE=/etc/ssl/certs/other.pem PGBOUNCER_MAX_USER_CONNECTIONS=20
check "explicit ports, CA file and connection cap win over the defaults" '
  [[ $status -eq 0 ]] && has_line "listen_port=6433" &&
  has_line "* = host=writer.cluster.example port=5433" &&
  has_line "server_tls_ca_file=/etc/ssl/certs/other.pem" && has_line "max_user_connections=20"'
teardown

setup
run_entrypoint 'PGBOUNCER_AUTH_USER=hub"app' 'PGBOUNCER_AUTH_PASSWORD=pa"ss""word'
check "double quotes in the userlist are doubled" \
  '[[ $status -eq 0 ]] && [[ $(cat "$userlist") == "\"hub\"\"app\" \"pa\"\"ss\"\"\"\"word\"" ]]'
teardown

setup
TRACED=1 run_entrypoint 'PGBOUNCER_AUTH_PASSWORD=Tr4ced"Secret'
check "under bash -x the password never reaches the output" '
  [[ -s $CALLS_LOG ]] && grep -q "^+" "$work/out.log" &&
  ! grep -q "Tr4ced" "$work/out.log"'
teardown

setup
TRACED=1 run_entrypoint 'PGBOUNCER_AUTH_PASSWORD=Tr4cedSecret' -PGBOUNCER_MAX_USER_CONNECTIONS
check "under bash -x a failed check does not print the password either" \
  '[[ ! -s $CALLS_LOG ]] && ! grep -q "Tr4ced" "$work/out.log"'
teardown

if [[ $failures -gt 0 ]]; then
  echo "$failures failure(s)"
  exit 1
fi
echo "all passed"
