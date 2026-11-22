#!/usr/bin/env python3
"""PgBouncer sidecar of the hub and worker tasks (ERPlora/aws README, «Imagen»): the hub_<hex> aliases reach Aurora
through it, in transaction mode, on loopback only. Renders the config from the task environment under /tmp, the only
writable path of the image, and replaces itself with pgbouncer, so the container's signals reach it. The image installs
it as the command `pgbouncer-entrypoint`. An empty setting counts as unset.

  PGBOUNCER_SERVER_HOST           Aurora writer (required)
  PGBOUNCER_AUTH_USER/_PASSWORD   hub_app, the only role in the auth file (required, secrets)
  PGBOUNCER_MAX_USER_CONNECTIONS  server connections per task, all hub databases together
                                  (required; the task definition's budget)
  PGBOUNCER_MAX_DB_CONNECTIONS    3: server connections per hub database, also its pool size
  PGBOUNCER_SERVER_IDLE_TIMEOUT   10: seconds an unused server connection stays open
  PGBOUNCER_MAX_CLIENT_CONN       300: client connections from the app
  PGBOUNCER_SERVER_PORT           5432
  PGBOUNCER_LISTEN_PORT           6432
  PGBOUNCER_SERVER_TLS_CA_FILE    /etc/ssl/certs/rds-global-bundle.pem (verify-full)
  PGBOUNCER_CONFIG_DIR            /tmp/pgbouncer (tests only)
"""

import os
import re
import signal
import sys

REQUIRED = ("PGBOUNCER_SERVER_HOST", "PGBOUNCER_AUTH_USER", "PGBOUNCER_AUTH_PASSWORD",
            "PGBOUNCER_MAX_USER_CONNECTIONS")
# Positive integers only: to pgbouncer a 0 lifts the cap or never closes an idle connection.
COUNTS = ("PGBOUNCER_MAX_USER_CONNECTIONS", "PGBOUNCER_SERVER_PORT", "PGBOUNCER_LISTEN_PORT",
          "PGBOUNCER_MAX_DB_CONNECTIONS", "PGBOUNCER_SERVER_IDLE_TIMEOUT", "PGBOUNCER_MAX_CLIENT_CONN")
# One value per line in both files: a line break would inject settings or users.
WRITTEN = ("PGBOUNCER_SERVER_HOST", "PGBOUNCER_AUTH_USER", "PGBOUNCER_AUTH_PASSWORD", "PGBOUNCER_SERVER_TLS_CA_FILE")
DEFAULTS = {
    "PGBOUNCER_SERVER_PORT": "5432",
    "PGBOUNCER_LISTEN_PORT": "6432",
    "PGBOUNCER_SERVER_TLS_CA_FILE": "/etc/ssl/certs/rds-global-bundle.pem",
    "PGBOUNCER_CONFIG_DIR": "/tmp/pgbouncer",
    "PGBOUNCER_MAX_DB_CONNECTIONS": "3",
    "PGBOUNCER_SERVER_IDLE_TIMEOUT": "10",
    "PGBOUNCER_MAX_CLIENT_CONN": "300",
}
POSITIVE = re.compile("[1-9][0-9]*")

# One pool per hub database, all as hub_app: a hub without activity costs no server connection (min_pool_size and
# reserve_pool_size 0, closed after server_idle_timeout), and at max_user_connections pgbouncer evicts another hub's
# oldest idle connection before it makes a client wait, so the task never holds more than its budget.
# default_pool_size equals max_db_connections: with a single user they are the same cap. auth_file lives under /tmp, not
# /run/pgbouncer, which the non-root user of the image cannot write. log_stats keeps its default: the line it writes
# every minute carries the average wait for a server connection, the only sign of a saturated pool without a metrics
# exporter.
#
# Writer change. After a Blue/Green switchover or a failover the writer's name resolves to another server, and AWS asks
# that no DNS cache outlives five seconds: past that, writes keep going to the old writer, which is read-only by then.
# pgbouncer ignores the record's own TTL and keeps an answer for dns_max_ttl and a failed lookup for dns_nxdomain_ttl,
# 15 s each by default. After a failed server login it refuses every client without dialling again for
# server_login_retry, 15 s by default too. Fixed here, not task settings: they follow from how Aurora changes writer,
# not from the size of a task.
CONFIG = """[databases]
* = host={host} port={server_port}

[pgbouncer]
listen_addr=127.0.0.1
listen_port={listen_port}
unix_socket_dir=
auth_type=scram-sha-256
auth_file={userlist}
pool_mode=transaction
max_client_conn={max_client_conn}
default_pool_size={max_db_connections}
min_pool_size=0
reserve_pool_size=0
max_db_connections={max_db_connections}
max_user_connections={max_user_connections}
server_idle_timeout={server_idle_timeout}
dns_max_ttl=5
dns_nxdomain_ttl=5
server_login_retry=2
autodb_idle_timeout=300
query_wait_timeout=10
server_tls_sslmode=verify-full
server_tls_ca_file={ca_file}
max_prepared_statements=0
"""


