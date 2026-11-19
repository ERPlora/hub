"""The databases the Hub connects to: control's pool, the hubs' alias through PgBouncer, the SaaS's `shared`
alias, and how long a cut of the database is waited for."""

import decouple
import pytest
from django.conf import settings
from psycopg_pool import ConnectionPool

from config.tests.settings_env import DEVELOPMENT_ENV, PRODUCTION_ENV


def test_defaults_are_the_local_compose_database_with_a_pool(load_settings):
    loaded = load_settings(**DEVELOPMENT_ENV)
    db = loaded["DATABASES"]["default"]
    assert db["ENGINE"] == "django.db.backends.postgresql"
    assert (db["NAME"], db["USER"], db["PASSWORD"], db["HOST"], db["PORT"]) == (
        "hub",
        "hub",
        "hub",
        "127.0.0.1",
        5432,
    )
    # A connection the server cut while it sat in the pool is never handed out (BASE-F111).
    pool = {"min_size": 1, "max_size": 8, "max_idle": 60, "timeout": 5, "check": ConnectionPool.check_connection}
    assert db["OPTIONS"]["pool"] == pool
    # Its own test database, so it never drops the one the packages/live suite is using.
    assert db["TEST"]["NAME"] == "test_hub_next"


def test_database_comes_from_the_environment(load_settings):
    loaded = load_settings(
        **DEVELOPMENT_ENV, DB_NAME="other", DB_HOST="db.internal", DB_PORT="6543"
    )
    db = loaded["DATABASES"]["default"]
    assert (db["NAME"], db["HOST"], db["PORT"]) == ("other", "db.internal", 6543)


def test_a_burst_of_pooled_connections_is_given_back_within_minutes(load_settings):
    # psycopg_pool closes one connection above min_size per max_idle, 600 s by default: a scanner
    # burst on *.erplora.com (60 requests/s) left the idle hub web holding its 8 control
    # connections for over an hour. With 60 s it is back to one within 7 minutes; that one stays
    # open for the next request.
    pool = load_settings(**DEVELOPMENT_ENV)["DATABASES"]["default"]["OPTIONS"]["pool"]
    assert (pool["min_size"], pool["max_size"], pool["max_idle"]) == (1, 8, 60)


@pytest.mark.django_db
def test_the_running_pool_closes_idle_connections_after_60_seconds():
    # Django hands OPTIONS["pool"] to psycopg_pool as is: the pool this process opened has it.
    from django.db import connection

    connection.ensure_connection()
    assert (connection.pool.min_size, connection.pool.max_idle) == (1, 60)


def test_database_tls_and_application_name_only_when_set(load_settings):
    options = load_settings(**DEVELOPMENT_ENV)["DATABASES"]["default"]["OPTIONS"]
    assert options == {
        "pool": {"min_size": 1, "max_size": 8, "max_idle": 60, "timeout": 5, "check": ConnectionPool.check_connection},
        "connect_timeout": 5,
    }
    loaded = load_settings(
        **PRODUCTION_ENV,
        DB_SSLMODE="verify-full",
        DB_SSLROOTCERT="/etc/ssl/certs/rds-global-bundle.pem",
        DB_APPLICATION_NAME="worker",
    )
    assert loaded["DATABASES"]["default"]["OPTIONS"] == {
        "pool": {"min_size": 1, "max_size": 8, "max_idle": 60, "timeout": 5, "check": ConnectionPool.check_connection},
        "connect_timeout": 5,
        "sslmode": "verify-full",
        "sslrootcert": "/etc/ssl/certs/rds-global-bundle.pem",
        "application_name": "worker",
    }


def test_a_dead_database_fails_within_db_connect_timeout_seconds(load_settings):
    # psycopg waits 30 s for a connection from the pool and 130 s per connection attempt, so a dead
    # database made /readyz answer 503 after its probes had given up. Both waits are
    # DB_CONNECT_TIMEOUT seconds, 5 by default.
    options = load_settings(**DEVELOPMENT_ENV)["DATABASES"]["default"]["OPTIONS"]
    assert (options["connect_timeout"], options["pool"]["timeout"]) == (5, 5)
    options = load_settings(**DEVELOPMENT_ENV, DB_CONNECT_TIMEOUT="2")["DATABASES"][
        "default"
    ]["OPTIONS"]
    assert (options["connect_timeout"], options["pool"]["timeout"]) == (2, 2)


