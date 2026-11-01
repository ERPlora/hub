"""Hot registration of the hubs' aliases (PLAN-DB §4 and §5; plan 2026-10-22-fase-2-tenencia, step 4).

A hub with a database of its own (``Hub.db_name``) gets its alias, ``hub_<hex of its id>`` (PLAN-DB §4), the first
time a process uses it: a copy of the static ``hub_template`` alias (``config/settings.py``: the PgBouncer sidecar in
transaction mode, no pool, ``CONN_MAX_AGE`` 0, no server-side cursors, no prepared statements) with the hub's database
as ``NAME`` and, for a hub on a :class:`control.models.Cluster`, that cluster's PgBouncer. Its ``NAME`` is the row's
``db_name`` (pre's ``pre_hub_<hex>``, a demo's ``<control>_demo_<hex>``), never derived from the id; an alias already
registered with another database is refused (``HubAliasConflict``): every thread keeps its connection to the first
one, so a hub moved to another database needs the process restarted. A template's database (``<control>_template…``)
never gets one: it is only cloned, and a connection to it would make its next clone fail (PLAN-DB §6).

Every hub's alias runs on the hubs' engine (``base.tenancy.backend``, ``base.tenancy.limits``): each transaction holds a
place of its hub's limiter in this process and carries its plan's ``statement_timeout``; registering the alias (on every
``use_hub``) makes or resizes that limiter from the hub's photo. The migrator's alias does not: its passes have their
own budget.

``connections.settings`` is never changed in place: ``close_old_connections`` walks it from other threads, so a new
dict with the alias is swapped in, under a lock, after looking again. A hub of the shared database (``db_name=""``,
phase 1 until S5) stays on ``default``.

The migrator's alias, ``<db_name>__ddl`` (PLAN-DB §4 and §7), is the same database reached directly, without
PgBouncer and without the control database's pool, as the migrator's role: only the migrator, the provisioning
(``base.tenancy.provision``) and the tests' template builder use it. :func:`migrator_conninfo` is the same connection
in libpq's terms, for ``psycopg`` itself (``base.tenancy.ops``: ``CREATE``/``DROP DATABASE`` on the maintenance
database ``postgres``).

A hub on a :class:`control.models.Cluster` (round 2026-10-30, S2a) is reached on that cluster: its alias through the
cluster's PgBouncer (its writer, directly, when the row names none) with the cluster's app role, its migrator's alias
and connection on the cluster's writer with the cluster's migrator role (``base.tenancy.credentials.credentials_for``).
A hub's alias never carries a migrator's role, nor asks for its secret: the web opens no other. Without a cluster, the
settings' own server and the environment's roles.
"""

import copy
import threading

from django.db import DEFAULT_DB_ALIAS, connections

from base.tenancy import limits, names
from base.tenancy.credentials import APP, MIGRATOR, credentials_for

#: The static alias every hub's alias is copied from; nobody connects to it.
TEMPLATE_ALIAS = "hub_template"
#: The default connection's TLS to the writer, which a hub's alias straight to a cluster's writer carries too.
TLS_OPTIONS = ("sslmode", "sslrootcert")
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


def _register(alias: str, build, *, replace: bool = False) -> str:
    """Swap in a new ``connections.settings`` with ``alias`` (``build()`` its settings) unless it is there already, or
    with its settings built again (``replace``)."""
    if alias in connections.settings and not replace:
        return alias
    with _lock:
        if replace or alias not in connections.settings:
            connections.settings = {**connections.settings, alias: build()}
    return alias


#: What a rotation of a cluster's secret changes in a hub's alias.
ROLE_KEYS = ("USER", "PASSWORD")
#: Where and as whom an alias reaches its database: a rotation changes its role, a move (``base.tenancy.move``) its
#: server. When the hub's row (read again by every request, live re-run and worker pass) says otherwise than the alias,
#: the alias is registered again with it and this thread's connection given it; another thread's takes it when that
#: thread opens the hub again.
REACH_KEYS = ("HOST", "PORT", *ROLE_KEYS)


def _take_this_threads_role(alias: str) -> None:
    """This thread's connection of ``alias``, if it has one, with the role its settings say now: closed and given them
    (another thread's takes them when that thread opens the hub again: every request does, through ``use_hub``)."""
    current = connections.settings[alias]
    for connection in connections.all(initialized_only=True):
        if connection.alias == alias and any(connection.settings_dict.get(key) != current[key] for key in REACH_KEYS):
            connection.close()
            connection.settings_dict = copy.deepcopy(current)


def _not_a_template(name: str, control: str) -> str:
    """``name``, unless it is one of ``control``'s templates (``InvalidDatabaseName``): only the migrator reaches those;
    nor the copy a hub left behind when it moved (``base.tenancy.move``): closed to the app, only ever dropped."""
    template = names.template_db_name(control)
    if name == template or name.startswith(f"{template}_"):
        raise names.InvalidDatabaseName(f"{name!r} is a template: it is only cloned, never a hub's database.")
    if names.is_moved(name, control=control):
        raise names.InvalidDatabaseName(f"{name!r} is the copy a hub left behind when it moved, never a hub's database.")
    return name


