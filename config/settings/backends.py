import hashlib

from decouple import config
from psycopg_pool import ConnectionPool

from base.cache import local_location
from base.tenancy.names import MAX_CONTROL
from config.settings.core import DEBUG, ERPLORA_ENVIRONMENT

# Database: Postgres only, also locally (compose.yaml). Django's native pool, never
# CONN_MAX_AGE > 0 with it. In production every connection verifies Aurora's certificate and host
# name (DB_SSLMODE=verify-full, DB_SSLROOTCERT = the RDS bundle in the image) and names its task
# (DB_APPLICATION_NAME, pg_stat_activity); each option only when set. A dead database fails within
# DB_CONNECT_TIMEOUT seconds, both waiting for a pooled connection and per connection attempt
# (psycopg: 30 s and 130 s), so /readyz answers 503 before its probes give up. The pool keeps one
# connection and gives back the rest of a burst one per minute (max_idle; psycopg's default of 600 s kept
# a scanner's 8 connections open for over an hour).

db_optional_options = {
    "DB_SSLMODE": "sslmode",
    "DB_SSLROOTCERT": "sslrootcert",
    "DB_APPLICATION_NAME": "application_name",
}
db_connect_timeout = config("DB_CONNECT_TIMEOUT", default=5, cast=int)
# Not test_hub: that one belongs to the packages/live suite, which may run at the same time. Two runs
# of this suite at once (two sessions, two checkouts) each set their own TEST_DB_NAME, as saas-next.
# Every database the suite makes derives from it: pytest-xdist appends `_gwN` and the tenancy a demo's
# `_demo_<hex>`, its longest (base.tenancy.names, which refuses a name past PostgreSQL's 63 characters). A name with no
# room for both (`_gw999`: up to 1000 workers) keeps its first characters and the first 8 of its
# SHA-256: the same database every run (--reuse-db, the fleet's sweep) and another for another name.
TEST_DB_NAME = config("TEST_DB_NAME", default="test_hub_next")
if len(TEST_DB_NAME.encode()) > (fitting := MAX_CONTROL - len("_gw999")):
    TEST_DB_NAME = (
        TEST_DB_NAME.encode()[: fitting - len("_12345678")].decode(errors="ignore")
        + f"_{hashlib.sha256(TEST_DB_NAME.encode()).hexdigest()[:8]}"
    )

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="hub"),
        "USER": config("DB_USER", default="hub"),
        "PASSWORD": config("DB_PASSWORD", default="hub"),
        "HOST": config("DB_HOST", default="127.0.0.1"),
        "PORT": config("DB_PORT", default=5432, cast=int),
        "OPTIONS": {
            "pool": {
                "min_size": 1,
                "max_size": 8,
                "max_idle": 60,
                "timeout": db_connect_timeout,
                # A connection the server cut while it sat in the pool (a restart, a switchover) is never handed out.
                "check": ConnectionPool.check_connection,
            },
            "connect_timeout": db_connect_timeout,
            **{
                option: value
                for env, option in db_optional_options.items()
                if (value := config(env, default=""))
            },
        },
        "TEST": {"NAME": TEST_DB_NAME},
    }
}

# The migrator's role (hub_migrator: DDL and CREATEDB) for the direct connections that make and change a
# hub's database: its `<db_name>__ddl` alias and the maintenance connection to `postgres` (base.tenancy.connections,
# base.tenancy.ops). Only the worker and the hub-migrate task have it (aws stacks/prod/apps.tf,
# hub_migrator_credentials; never the web). Unset, there is no migrator (base.tenancy.credentials fails closed, never
# hub_app), except in development (DEBUG, the suite), where the compose Postgres's user is every role.
DB_MIGRATOR_USER = config("DB_MIGRATOR_USER", default=DATABASES["default"]["USER"] if DEBUG else "")
DB_MIGRATOR_PASSWORD = config("DB_MIGRATOR_PASSWORD", default=DATABASES["default"]["PASSWORD"] if DEBUG else "")