def test_a_cut_of_the_database_is_waited_for_far_below_the_load_balancer(load_settings):
    # BASE-F111: a request waits for a cut up to its limit, and its last try may still wait DB_CONNECT_TIMEOUT for a
    # pooled connection and as long to connect: all of it far below the 120 s of the ALB's idle_timeout.
    loaded = load_settings(**DEVELOPMENT_ENV)
    cut = loaded["LIVE"]["database_cut"]
    connect_timeout = loaded["DATABASES"]["default"]["OPTIONS"]["connect_timeout"]
    assert cut["wait_seconds"] == 20
    assert cut["wait_seconds"] + 2 * connect_timeout < 60
    assert load_settings(**DEVELOPMENT_ENV, DB_CUT_WAIT_SECONDS="8")["LIVE"]["database_cut"]["wait_seconds"] == 8


def test_what_tries_again_on_its_own_gets_its_503_at_once(load_settings):
    # The SaaS's signed calls try again themselves, and /readyz has to say the database is gone before its probes give up.
    prefixes = load_settings(**DEVELOPMENT_ENV)["LIVE"]["database_cut"]["no_wait_prefixes"]
    assert sorted(prefixes) == ["/internal/", "/readyz"]


# ── The `shared` alias: the SaaS's `saas` database, for register_apps only ──


def test_development_always_has_the_shared_alias_on_the_local_saas_database(
    load_settings,
):
    shared = load_settings(**DEVELOPMENT_ENV)["DATABASES"]["shared"]
    assert shared["ENGINE"] == "django.db.backends.postgresql"
    # compose.yaml: one user `hub` for everything, owner of the `saas` database.
    assert (
        shared["NAME"],
        shared["USER"],
        shared["PASSWORD"],
        shared["HOST"],
        shared["PORT"],
    ) == (
        "saas",
        "hub",
        "hub",
        "127.0.0.1",
        5432,
    )
    # Its own test database, where a session fixture creates the schema and the two tables.
    assert shared["TEST"]["NAME"] == "test_hub_next_shared"


def test_the_migrators_role_is_the_default_connections_only_in_development(load_settings):
    """Locally (and in the suite) the compose Postgres's user is every role; in AWS only the worker and hub-migrate
    carry DB_MIGRATOR_* (aws stacks/prod/apps.tf), and without them there is no migrator (base.tenancy.credentials)."""
    development = load_settings(**DEVELOPMENT_ENV, DB_USER="hub", DB_PASSWORD="hub-pw")
    production = load_settings(**PRODUCTION_ENV, DB_USER="hub_app", DB_PASSWORD="app-pw")
    worker = load_settings(**PRODUCTION_ENV, DB_MIGRATOR_USER="hub_migrator", DB_MIGRATOR_PASSWORD="migrator-pw")

    assert (development["DB_MIGRATOR_USER"], development["DB_MIGRATOR_PASSWORD"]) == ("hub", "hub-pw")
    assert (production["DB_MIGRATOR_USER"], production["DB_MIGRATOR_PASSWORD"]) == ("", "")
    assert (worker["DB_MIGRATOR_USER"], worker["DB_MIGRATOR_PASSWORD"]) == ("hub_migrator", "migrator-pw")


def test_the_hubs_template_alias_is_named_after_control_and_reaches_it_directly_in_development(load_settings):
    """Every hub's alias copies hub_template (base.tenancy.connections); locally, the compose Postgres."""
    databases = load_settings(**DEVELOPMENT_ENV, DB_NAME="pre_hub", TEST_DB_NAME="test_hub_sup")["DATABASES"]
    template = databases["hub_template"]

    assert template["NAME"] == "pre_hub_template"
    assert (template["HOST"], template["PORT"]) == (databases["default"]["HOST"], databases["default"]["PORT"])
    assert (template["CONN_MAX_AGE"], template["DISABLE_SERVER_SIDE_CURSORS"]) == (0, True)
    assert template["OPTIONS"] == {"connect_timeout": 5, "prepare_threshold": None}
    assert template["TEST"]["NAME"] == "test_hub_sup_template"


