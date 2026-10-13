"""Database routers of hub-next.

``SharedRouter`` (round 16, PLAN §21; spec §3.3) goes first in ``DATABASE_ROUTERS``: the models of
the ``shared`` app (the mirror of the SaaS's ``shared`` schema) read and write only on the
``shared`` alias, and it answers ``None`` for every other model, so the next router (phase 2's
``TenantRouter``) or ``default`` decides. The Hub never migrates anything on that alias nor the
``shared`` app anywhere: the SaaS owns those tables. A model of another app sent to the alias by
hand (``.using("shared")`` skips the routers) is stopped by the ``hub_shared`` role, not here.
"""

SHARED_ALIAS = "shared"
SHARED_APP_LABEL = "shared"


def _is_shared(model_or_object) -> bool:
    return model_or_object._meta.app_label == SHARED_APP_LABEL


class SharedRouter:
    def db_for_read(self, model, **hints) -> str | None:
        return SHARED_ALIAS if _is_shared(model) else None

    def db_for_write(self, model, **hints) -> str | None:
        return SHARED_ALIAS if _is_shared(model) else None

    def allow_relation(self, obj1, obj2, **hints) -> bool | None:
        first, second = _is_shared(obj1), _is_shared(obj2)
        if first and second:
            return True
        return False if first or second else None

    def allow_migrate(
        self, db: str, app_label: str, model_name: str | None = None, **hints
    ) -> bool | None:
        if db == SHARED_ALIAS or app_label == SHARED_APP_LABEL:
            return False
        return None
