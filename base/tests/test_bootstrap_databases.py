"""``manage.py bootstrap_databases``: the ``db-bootstrap`` task (aws-next README, «Contrato»).

Run once as the RDS master on ``postgres``, and again to rotate the passwords: it reads every
``*_PASSWORD``, prints one line per step (``created``/``exists``/``updated``/``skipped``) and
never a password, and exits non-zero (a ``CommandError``, which the infra's ``task_failed`` rule
reports) when a variable is missing or a step fails. What the roles can do afterwards is
``test_bootstrap.py``, whose helpers these tests reuse (same emulated master, per-process prefix
through ``--prefix``).
"""

import os
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from base.tenancy import bootstrap
from base.tests.test_bootstrap import (
    VARIABLES,
    connect_error,
    create_master,
    drop_prefixed,
    superuser,
)

#: The extensions the command creates here: the emulated master's are trusted (``test_bootstrap.py``,
#: ``rds_cluster`` for ``vector``).
EXTENSIONS = ("pgcrypto",)
MISSING = "erplora_no_such_extension"


@pytest.fixture
def prefix():
    value = f"test_bsf_{os.getpid()}_"
    drop_prefixed(value)
    yield value
    drop_prefixed(value)


@pytest.fixture
def passwords(monkeypatch) -> dict[str, str]:
    """Every ``*_PASSWORD`` in the environment; role → password."""
    values = {role: f"pw-{role}-1" for role in VARIABLES}
    for role, variable in VARIABLES.items():
        monkeypatch.setenv(variable, values[role])
    return values


@pytest.fixture
def master(prefix, monkeypatch, settings) -> dict:
    """The command connects as the emulated master; ``DEBUG`` skips a missing extension."""
    conninfo = create_master(prefix)
    monkeypatch.setattr(bootstrap, "admin_conninfo", lambda: conninfo)
    monkeypatch.setattr(bootstrap, "TEMPLATE_EXTENSIONS", EXTENSIONS)
    monkeypatch.setattr(bootstrap, "SAAS_EXTENSIONS", EXTENSIONS)
    settings.DEBUG = True
    return conninfo


def run_command(prefix: str) -> tuple[str, str]:
    out, err = StringIO(), StringIO()
    call_command("bootstrap_databases", prefix=prefix, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def test_first_run_creates_everything_and_a_second_run_only_reports_exists_or_updated(
    prefix, passwords, master
):
    first, _ = run_command(prefix)
    second, second_err = run_command(prefix)

    for role in VARIABLES:
        assert f"role {prefix}{role}: created" in first
        assert f"role {prefix}{role}: updated" in second
    for database in ("hub", "hub_template", "saas"):
        assert f"database {prefix}{database}: created" in first
        assert f"database {prefix}{database}: exists" in second
    assert f"schema shared on {prefix}saas: created" in first
    assert f"schema shared on {prefix}saas: exists" in second
    for database in ("hub_template", "saas"):
        assert f"extension pgcrypto on {prefix}{database}: created" in first
        assert f"extension pgcrypto on {prefix}{database}: exists" in second
    assert ": created" not in second
    assert "WARNING" not in second_err
    for value in passwords.values():
        assert value not in first + second + second_err


def test_rotating_a_password_lets_the_role_in_with_the_new_one_only(
    prefix, passwords, master, monkeypatch
):
    run_command(prefix)
    hub_app = prefix + "hub_app"
    assert connect_error(hub_app, passwords["hub_app"], prefix + "hub") is None

    monkeypatch.setenv("HUB_APP_PASSWORD", "pw-hub_app-2")
    run_command(prefix)

    assert connect_error(hub_app, "pw-hub_app-2", prefix + "hub") is None
    assert "password authentication failed" in connect_error(
        hub_app, passwords["hub_app"], prefix + "hub"
    )


def test_a_missing_password_exits_non_zero_and_touches_nothing(
    prefix, passwords, master, monkeypatch
):
    monkeypatch.delenv("HUB_SHARED_PASSWORD")
    monkeypatch.setenv("SAAS_APP_PASSWORD", "")

    with pytest.raises(CommandError) as raised:
        run_command(prefix)

    assert raised.value.returncode != 0
    assert "HUB_SHARED_PASSWORD" in str(raised.value)
    assert "SAAS_APP_PASSWORD" in str(raised.value)
    with superuser() as conn:
        assert not conn.execute(
            "SELECT 1 FROM pg_roles WHERE starts_with(rolname, %s) AND rolname <> %s",
            [prefix, prefix + "master"],
        ).fetchall()


def test_a_failing_step_exits_non_zero_and_names_the_step(
    prefix, passwords, monkeypatch, settings
):
    conninfo = create_master(prefix, createrole=False)
    monkeypatch.setattr(bootstrap, "admin_conninfo", lambda: conninfo)
    settings.DEBUG = True

    with pytest.raises(CommandError) as raised:
        run_command(prefix)

    assert raised.value.returncode != 0
    assert f"role {prefix}hub_app" in str(raised.value)
    assert "permission denied" in str(raised.value)


def test_an_invalid_prefix_is_refused_before_connecting(passwords, monkeypatch):
    def no_connection():
        raise AssertionError("connected with an invalid prefix")

    monkeypatch.setattr(bootstrap, "admin_conninfo", no_connection)

    with pytest.raises(CommandError, match="prefix"):
        run_command("Bad-Prefix")


@pytest.mark.parametrize(
    ("constant", "database"),
    [("TEMPLATE_EXTENSIONS", "hub_template"), ("SAAS_EXTENSIONS", "saas")],
)
def test_a_missing_extension_fails_in_production_and_warns_locally(
    prefix, passwords, master, settings, monkeypatch, constant, database
):
    monkeypatch.setattr(bootstrap, constant, (MISSING,))
    subject = f"extension {MISSING} on {prefix}{database}"
    settings.DEBUG = False

    with pytest.raises(CommandError) as raised:
        run_command(prefix)
    settings.DEBUG = True
    out, err = run_command(prefix)

    assert raised.value.returncode != 0
    assert f"{subject}: not available on this server" in str(raised.value)
    assert f"bootstrap_databases: {subject}: skipped (not available on this server)" in out
    assert f"WARNING {subject}: skipped" in err


def test_the_pre_prefix_names_every_database_and_role_the_infra_expects(passwords, monkeypatch):
    # The db-bootstrap task of pre runs `bootstrap_databases --prefix pre_` with prod's image (plan
    # 2026-10-14-entorno-pre §1.2): these nine names are the ones its secret erplora/pre/db and the
    # pre tasks' DB_NAME carry. A prefix, never a suffix: no `hub\_%` pattern of prod reaches them.
    seen = {}

    def record(*, names, **kwargs):
        seen["names"] = names
        return []

    monkeypatch.setattr(bootstrap, "bootstrap", record)
    run_command("pre_")

    assert seen["names"] == bootstrap.Names(
        control="pre_hub",
        template="pre_hub_template",
        saas="pre_saas",
        hub_app="pre_hub_app",
        hub_migrator="pre_hub_migrator",
        hub_admin="pre_hub_admin",
        saas_app="pre_saas_app",
        saas_migrator="pre_saas_migrator",
        hub_shared="pre_hub_shared",
    )