def register_hub_alias(hub) -> str:
    """The alias of ``hub``'s own database, registered if this process has not yet; its name is validated first, and
    a template's is refused. It runs on the hubs' engine, and its limiter follows ``hub``'s photo
    (``base.tenancy.limits``)."""
    control = control_name()
    name = _not_a_template(names.validate(hub.db_name, control=control), control)
    alias = hub_alias(hub)
    registered = connections.settings.get(alias)
    if registered is not None and registered["NAME"] != name:
        raise HubAliasConflict(
            f"{alias} already reaches {registered['NAME']!r} in this process, and its hub now names {name!r}."
        )
    overrides = {"NAME": name, "ENGINE": limits.ENGINE}
    cluster = getattr(hub, "cluster", None)
    if cluster is not None:
        found = credentials_for(cluster, APP)
        overrides |= {"USER": found.user, "PASSWORD": found.password}
        if cluster.pooler_host:
            overrides |= {"HOST": cluster.pooler_host, "PORT": cluster.pooler_port}
        else:
            # Its writer, directly (the task's sidecar only knows the settings' own server): with the writer's TLS, which
            # the template, on the sidecar's loopback, does not carry.
            host, port = _writer(cluster)
            default_options = connections.settings[DEFAULT_DB_ALIAS]["OPTIONS"]
            tls = {option: default_options[option] for option in TLS_OPTIONS if option in default_options}
            overrides |= {
                "HOST": host,
                "PORT": port,
                "OPTIONS": copy.deepcopy(connections.settings[TEMPLATE_ALIAS]["OPTIONS"]) | tls,
            }
    template = connections.settings[TEMPLATE_ALIAS]
    rotated = registered is not None and any(registered[key] != overrides.get(key, template[key]) for key in REACH_KEYS)
    _register(alias, lambda: _copied(TEMPLATE_ALIAS, **overrides), replace=rotated)
    _take_this_threads_role(alias)
    limits.configure(alias, hub)
    return alias


def _writer(cluster) -> tuple[str, int]:
    """Where the migrator reaches a database directly: the cluster's writer, or the default connection's server."""
    if cluster is not None:
        return cluster.host, cluster.port
    default = connections.settings[DEFAULT_DB_ALIAS]
    return default["HOST"], default["PORT"]


def migrator_conninfo(dbname: str, *, cluster=None) -> dict:
    """The migrator's direct connection to ``dbname`` (on ``cluster``, or the settings' own server) in libpq's terms
    (``psycopg.connect(**…)``): the default connection's TLS and timeout, the migrator's role, no pool."""
    default = connections.settings[DEFAULT_DB_ALIAS]
    found = credentials_for(cluster, MIGRATOR)
    host, port = _writer(cluster)
    options = {key: value for key, value in default["OPTIONS"].items() if key not in NON_LIBPQ_OPTIONS}
    return {
        **options,
        "dbname": dbname,
        "host": host,
        "port": port,
        "user": found.user,
        "password": found.password,
    }


def register_ddl_alias(db_name: str, *, cluster=None) -> str:
    """The migrator's alias of the database ``db_name`` (``<db_name>__ddl``) on ``cluster`` (or the settings' own
    server): direct, as the migrator's role, no pool, closed after use. Registered again when that role's user or
    password changed (a rotation of the cluster's ``…/migrator`` secret), or its writer (a move)."""
    names.validate(db_name, control=control_name())
    found = credentials_for(cluster, MIGRATOR)

    def build() -> dict:
        host, port = _writer(cluster)
        settings = _copied(
            DEFAULT_DB_ALIAS,
            NAME=db_name,
            HOST=host,
            PORT=port,
            USER=found.user,
            PASSWORD=found.password,
            CONN_MAX_AGE=0,
            DISABLE_SERVER_SIDE_CURSORS=True,
        )
        settings["OPTIONS"].pop("pool", None)
        return settings

    name = f"{db_name}{names.DDL_SUFFIX}"
    registered = connections.settings.get(name)
    reach = (*_writer(cluster), found.user, found.password)
    rotated = registered is not None and tuple(registered[key] for key in REACH_KEYS) != reach
    alias = _register(name, build, replace=rotated)
    # A connection object this thread kept from an earlier registration (forgotten since) reaches as that one's role.
    _take_this_threads_role(alias)
    return alias


def close_hub_aliases(hub) -> None:
    """Close this thread's connections to ``hub``'s database (its alias and its migrator's), if it opened any: what a
    hub's preparation does when it ends, so a pass over many hubs never holds one open per hub."""
    wanted = {hub_alias(hub), f"{hub.db_name}{names.DDL_SUFFIX}"}
    for connection in connections.all(initialized_only=True):
        if connection.alias in wanted:
            connection.close()


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


def close_this_threads_connections() -> None:
    """Close every connection this thread opened, control's included (a pooled one goes back to its pool): what a
    thread of the worker does when its piece ends (``base.worker.Background``, as ``migrate_hubs``' threads)."""
    connections.close_all()