def test_in_aws_the_hubs_go_through_the_pgbouncer_sidecar_without_tls_to_it(load_settings):
    """The sidecar listens on the task's loopback; TLS goes from it to Aurora, so the alias drops the
    writer's sslmode and certificate and keeps the rest."""
    loaded = load_settings(
        **PRODUCTION_ENV,
        DB_HOST="writer.cluster.eu-west-1.rds.amazonaws.com",
        DB_SSLMODE="verify-full",
        DB_SSLROOTCERT="/etc/ssl/certs/rds-global-bundle.pem",
        DB_APPLICATION_NAME="hub",
        PGBOUNCER_HOST="127.0.0.1",
        PGBOUNCER_PORT="6432",
    )
    template = loaded["DATABASES"]["hub_template"]

    assert (template["HOST"], template["PORT"]) == ("127.0.0.1", 6432)
    assert template["OPTIONS"] == {"connect_timeout": 5, "application_name": "hub", "prepare_threshold": None}
    assert loaded["DATABASE_ROUTERS"] == ["base.routers.SharedRouter", "base.tenancy.router.TenantRouter"]


def test_what_pgbouncer_gives_each_database_is_prod_s_unless_the_environment_says(load_settings):
    """No plan gets more at once than this (``base.tenancy.limits``): 48 in prod and in pre (ERPlora/aws
    ``stacks/prod/apps.tf``); without the setting, 6."""
    assert load_settings(**PRODUCTION_ENV)["PGBOUNCER_MAX_DB_CONNECTIONS"] == 6
    assert load_settings(**PRODUCTION_ENV, PGBOUNCER_MAX_DB_CONNECTIONS="3")["PGBOUNCER_MAX_DB_CONNECTIONS"] == 3


def test_the_shared_alias_opens_one_short_connection_without_a_pool(load_settings):
    shared = load_settings(**DEVELOPMENT_ENV)["DATABASES"]["shared"]
    assert shared["CONN_MAX_AGE"] == 0
    assert "pool" not in shared["OPTIONS"]
    assert shared["OPTIONS"] == {"connect_timeout": 5}


def test_production_without_shared_credentials_has_no_shared_alias(load_settings):
    # The web service never writes in `shared`: only the worker task receives SHARED_DB_USER.
    assert "shared" not in load_settings(**PRODUCTION_ENV)["DATABASES"]


def test_production_shared_alias_comes_from_its_secret_with_the_tls_of_every_direct_connection(
    load_settings,
):
    loaded = load_settings(
        **PRODUCTION_ENV,
        SHARED_DB_USER="hub_shared",
        SHARED_DB_PASSWORD="from-secrets-manager",
        DB_HOST="aurora.writer",
        DB_SSLMODE="verify-full",
        DB_SSLROOTCERT="/etc/ssl/certs/rds-global-bundle.pem",
    )
    shared = loaded["DATABASES"]["shared"]
    assert (shared["NAME"], shared["USER"], shared["PASSWORD"], shared["HOST"]) == (
        "saas",
        "hub_shared",
        "from-secrets-manager",
        "aurora.writer",
    )
    assert shared["OPTIONS"] == {
        "connect_timeout": 5,
        "sslmode": "verify-full",
        "sslrootcert": "/etc/ssl/certs/rds-global-bundle.pem",
    }
    assert shared["CONN_MAX_AGE"] == 0


def test_production_shared_alias_without_its_password_refuses_to_start(load_settings):
    with pytest.raises(decouple.UndefinedValueError, match="SHARED_DB_PASSWORD"):
        load_settings(**PRODUCTION_ENV, SHARED_DB_USER="hub_shared")


def test_the_shared_router_goes_first_and_the_tests_route_as_production_does(load_settings):
    # The TenantRouter goes after it and never touches `shared`.
    routers = ["base.routers.SharedRouter", "base.tenancy.router.TenantRouter"]
    assert load_settings(**PRODUCTION_ENV)["DATABASE_ROUTERS"] == routers
    assert settings.DATABASE_ROUTERS == routers
