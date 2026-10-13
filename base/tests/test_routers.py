"""SharedRouter: the models of ``shared`` live on the ``shared`` alias, and nothing else does (round 16).

PLAN §21 and spec §3.3: the Hub's mirror of the SaaS's ``shared`` schema reads and writes only on the
``shared`` alias; every other model is left to the next router (phase 2's ``TenantRouter``) or to
``default``; nothing relates across the two; and the Hub never migrates anything there, nor the
``shared`` app anywhere, also in the tests.
"""

import re

import pytest
from django.contrib.auth import get_user_model
from django.db import connections

from base.catalog import register_apps
from base.models import Membership
from base.routers import SharedRouter
from shared.models import App, AppDoc

router = SharedRouter()


@pytest.mark.parametrize("model", [App, AppDoc])
def test_a_model_of_shared_reads_and_writes_on_the_shared_alias(model):
    assert router.db_for_read(model) == "shared"
    assert router.db_for_write(model) == "shared"


@pytest.mark.parametrize("model", [Membership, get_user_model()])
def test_any_other_model_is_left_to_the_next_router(model):
    assert router.db_for_read(model) is None
    assert router.db_for_write(model) is None


def test_nothing_relates_a_model_of_shared_with_another_one():
    app, membership = App(id="demo"), Membership()
    assert router.allow_relation(app, membership) is False
    assert router.allow_relation(membership, app) is False
    assert router.allow_relation(AppDoc(app=app), app) is True
    assert router.allow_relation(membership, get_user_model()()) is None


@pytest.mark.parametrize("app_label", ["shared", "base", "auth", "demo", "contenttypes"])
def test_nothing_migrates_on_the_shared_alias(app_label):
    assert router.allow_migrate("shared", app_label) is False


@pytest.mark.parametrize("alias", ["default", "shared", "hub_0190a1b2c3d4"])
def test_the_shared_app_never_migrates(alias):
    assert router.allow_migrate(alias, "shared", model_name="app") is False


def test_other_apps_migrate_where_the_next_router_says():
    assert router.allow_migrate("default", "base") is None


#: What register_apps may send to the `shared` alias: its two tables, its transaction lock, the
#: check of the mirror's columns and the savepoints of its transaction.
ALLOWED_SHARED_SQL = re.compile(
    r'"shared"\."(?:app|app_doc)"|pg_advisory_xact_lock|information_schema\.columns|^(?:RELEASE |ROLLBACK TO )?SAVEPOINT '
)


@pytest.mark.django_db(databases=["default", "shared"])
@pytest.mark.usefixtures("shared_schema")
def test_register_apps_only_reaches_the_shared_tables_and_its_lock(settings):
    settings.APP_VERSION, settings.APP_RELEASED_AT = "4da2a10", "2026-10-13T20:50:00+02:00"
    sent: dict[str, list[str]] = {"shared": [], "default": []}

    def recorder(alias):
        def record(execute, sql, params, many, context):
            sent[alias].append(sql)
            return execute(sql, params, many, context)

        return record

    with connections["shared"].execute_wrapper(recorder("shared")), connections["default"].execute_wrapper(recorder("default")):
        register_apps()

    assert [sql for sql in sent["shared"] if not ALLOWED_SHARED_SQL.search(sql)] == []
    assert any("pg_advisory_xact_lock" in sql for sql in sent["shared"])
    assert any('INSERT INTO "shared"."app"' in sql for sql in sent["shared"])
    # The Hub's own database is not touched: nothing of the registry goes anywhere else.
    assert sent["default"] == []