# The SaaS's `saas` database, schema `shared`, only for register_apps.
# Declared only where its credentials exist: in production the worker task (SHARED_DB_USER, role
# hub_shared), locally always (compose.yaml's user). Straight to Aurora's writer (the PgBouncer
# sidecar only knows hub_app) with the TLS and timeout of every direct connection; one short
# connection when the worker starts, no pool.
SHARED_DB_USER = config("SHARED_DB_USER", default="hub" if DEBUG else "")
if SHARED_DB_USER:
    DATABASES["shared"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("SHARED_DB_NAME", default="saas"),
        "USER": SHARED_DB_USER,
        "PASSWORD": config("SHARED_DB_PASSWORD", default="hub")
        if DEBUG
        else config("SHARED_DB_PASSWORD"),
        "HOST": config("DB_HOST", default="127.0.0.1"),
        "PORT": config("DB_PORT", default=5432, cast=int),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {
            option: value
            for option, value in DATABASES["default"]["OPTIONS"].items()
            if option != "pool"
        },
        "TEST": {"NAME": f"{TEST_DB_NAME}_shared"},
    }
# The template of every hub's alias: base.tenancy.connections copies
# it, NAME aside, for each hub with a database of its own, and nobody ever connects to the template itself (its clone
# would fail). The hubs' databases go through the PgBouncer sidecar of the task in transaction mode
# (PGBOUNCER_HOST/PORT, aws stacks/prod/apps.tf; locally the Postgres of compose.yaml, directly): no pool,
# CONN_MAX_AGE 0, no server-side cursors and no prepared statements: prepare_threshold=None explicitly (Django leaves
# it unset and psycopg 3 prepares on a statement's fifth run, which PgBouncer with max_prepared_statements=0 loses:
# «prepared statement _pg3_N does not exist»). The sidecar listens on the task's own loopback, so TLS goes from
# PgBouncer to Aurora, not to it.
PGBOUNCER_HOST = config("PGBOUNCER_HOST", default="")
# PgBouncer's connections per database, each task's (ERPlora/aws stacks/prod/apps.tf: 48 in prod and in pre): no plan
# gets more transactions at once than this (base.tenancy.limits), or what passes it would wait in PgBouncer and fail
# uncounted.
PGBOUNCER_MAX_DB_CONNECTIONS = config("PGBOUNCER_MAX_DB_CONNECTIONS", default=6, cast=int)
DATABASES["hub_template"] = {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": f"{DATABASES['default']['NAME']}_template",
    "USER": DATABASES["default"]["USER"],
    "PASSWORD": DATABASES["default"]["PASSWORD"],
    "HOST": PGBOUNCER_HOST or DATABASES["default"]["HOST"],
    "PORT": config("PGBOUNCER_PORT", default=6432, cast=int) if PGBOUNCER_HOST else DATABASES["default"]["PORT"],
    "CONN_MAX_AGE": 0,
    "DISABLE_SERVER_SIDE_CURSORS": True,
    "OPTIONS": {
        **{
            option: value
            for option, value in DATABASES["default"]["OPTIONS"].items()
            if option != "pool" and not (PGBOUNCER_HOST and option in ("sslmode", "sslrootcert"))
        },
        "prepare_threshold": None,
    },
    "TEST": {"NAME": f"{TEST_DB_NAME}_template"},
}
# First: the models of `shared` go to that alias only. Then the TenantRouter: control's models to `default`, a hub's
# to the alias of the active use_hub (base.tenancy.router).
DATABASE_ROUTERS = ["base.routers.SharedRouter", "base.tenancy.router.TenantRouter"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Cache: the shared Valkey (TLS, rediss://) when VALKEY_URL is set, with a prefix per project and
# environment (hub, pre-hub: pre shares prod's Valkey), a TTL on every key (never TIMEOUT=None) and
# 2 s socket timeouts (a Valkey that hangs fails the call, not the request; Django hands OPTIONS to
# redis-py); otherwise a folder of the machine's disk per control database, shared by its web server and its worker as
# Valkey is, refusing what that Valkey (a cluster) refuses: a call on keys of different hash slots (base/cache.py).

VALKEY_URL = config("VALKEY_URL", default="")
CACHE_KEY_PREFIX = "hub" if ERPLORA_ENVIRONMENT == "prod" else f"{ERPLORA_ENVIRONMENT}-hub"
CACHES = {
    "default": (
        {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": VALKEY_URL,
            "KEY_PREFIX": CACHE_KEY_PREFIX,
            "TIMEOUT": 300,
            "OPTIONS": {"socket_connect_timeout": 2, "socket_timeout": 2},
        }
        if VALKEY_URL
        else {"BACKEND": "base.cache.ClusterFileBasedCache", "LOCATION": local_location(DATABASES["default"]["NAME"])}
    )
}
