"""The Hub's schema migrator.

``manage.py migrate_hubs`` (the ``hub-migrate`` task of every deploy) runs it, in this order:

1. the control database (``default``), under a session advisory lock, so two overlapping deploys never migrate it at
   once (the second waits, then finds nothing to apply): ``migrate_control``;
2. the templates, as canaries, on every server the hubs live on (``clusters_to_migrate``: ``CREATE DATABASE …
   TEMPLATE`` clones only within one): ``<control>_template``, the platform alone, and one
   ``<control>_template_<vertical>`` per vertical of ``base.catalog``, cloned from it, with the tables of that
   vertical's apps and every app off (``templates``, ``ensure_template``).
   One missing is created; one whose list changed is brought up to date, never rebuilt;
3. every hub with a database of its own that is behind the code (``is_behind``, from ``Hub.schema_apps``: a deploy
   without migrations opens none), each on its own server, ERPlora's own first, then at most ``HUB_WORKERS`` at once:
   ``migrate_hubs_behind``.

``ensure_schema(hub, add=())`` is the only function that changes a hub's schema: through the hub's direct
``<db_name>__ddl`` alias, under the schema lock of that database (``pg_try_advisory_lock(hashtext('erplora.schema'))``:
the key lives in each database, so it is per hub), it brings the platform (``base``, ``live``), the apps the hub's
database already has and ``add`` (closed by ``requires``) to the code's leaf with ``migrate_apps``, then writes down in
control what that database has (``Hub.schema_apps``: its ``django_migrations`` rules) and ``schema_state = current``,
on a row that names it (a cut names it in its last step, which records it then), and forgets what any process kept
of it (``base.activation.forget``). It never steps back and never deletes a table.
``pending_control``, ``pending_template`` and ``is_behind`` are ``migrate_hubs --check``: what a run would apply, applying
nothing.

The only package of ``base/`` and ``apps/`` that names a connection by hand and takes session advisory locks
(``tests/test_guardrails.py``): the control database and the hubs' ``__ddl`` aliases are reached directly, never through
PgBouncer, so a session lock holds for as long as its function runs. ``CREATE DATABASE`` (a missing template) goes
through a direct autocommit connection to that server's ``postgres`` database, a database's name only as
``sql.Identifier`` (``base.tenancy.names``). On a hub's or a template's server the migrator connects with its own
credentials (``migrator_credentials``: ``hub_migrator``'s in the ``hub-migrate`` task and the worker).

Each part lives in a module of its own, imported here: ``control_database``, ``hub_templates`` and ``hubs_pass`` (the
three steps of ``migrate_hubs``), ``schema`` (``ensure_schema``), ``servers`` (where the migrator connects, and as whom)
and ``app_sets`` (which apps a hub's database holds).
"""

from . import (
    app_sets as app_sets,
    control_database as control_database,
    hub_templates as hub_templates,
    hubs_pass as hubs_pass,
    schema as schema,
    servers as servers,
)
