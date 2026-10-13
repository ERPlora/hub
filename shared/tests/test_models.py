"""The Hub's mirror of the ``shared`` schema of the SaaS's database (round 16, PLAN §21; spec §3.2).

The SaaS owns ``shared.app`` and ``shared.app_doc`` and migrates them; the Hub writes them through
these models, ``managed = False``, from ``base/catalog.py`` only. The columns come from
``live.shared_catalog`` (written once for both projects); what the mirror adds is pinned here: the
quoted tables, no migrations of its own and the unique constraint the SaaS's migration creates.
"""

from importlib.util import find_spec

from django.apps import apps
from django.db import models
from django.db.migrations.loader import MigrationLoader
from live.meta import LiveAppConfig
from live.shared_catalog import APP_DOC_TABLE, APP_TABLE, AbstractApp, AbstractAppDoc

from shared.models import App, AppDoc


def test_shared_is_a_platform_app_at_the_root_with_only_models():
    config = apps.get_app_config("shared")
    assert isinstance(config, LiveAppConfig)
    assert (config.name, config.label, config.kind) == ("shared", "shared", "platform")
    # No routes: the Hub never serves the catalog; base/catalog.py writes it.
    assert find_spec("shared.api") is None


def test_the_mirror_concretes_the_contract_of_live():
    assert issubclass(App, AbstractApp)
    assert issubclass(AppDoc, AbstractAppDoc)


def test_the_hub_never_creates_or_alters_the_tables():
    assert App._meta.managed is False
    assert AppDoc._meta.managed is False
    # No migrations module either: makemigrations has nothing to write for it.
    assert "shared" not in MigrationLoader(None, ignore_no_migrations=True).migrated_apps


def test_the_tables_name_their_schema_already_quoted():
    assert App._meta.db_table == APP_TABLE == '"shared"."app"'
    assert AppDoc._meta.db_table == APP_DOC_TABLE == '"shared"."app_doc"'


def test_a_document_points_at_the_mirror_s_own_app():
    field = AppDoc._meta.get_field("app")
    assert field.related_model is App
    assert field.remote_field.on_delete is models.PROTECT
    assert field.column == "app_id"


def test_the_unique_constraint_is_the_saas_s_one():
    # The SaaS's migration names it; the test database is built from this mirror (no migrations).
    [constraint] = AppDoc._meta.constraints
    assert isinstance(constraint, models.UniqueConstraint)
    assert (constraint.name, tuple(constraint.fields)) == ("shared_app_doc_app_lang_unique", ("app", "lang"))


def test_the_columns_are_the_saas_s_one_by_one():
    # Column, type and length of every field, as `\d shared.app` shows them in the SaaS's database.
    def columns(model):
        return [(f.column, f.get_internal_type(), getattr(f, "max_length", None), f.null) for f in model._meta.concrete_fields]

    assert columns(App) == [
        ("id", "CharField", 63, False),
        ("name_en", "CharField", 80, False),
        ("name_es", "CharField", 80, False),
        ("summary_en", "CharField", 120, False),
        ("summary_es", "CharField", 120, False),
        ("description_en", "TextField", None, False),
        ("description_es", "TextField", None, False),
        ("icon", "CharField", 100, False),
        ("icon_svg", "TextField", None, False),
        ("category", "CharField", 20, False),
        ("premium", "BooleanField", None, False),
        ("requires", "JSONField", None, False),
        ("verticals", "JSONField", None, False),
        ("listed", "BooleanField", None, False),
        ("hub_version", "CharField", 64, False),
        ("registered_at", "DateTimeField", None, False),
    ]
    assert columns(AppDoc) == [
        ("id", "UUIDField", 32, False),
        ("app_id", "ForeignKey", None, False),
        ("lang", "CharField", 8, False),
        ("markdown", "TextField", None, False),
        ("source_hash", "CharField", 64, False),
        ("updated_at", "DateTimeField", None, False),
    ]
