"""``TenantRouter``: control's models to ``default``, a hub's to its hub's alias (PLAN-DB §4; plan 2026-10-22, step 5).

Second in ``DATABASE_ROUTERS``, after ``base.routers.SharedRouter`` (the SaaS's ``shared`` schema). It reads the
database class of each model from ``base.tenancy.inventory`` and the active context from ``base.tenancy.context``:

- ``control`` → ``default``, always;
- ``hub`` → the alias of the active ``use_hub`` (or ``default`` in phase 1's shared database); without a context, or
  in control's, ``HubContextMissing``: never a guess;
- ``contextual`` (the outbox) → the alias of the active context, control's included.

A hub's object related to one already loaded (``instance`` hint) goes where that one is, as Django's own default does.

``allow_relation`` compares databases, not aliases (``hub_x`` and ``hub_x__ddl`` are one database). ``allow_migrate``:
control's models only on ``default``; a hub's only on a migrator's ``…__ddl`` alias and, while phase 1's hubs keep
their data in control's database (S1–S4, plan decision 1), on ``default`` too; S5 takes ``default`` out of that rule
with the shared database.
"""

from django.db import DEFAULT_DB_ALIAS, connections

from base.tenancy import context, inventory, names

#: Phase 1's shared database (S1–S4): control's, where every hub with ``db_name=""`` still has its tables.
SHARED_DATABASE_ALIAS = DEFAULT_DB_ALIAS


def _route(model, hints: dict) -> str | None:
    database_class = inventory.classify(model)
    if database_class == inventory.CONTROL:
        return DEFAULT_DB_ALIAS
    if database_class == inventory.SHARED:
        return None
    related = hints.get("instance")
    if related is not None and related._state.db is not None:
        # An object related to one already loaded lives in that one's database (a migration's RunPython on a
        # hub's __ddl alias, an object of the hub being served): Django's own rule.
        return related._state.db
    active = context.current()
    if database_class == inventory.HUB and active.kind == context.CONTROL:
        raise context.HubContextMissing(
            f"{model._meta.label} is a hub's model: run it inside use_hub(hub), not on control."
        )
    return active.alias


def _database(alias: str) -> str | None:
    settings = connections.settings.get(alias)
    return None if settings is None else settings["NAME"]


class TenantRouter:
    def db_for_read(self, model, **hints) -> str | None:
        return _route(model, hints)

    def db_for_write(self, model, **hints) -> str | None:
        return _route(model, hints)

    def allow_relation(self, obj1, obj2, **hints) -> bool | None:
        first, second = obj1._state.db, obj2._state.db
        if first is None or second is None:
            return None
        return first == second or _database(first) == _database(second)

    def allow_migrate(self, db: str, app_label: str, model_name: str | None = None, **hints) -> bool | None:
        if model_name is None:
            database_class = inventory.APP_CLASSES.get(app_label) or inventory.classify_label(app_label, "")
        else:
            database_class = inventory.classify_label(app_label, model_name)
        if database_class == inventory.SHARED:
            return None
        if database_class == inventory.CONTROL:
            return db == DEFAULT_DB_ALIAS
        return db == SHARED_DATABASE_ALIAS or db.endswith(names.DDL_SUFFIX)
