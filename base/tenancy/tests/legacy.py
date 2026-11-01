"""The suite's tests written before the tenancy: where they keep their businesses' rows without a context of their own.

Production has no such place: since S5 every business has its own database, and a hub's model or operation without
``use_hub`` fails (``HubContextMissing``); a business without one is never entered (``HubWithoutDatabase``). The tests
of phase 1 call operations and the ORM directly, for the local hubs ``a`` and ``b`` and the businesses they make
(``db_name=""``), so the session keeps a place for them: control's test database also holds the tables of the hubs'
apps (:class:`LegacyTablesRouter`, in ``config/settings_pytest.py`` only), and :data:`LEGACY` is the fallback the root
``conftest.py`` sets (``context._test_fallback``), under which such a business is entered there. The tests of the
tenancy turn it off (``no_test_fallback``) and run as production does; the tests of the cut write with
:func:`use_legacy` what phase 1 left in control's tables.
"""

from django.db import DEFAULT_DB_ALIAS

from base.tenancy import context, inventory

#: The fallback of the suite's tests written before the tenancy: control's test database, every business's rows in it.
LEGACY = context.DatabaseContext(kind="legacy", alias=DEFAULT_DB_ALIAS)


def use_legacy():
    """Work on control's test database as phase 1 did, every business's rows in it, until the block ends."""
    return context._entered(LEGACY)


class LegacyTablesRouter:
    """First of the tests' ``DATABASE_ROUTERS``: control's test database gets the tables of the hubs' apps too, for the
    suite's tests written before the tenancy. Says nothing of anything else (the ``TenantRouter`` decides)."""

    def allow_migrate(self, db: str, app_label: str, model_name: str | None = None, **hints) -> bool | None:
        if db != DEFAULT_DB_ALIAS:
            return None
        if model_name is None:
            database_class = inventory.APP_CLASSES.get(app_label) or inventory.classify_label(app_label, "")
        else:
            database_class = inventory.classify_label(app_label, model_name)
        return True if database_class == inventory.HUB else None
