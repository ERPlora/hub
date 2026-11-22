"""Tests of docker/pgbouncer_entrypoint.py, the start of the PgBouncer sidecar: it renders the config from the task's
environment and replaces itself with pgbouncer. A fake pgbouncer first on the PATH records how it was started.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "docker" / "pgbouncer_entrypoint.py"

# The fake writes its PID, its arguments, its umask and the signals it was started ignoring (`trap -p` lists those).
FAKE_PGBOUNCER = """#!/usr/bin/env bash
echo "$$ $*" >> "$CALLS_LOG"
echo "umask=$(umask)" >> "$CALLS_LOG.state"
trap -p PIPE XFSZ >> "$CALLS_LOG.state"
"""

REQUIRED = ["PGBOUNCER_SERVER_HOST", "PGBOUNCER_AUTH_USER", "PGBOUNCER_AUTH_PASSWORD",
            "PGBOUNCER_MAX_USER_CONNECTIONS"]
COUNTS = ["PGBOUNCER_MAX_USER_CONNECTIONS", "PGBOUNCER_SERVER_PORT", "PGBOUNCER_LISTEN_PORT",
          "PGBOUNCER_MAX_DB_CONNECTIONS", "PGBOUNCER_SERVER_IDLE_TIMEOUT", "PGBOUNCER_MAX_CLIENT_CONN"]
WRITTEN = ["PGBOUNCER_SERVER_HOST", "PGBOUNCER_AUTH_USER", "PGBOUNCER_AUTH_PASSWORD", "PGBOUNCER_SERVER_TLS_CA_FILE"]
OPTIONAL = ["PGBOUNCER_SERVER_PORT", "PGBOUNCER_LISTEN_PORT", "PGBOUNCER_SERVER_TLS_CA_FILE",
            "PGBOUNCER_MAX_DB_CONNECTIONS", "PGBOUNCER_SERVER_IDLE_TIMEOUT", "PGBOUNCER_MAX_CLIENT_CONN"]


class Sidecar:
    """The sidecar's task environment in a folder of its own, one run of the entrypoint and what it left behind."""

    def __init__(self, folder):
        self.folder = folder
        self.bin = folder / "bin"
        self.bin.mkdir()
        fake = self.bin / "pgbouncer"
        fake.write_text(FAKE_PGBOUNCER)
        fake.chmod(0o755)
        self.calls = folder / "calls.log"
        self.calls.write_text("")
        self.config_dir = folder / "pgbouncer"
        self.env = {name: value for name, value in os.environ.items() if not name.startswith("PGBOUNCER_")}
        self.env.update(PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}", CALLS_LOG=str(self.calls),
                        PGBOUNCER_CONFIG_DIR=str(self.config_dir), PGBOUNCER_SERVER_HOST="writer.cluster.example",
                        PGBOUNCER_AUTH_USER="hub_app", PGBOUNCER_AUTH_PASSWORD="s3cret",
                        PGBOUNCER_MAX_USER_CONNECTIONS="40")

    def run(self, command=None, **overrides):
        """Runs the entrypoint with these overrides of the task environment (None unsets one)."""
        env = dict(self.env)
        for name, value in overrides.items():
            if value is None:
                env.pop(name, None)
            else:
                env[name] = value
        process = subprocess.Popen(command or [sys.executable, str(SCRIPT)], env=env, cwd=self.folder,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate(timeout=60)
        self.pid, self.status = process.pid, process.returncode
        self.output = (out + err).decode(errors="backslashreplace")
        return self

    def refused(self, message):
        """It stopped with status 1, printed only this line and never started pgbouncer."""
        return (self.status, self.output, self.called()) == (1, f"pgbouncer-entrypoint: {message}\n", "")

    def stopped_without_pgbouncer(self, status):
        """It stopped with this status and a single line of its own, and pgbouncer never ran."""
        lines = self.output.splitlines()
        return (self.status == status and len(lines) == 1 and lines[0].startswith("pgbouncer-entrypoint: ")
                and self.called() == "")

    def called(self):
        return self.calls.read_text()

    def state(self):
        return Path(f"{self.calls}.state").read_text()

    def ini(self):
        return (self.config_dir / "pgbouncer.ini").read_text().splitlines()

    def has(self, *lines):
        return set(lines) <= set(self.ini())

    def userlist(self):
        return (self.config_dir / "userlist.txt").read_bytes()


def mode(path):
    return path.stat().st_mode & 0o777


@pytest.fixture
def sidecar(tmp_path):
    return Sidecar(tmp_path)


@pytest.fixture
def started(sidecar):
    """A run with the task's required settings only."""
    return sidecar.run()


@pytest.mark.parametrize("name", REQUIRED)
@pytest.mark.parametrize("value", [None, ""], ids=["missing", "empty"])
def test_a_missing_or_empty_required_setting_stops_it_naming_the_setting(sidecar, name, value):
    assert sidecar.run(**{name: value}).refused(f"{name} is required")


@pytest.mark.parametrize("name", COUNTS)
@pytest.mark.parametrize("value", ["forty", "0"])
def test_counts_and_ports_take_positive_integers_only(sidecar, name, value):
    assert sidecar.run(**{name: value}).refused(f"{name} must be a positive integer")


@pytest.mark.parametrize("value", ["08", "5x", " 5", "-1", "٣"])
def test_a_count_is_ascii_digits_without_a_leading_zero_or_anything_around(sidecar, value):
    sidecar.run(PGBOUNCER_MAX_DB_CONNECTIONS=value)
    assert sidecar.refused("PGBOUNCER_MAX_DB_CONNECTIONS must be a positive integer")


@pytest.mark.parametrize("name", WRITTEN)
@pytest.mark.parametrize("line_break", ["\n", "\r"], ids=["LF", "CR"])
def test_a_line_break_in_a_written_value_is_refused_so_nothing_is_injected(sidecar, name, line_break):
    sidecar.run(**{name: f"pass{line_break}[pgbouncer]"})
    assert sidecar.refused(f"{name} must not contain a line break")


def test_the_first_failed_check_is_the_one_reported(sidecar):
    sidecar.run(PGBOUNCER_AUTH_USER=None, PGBOUNCER_SERVER_PORT="x", PGBOUNCER_AUTH_PASSWORD="a\nb")
    assert sidecar.refused("PGBOUNCER_AUTH_USER is required")
    sidecar.run(PGBOUNCER_SERVER_PORT="x", PGBOUNCER_AUTH_PASSWORD="a\nb")
    assert sidecar.refused("PGBOUNCER_SERVER_PORT must be a positive integer")


def test_writes_the_pool_settings_of_the_hub_databases(started):
    assert started.status == 0
    assert started.has("pool_mode=transaction", "auth_type=scram-sha-256", "default_pool_size=3",
                       "max_db_connections=3", "max_client_conn=300", "server_idle_timeout=10",
                       "autodb_idle_timeout=300", "query_wait_timeout=10", "server_tls_sslmode=verify-full",
                       "max_prepared_statements=0")


def test_writer_dns_expires_within_awss_five_second_budget_and_login_retries_soon(started):
    assert started.has("dns_max_ttl=5", "server_login_retry=2")


def test_a_writer_name_that_failed_to_resolve_is_asked_again_within_the_same_five_seconds(started):
    assert started.has("dns_nxdomain_ttl=5")


def test_an_idle_hub_database_costs_no_server_connection_no_minimum_no_reserve(started):
    assert started.has("min_pool_size=0", "reserve_pool_size=0")


def test_every_setting_is_written_once(started):
    names = [line.split("=")[0] for line in started.ini() if "=" in line and not line.startswith("*")]
    assert len(names) == len(set(names)) == 21


def test_listens_on_loopback_only_without_a_unix_socket(started):
    assert started.has("listen_addr=127.0.0.1", "unix_socket_dir=")


def test_max_user_connections_comes_from_the_task(started):
    assert started.has("max_user_connections=40")


def test_defaults_listen_on_6432_the_writer_on_5432_the_rds_bundle_as_ca(started):
    assert started.has("listen_port=6432", "* = host=writer.cluster.example port=5432",
                       "server_tls_ca_file=/etc/ssl/certs/rds-global-bundle.pem")


def test_the_auth_file_sits_next_to_the_config_under_the_writable_dir(started):
    assert started.has(f"auth_file={started.config_dir}/userlist.txt")


def test_every_database_goes_to_the_writer_under_databases(started):
    ini = started.ini()
    assert ini[:2] == ["[databases]", "* = host=writer.cluster.example port=5432"]
    assert ini[3] == "[pgbouncer]"


def test_the_userlist_holds_only_the_auth_user_readable_by_its_owner_only(started):
    assert started.userlist() == b'"hub_app" "s3cret"\n'
    assert mode(started.config_dir / "userlist.txt") == 0o600


def test_execs_pgbouncer_with_the_config_same_pid_no_wrapper_left(started):
    assert started.called() == f"{started.pid} {started.config_dir}/pgbouncer.ini\n"


def test_never_prints_the_password(started):
    assert started.output == ""


def test_explicit_ports_ca_file_and_connection_cap_win_over_the_defaults(sidecar):
    sidecar.run(PGBOUNCER_SERVER_PORT="5433", PGBOUNCER_LISTEN_PORT="6433", PGBOUNCER_MAX_USER_CONNECTIONS="20",
                PGBOUNCER_SERVER_TLS_CA_FILE="/etc/ssl/certs/other.pem")
    assert sidecar.status == 0
    assert sidecar.has("listen_port=6433", "* = host=writer.cluster.example port=5433",
                       "server_tls_ca_file=/etc/ssl/certs/other.pem", "max_user_connections=20")


def test_the_per_database_cap_sets_the_pool_size_too_idle_timeout_and_client_cap_from_the_task(sidecar):
    sidecar.run(PGBOUNCER_MAX_DB_CONNECTIONS="6", PGBOUNCER_SERVER_IDLE_TIMEOUT="15", PGBOUNCER_MAX_CLIENT_CONN="500")
    assert sidecar.status == 0
    assert sidecar.has("default_pool_size=6", "max_db_connections=6", "server_idle_timeout=15",
                       "max_client_conn=500", "min_pool_size=0", "reserve_pool_size=0")


def test_an_empty_optional_setting_takes_its_default(sidecar):
    sidecar.run(**dict.fromkeys(OPTIONAL, ""))
    assert sidecar.status == 0
    assert sidecar.has("listen_port=6432", "* = host=writer.cluster.example port=5432",
                       "server_tls_ca_file=/etc/ssl/certs/rds-global-bundle.pem", "default_pool_size=3",
                       "max_db_connections=3", "server_idle_timeout=10", "max_client_conn=300")


def test_double_quotes_in_the_userlist_are_doubled(sidecar):
    sidecar.run(PGBOUNCER_AUTH_USER='hub"app', PGBOUNCER_AUTH_PASSWORD='pa"ss""word')
    assert sidecar.status == 0
    assert sidecar.userlist() == b'"hub""app" "pa""ss""""word"\n'


def test_a_password_that_is_not_utf8_reaches_the_userlist_byte_for_byte(sidecar):
    sidecar.run(PGBOUNCER_AUTH_PASSWORD=b"p\xff\xfe\x80w")
    assert sidecar.status == 0
    assert sidecar.userlist() == b'"hub_app" "p\xff\xfe\x80w"\n'


def test_the_config_its_folder_and_what_pgbouncer_writes_stay_with_their_owner(started):
    assert mode(started.config_dir) == 0o700
    assert mode(started.config_dir / "pgbouncer.ini") == 0o600
    assert "umask=0077\n" in started.state()


def test_a_userlist_left_by_an_earlier_start_is_closed_to_its_owner_again(sidecar):
    sidecar.config_dir.mkdir()
    (sidecar.config_dir / "userlist.txt").write_text("old")
    (sidecar.config_dir / "userlist.txt").chmod(0o644)
    sidecar.run()
    assert sidecar.userlist() == b'"hub_app" "s3cret"\n'
    assert mode(sidecar.config_dir / "userlist.txt") == 0o600


def test_pgbouncer_starts_with_the_default_action_of_the_signals_python_ignores(started):
    assert started.state() == "umask=0077\n"


def test_runs_as_a_command_found_on_the_path(sidecar):
    sidecar.run(command=[str(SCRIPT)])
    assert sidecar.status == 0
    assert sidecar.called() == f"{sidecar.pid} {sidecar.config_dir}/pgbouncer.ini\n"


def test_without_pgbouncer_it_stops_with_the_status_of_a_command_not_found(sidecar, tmp_path):
    (tmp_path / "empty").mkdir()
    sidecar.run(PATH=str(tmp_path / "empty"))
    assert sidecar.stopped_without_pgbouncer(127)


def test_a_pgbouncer_it_cannot_execute_stops_it_with_the_status_of_a_command_not_executable(sidecar):
    (sidecar.bin / "pgbouncer").chmod(0o644)
    sidecar.run(PATH=str(sidecar.bin))
    assert sidecar.stopped_without_pgbouncer(126)


def test_a_config_folder_it_cannot_create_stops_it_naming_the_folder(sidecar):
    sidecar.config_dir.write_text("a file where the folder goes")
    sidecar.run()
    assert sidecar.stopped_without_pgbouncer(1)
    assert str(sidecar.config_dir) in sidecar.output
