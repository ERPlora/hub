"""Hot registration of the hubs' aliases (PLAN-DB §4 and §5; plan 2026-10-22-fase-2-tenencia, step 4).

A hub with a database of its own (``Hub.db_name``) gets its alias, ``hub_<hex of its id>`` (PLAN-DB §4), the first
time a process uses it: a copy of the static ``hub_template`` alias (``config/settings.py``: the PgBouncer sidecar in
transaction mode, no pool, ``CONN_MAX_AGE`` 0, no server-side cursors, no prepared statements) with the hub's database
as ``NAME`` and, for a hub on a :class:`control.models.Cluster`, that cluster's PgBouncer. Its ``NAME`` is the row's
``db_name`` (pre's ``pre_hub_<hex>``, a demo's ``<control>_demo_<hex>``), never derived from the id; an alias already
registered with another database is refused (``HubAliasConflict``): every thread keeps its connection to the first
one, so a hub moved to another database needs the process restarted.

``connections.settings`` is never changed in place: ``close_old_connections`` walks it from other threads, so a new
dict with the alias is swapped in, under a lock, after looking again. A hub of the shared database (``db_name=""``,
phase 1 until S5) stays on ``default``.

The migrator's alias, ``<db_name>__ddl`` (PLAN-DB §4 and §7), is the same database reached directly, without
PgBouncer and without the control database's pool, as the migrator's role (``settings.DB_MIGRATOR_USER``; the default
connection's where it is not set): only the migrator, the provisioning (``base.tenancy.provision``) and the tests'
template builder use it. :func:`migrator_conninfo` is the same connection in libpq's terms, for ``psycopg`` itself
(``base.tenancy.ops``: ``CREATE``/``DROP DATABASE`` on the maintenance database ``postgres``).
"""

import copy
import threading

from django.conf import settings as django_settings
from django.db import DEFAULT_DB_ALIAS, connections

from base.tenancy import names

#: The static alias every hub's alias is copied from; nobody connects to it.
TEMPLATE_ALIAS = "hub_template"
#: Options of a Django alias that are Django's or psycopg's, not libpq's.
NON_LIBPQ_OPTIONS = frozenset(
    {"pool", "isolation_level", "assume_role", "cursor_factory", "context", "prepare_threshold", "server_side_binding"}
)

_lock = threading.Lock()


class HubAliasConflict(RuntimeError):
    """A hub's alias this process registered with another database than its row names now."""


def hub_alias(hub) -> str:
    """The alias of ``hub``'s own database: ``hub_<hex>``, whatever the database's name."""
    return f"hub_{hub.id.hex}"


def control_name() -> str:
    """The control database's name, which every hub's database name derives from (``base.tenancy.names``)."""
    return connections.settings[DEFAULT_DB_ALIAS]["NAME"]


def _copied(base_alias: str, **overrides) -> dict:
    return copy.deepcopy(connections.settings[base_alias]) | overrides


def _register(alias: str, build) -> str:
    """Swap in a new ``connections.settings`` with ``alias`` (``build()`` its settings) unless it is there already."""
    if alias in connections.settings:
        return alias
    with _lock:
        if alias not in connections.settings:
            connections.settings = {**connections.settings, alias: build()}
    return alias


def register_hub_alias(hub) -> str:
    """The alias of ``hub``'s own database, registered if this process has not yet; its name is validated first."""
    name = names.validate(hub.db_name, control=control_name())
    alias = hub_alias(hub)
    registered = connections.settings.get(alias)
    if registered is not None and registered["NAME"] != name:
        raise HubAliasConflict(
            f"{alias} already reaches {registered['NAME']!r} in this process, and its hub now names {name!r}."
        )
    overrides = {"NAME": name}
    cluster = getattr(hub, "cluster", None)
    if cluster is not None:
        overrides |= {"HOST": cluster.pooler_host, "PORT": cluster.pooler_port}
    return _register(alias, lambda: _copied(TEMPLATE_ALIAS, **overrides))


def _migrator_role() -> tuple[str, str]:
    """The migrator's user and password: ``DB_MIGRATOR_USER``/``_PASSWORD``, or the default connection's."""
    if django_settings.DB_MIGRATOR_USER:
        return django_settings.DB_MIGRATOR_USER, django_settings.DB_MIGRATOR_PASSWORD
    default = connections.settings[DEFAULT_DB_ALIAS]
    return default["USER"], default["PASSWORD"]


def migrator_conninfo(dbname: str) -> dict:
    """The migrator's direct connection to ``dbname`` in libpq's terms (``psycopg.connect(**…)``): the default
    connection's server, TLS and timeout, the migrator's role, no pool."""
    default = connections.settings[DEFAULT_DB_ALIAS]
    user, password = _migrator_role()
    options = {key: value for key, value in default["OPTIONS"].items() if key not in NON_LIBPQ_OPTIONS}
    return {**options, "dbname": dbname, "host": default["HOST"], "port": default["PORT"], "user": user, "password": password}


def register_ddl_alias(db_name: str) -> str:
    """The migrator's alias of the database ``db_name`` (``<db_name>__ddl``): direct, as the migrator's role, no pool,
    closed after use."""
    names.validate(db_name, control=control_name())

    def build() -> dict:
        user, password = _migrator_role()
        settings = _copied(
            DEFAULT_DB_ALIAS,
            NAME=db_name,
            USER=user,
            PASSWORD=password,
            CONN_MAX_AGE=0,
            DISABLE_SERVER_SIDE_CURSORS=True,
        )
        settings["OPTIONS"].pop("pool", None)
        return settings

    return _register(f"{db_name}{names.DDL_SUFFIX}", build)


def alias_for(hub) -> str:
    """The alias ``hub``'s models go to: its database's, or ``default`` while it shares control's (``db_name=""``)."""
    if not hub.db_name:
        return DEFAULT_DB_ALIAS
    return register_hub_alias(hub)


def open_hub_alias(hub) -> str:
    """:func:`alias_for` with the database's identity checked (once per process and alias): what ``use_hub`` uses."""
    alias = alias_for(hub)
    if alias != DEFAULT_DB_ALIAS:
        from base.tenancy import identity

        identity.verify(alias, hub.id)
    return alias