def setting(name):
    return os.environ.get(name) or DEFAULTS.get(name, "")


def refusal():
    """Why the task environment cannot start the sidecar, or None when it can."""
    for name in REQUIRED:
        if not setting(name):
            return f"{name} is required"
    for name in COUNTS:
        if not POSITIVE.fullmatch(setting(name)):
            return f"{name} must be a positive integer"
    for name in WRITTEN:
        if "\n" in setting(name) or "\r" in setting(name):
            return f"{name} must not contain a line break"
    return None


def quote(value):
    """A field of the auth file: between double quotes, a double quote inside doubled."""
    return '"' + value.replace('"', '""') + '"'


def write(path, text):
    # os.environ decoded each value with the file system's encoding: encoding it back the same way writes every byte
    # as the task gave it, also one that is not UTF-8.
    with open(path, "wb") as file:
        file.write(os.fsencode(text))


def render(folder):
    """Writes the auth file and the config into the folder and returns the config's path."""
    os.makedirs(folder, exist_ok=True)
    userlist = f"{folder}/userlist.txt"
    write(userlist, f"{quote(setting('PGBOUNCER_AUTH_USER'))} {quote(setting('PGBOUNCER_AUTH_PASSWORD'))}\n")
    os.chmod(userlist, 0o600)
    config = f"{folder}/pgbouncer.ini"
    write(config, CONFIG.format(
        host=setting("PGBOUNCER_SERVER_HOST"), server_port=setting("PGBOUNCER_SERVER_PORT"),
        listen_port=setting("PGBOUNCER_LISTEN_PORT"), userlist=userlist,
        max_client_conn=setting("PGBOUNCER_MAX_CLIENT_CONN"),
        max_db_connections=setting("PGBOUNCER_MAX_DB_CONNECTIONS"),
        max_user_connections=setting("PGBOUNCER_MAX_USER_CONNECTIONS"),
        server_idle_timeout=setting("PGBOUNCER_SERVER_IDLE_TIMEOUT"),
        ca_file=setting("PGBOUNCER_SERVER_TLS_CA_FILE"),
    ))
    return config


def fail(message, status=1):
    print(f"pgbouncer-entrypoint: {message}", file=sys.stderr)
    return status


def main():
    problem = refusal()
    if problem:
        return fail(problem)
    folder = setting("PGBOUNCER_CONFIG_DIR")
    os.umask(0o077)
    try:
        config = render(folder)
    except OSError as error:
        return fail(f"cannot write the config in {folder}: {error.strerror}")
    # Python starts with SIGPIPE and SIGXFSZ ignored, and an ignored signal stays ignored across exec: pgbouncer gets
    # their default action back, as a shell would have left it.
    for number in (signal.SIGPIPE, signal.SIGXFSZ):
        signal.signal(number, signal.SIG_DFL)
    try:
        os.execvp("pgbouncer", ["pgbouncer", config])
    except OSError as error:
        # A shell's statuses: 127 for a command it cannot find, 126 for one it cannot execute.
        return fail(f"cannot run pgbouncer: {error.strerror}", 127 if isinstance(error, FileNotFoundError) else 126)


if __name__ == "__main__":
    sys.exit(main())
