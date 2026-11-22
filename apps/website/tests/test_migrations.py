"""The website app's migrations.

0002: the two free colours of before become the custom palette.

A site's draft theme and the theme of its publication ``{primary, accent, mode}`` become ``{palette: "custom",
custom: {primary, accent}, mode}``, so every page keeps its colours; a theme already in the new shape and an empty one
are left alone. The reverse gives back the two colours (a curated palette's own, for a site that chose one) and turns
``auto`` into ``light``.

0003: «Your colours» stops being a palette of its own: any palette takes the owner's two colours over its own
(``custom``), so a custom palette becomes ``ocean`` with its colours (painted the same), and the colours a curated
palette kept for later go (they were not painted). The reverse turns a palette with the owner's colours back into the
custom palette. The functions of the ``RunPython`` are called the way the migrations run them.

0006: the business's database holds its one site, so the rows stop naming their business. The column stays in the
database for the code of before, which still runs while the deploy migrates; the rows copied in from another business
(nothing ever read them) go, and a second site is refused. Going back writes the business on the rows made after it.
These run on a business's own database, cloned from the template for each test, through the migrator's alias as
``migrate_hubs`` runs them.
"""

import io
import uuid
from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.core.management import call_command
from django.db import IntegrityError, connections, transaction
from django.db.migrations.executor import MigrationExecutor

from apps.website.models import Site
from apps.website.palettes import PALETTES
from apps.website.schemas import Theme
from apps.website.tests.conftest import HUB_DB
from base.models.identity import HubIdentity
from base.tenancy import connections as tenancy_connections
from base.tenancy import names
from base.tenancy.context import current_alias
from base.tenancy.tests import hubs

APP = "website"
BEFORE = [(APP, "0005_image_filename")]
AFTER = [(APP, "0006_one_site_per_database")]

migration = import_module("apps.website.migrations.0002_theme_palettes")
overrides = import_module("apps.website.migrations.0003_theme_overrides")
one_site = import_module("apps.website.migrations.0006_one_site_per_database")

OLD = {"primary": "#aa0000", "accent": "#112233", "mode": "dark"}
NEW = {"palette": "custom", "custom": {"primary": "#aa0000", "accent": "#112233"}, "mode": "dark"}


def site(theme: dict, published_theme: dict | None = None) -> Site:
    published = {} if published_theme is None else {"template": "modern", "theme": published_theme, "content": {}}
    return Site.objects.create(theme=theme, published_content=published)


def run(function) -> None:
    with connections[current_alias()].schema_editor() as editor:
        function(global_apps, editor)


def migrated(function, theme: dict, published_theme: dict | None = None) -> Site:
    """The business's site with ``theme`` after ``function`` ran on it; its row goes, so the next one fits."""
    row = site(theme, published_theme)
    run(function)
    row.refresh_from_db()
    row.delete()
    return row


@HUB_DB
def test_the_migrations_are_in_step_with_the_models():
    output = io.StringIO()
    call_command("makemigrations", APP, "--check", "--dry-run", stdout=output)
    assert "No changes detected" in output.getvalue()


@HUB_DB
def test_the_two_colours_become_the_custom_palette_in_the_draft_and_the_publication():
    old = site(OLD, {"primary": "#2563eb", "accent": "#f59e0b", "mode": "light"})
    run(migration.to_palettes)
    old.refresh_from_db()
    assert old.theme == NEW
    assert old.published_content["theme"] == {
        "palette": "custom",
        "custom": {"primary": "#2563eb", "accent": "#f59e0b"},
        "mode": "light",
    }
    assert old.published_content["template"] == "modern"
    # What it writes is, once 0003 has run, a valid theme of today with the same colours.
    run(overrides.to_overrides)
    old.refresh_from_db()
    assert Theme.model_validate(old.theme).custom.primary == "#aa0000"


@HUB_DB
def test_a_theme_already_moved_or_empty_and_a_site_never_published_are_left_alone():
    moved = migrated(migration.to_palettes, {"palette": "forest", "custom": None, "mode": "auto"})
    empty = migrated(migration.to_palettes, {})
    never = migrated(migration.to_palettes, OLD)
    assert moved.theme == {"palette": "forest", "custom": None, "mode": "auto"}
    assert empty.theme == {}
    assert never.theme == NEW and never.published_content == {}


@HUB_DB
def test_the_reverse_gives_back_two_colours_and_a_light_or_dark_page():
    custom = migrated(migration.to_colours, NEW, NEW)
    curated = migrated(migration.to_colours, {"palette": "forest", "custom": None, "mode": "auto"})
    assert custom.theme == OLD and custom.published_content["theme"] == OLD
    assert curated.theme == {"primary": PALETTES["forest"]["light"]["primary"], "accent": PALETTES["forest"]["accent"], "mode": "light"}


def test_the_migration_runs_its_python_both_ways():
    operation = migration.Migration.operations[0]
    assert operation.code is migration.to_palettes
    assert operation.reverse_code is migration.to_colours


TWEAK = {"primary": "#aa0000", "accent": "#112233"}


@HUB_DB
def test_the_custom_palette_becomes_ocean_with_the_owners_colours_and_kept_colours_go():
    to_overrides = overrides.to_overrides
    custom = migrated(to_overrides, {"palette": "custom", "custom": TWEAK, "mode": "dark"}, {"palette": "custom", "custom": TWEAK, "mode": "auto"})
    kept = migrated(to_overrides, {"palette": "forest", "custom": TWEAK, "mode": "auto"}, {"palette": "sand", "custom": TWEAK, "mode": "light"})
    plain = migrated(to_overrides, {"palette": "forest", "custom": None, "mode": "auto"})
    empty = migrated(to_overrides, {})
    assert custom.theme == {"palette": "ocean", "custom": TWEAK, "mode": "dark"}
    assert custom.published_content["theme"] == {"palette": "ocean", "custom": TWEAK, "mode": "auto"}
    assert custom.published_content["template"] == "modern"
    # Colours a curated palette only kept for later were never painted: they go, and the page stays as it was.
    assert kept.theme == {"palette": "forest", "custom": None, "mode": "auto"}
    assert kept.published_content["theme"] == {"palette": "sand", "custom": None, "mode": "light"}
    assert plain.theme == {"palette": "forest", "custom": None, "mode": "auto"} and plain.published_content == {}
    assert empty.theme == {}
    for row in (custom, kept, plain):
        Theme.model_validate(row.theme)


@HUB_DB
def test_the_reverse_turns_the_owners_colours_back_into_the_custom_palette():
    to_custom = overrides.to_custom_palette
    tweaked = migrated(to_custom, {"palette": "forest", "custom": TWEAK, "mode": "auto"}, {"palette": "forest", "custom": TWEAK, "mode": "dark"})
    plain = migrated(to_custom, {"palette": "forest", "custom": None, "mode": "auto"})
    assert tweaked.theme == {"palette": "custom", "custom": TWEAK, "mode": "auto"}
    assert tweaked.published_content["theme"] == {"palette": "custom", "custom": TWEAK, "mode": "dark"}
    assert plain.theme == {"palette": "forest", "custom": None, "mode": "auto"}


def test_migration_0003_runs_its_python_both_ways():
    operation = overrides.Migration.operations[0]
    assert overrides.Migration.dependencies == [("website", "0002_theme_palettes")]
    assert operation.code is overrides.to_overrides
    assert operation.reverse_code is overrides.to_custom_palette


# 0006: one site per database


@pytest.fixture
def database(hub_databases, django_db_blocker):
    """The migrator's connection to a business's database cloned from the template for the test, dropped after it. No
    test case around it: one refuses the migrator's alias (``…__ddl``), which is not among its databases."""
    name = names.hub_db_name(hub_databases.control, uuid.uuid7())
    with django_db_blocker.unblock(), hubs.clone_of_the_template(hub_databases, name):
        database = connections[tenancy_connections.register_ddl_alias(name)]
        try:
            yield database
        finally:
            database.close()


def migrate(database, targets):
    executor = MigrationExecutor(database)
    executor.loader.build_graph()
    executor.migrate(targets)
    return MigrationExecutor(database).loader.project_state(targets).apps


def columns(database, table: str) -> set[str]:
    with database.cursor() as cursor:
        return {column.name for column in database.introspection.get_table_description(cursor, table)}


def image(model, alias: str, business: uuid.UUID | None = None):
    fields = {"hub_id": business} if business else {}
    return model.objects.using(alias).create(
        key=f"hub-{uuid.uuid7().hex}/website/img/{uuid.uuid7().hex[:16]}.png",
        sha256="a" * 64,
        content_type="image/png",
        width=1,
        height=1,
        size=1,
        **fields,
    )


def test_the_rows_of_another_business_go_and_the_business_keeps_its_own(database):
    alias = database.alias
    old = migrate(database, BEFORE)
    own, other = uuid.uuid7(), uuid.uuid7()
    HubIdentity.objects.using(alias).create(hub_id=own)
    OldSite, OldImage = old.get_model(APP, "Site"), old.get_model(APP, "Image")
    mine = OldSite.objects.using(alias).create(hub_id=own, template="bold")
    OldSite.objects.using(alias).create(hub_id=other, template="modern")
    my_image, _theirs = image(OldImage, alias, own), image(OldImage, alias, other)

    new = migrate(database, AFTER)
    NewSite, NewImage = new.get_model(APP, "Site"), new.get_model(APP, "Image")
    assert list(NewSite.objects.using(alias).values_list("id", "template")) == [(mine.id, "bold")]
    assert list(NewImage.objects.using(alias).values_list("id", flat=True)) == [my_image.id]
    for model, table in ((NewSite, "website_site"), (NewImage, "website_image")):
        assert "hub_id" not in {field.name for field in model._meta.get_fields()}
        # The column is never dropped: the code of before still reads and writes it during the deploy.
        assert "hub_id" in columns(database, table)


def test_a_second_site_is_refused_and_rows_made_now_need_no_business(database):
    alias = database.alias
    new = migrate(database, AFTER)
    NewSite = new.get_model(APP, "Site")
    NewSite.objects.using(alias).create()
    image(new.get_model(APP, "Image"), alias)
    with pytest.raises(IntegrityError), transaction.atomic(using=alias):
        NewSite.objects.using(alias).create()


def test_a_database_that_names_no_business_keeps_its_rows(database):
    alias = database.alias
    old = migrate(database, BEFORE)
    kept = old.get_model(APP, "Site").objects.using(alias).create(hub_id=uuid.uuid7())
    new = migrate(database, AFTER)
    assert list(new.get_model(APP, "Site").objects.using(alias).values_list("id", flat=True)) == [kept.id]


def test_going_back_writes_the_business_on_the_rows_made_after(database):
    alias = database.alias
    new = migrate(database, AFTER)
    own = uuid.uuid7()
    HubIdentity.objects.using(alias).create(hub_id=own)
    made = new.get_model(APP, "Site").objects.using(alias).create(template="minimal")
    uploaded = image(new.get_model(APP, "Image"), alias)

    old = migrate(database, BEFORE)
    assert old.get_model(APP, "Site").objects.using(alias).get(id=made.id).hub_id == own
    assert old.get_model(APP, "Image").objects.using(alias).get(id=uploaded.id).hub_id == own
    # And the code of before finds its row again, as it always did.
    assert old.get_model(APP, "Site").objects.using(alias).filter(hub_id=own).count() == 1


def test_migration_0006_runs_its_python_both_ways_after_base_knows_the_business():
    assert ("base", "0007_registry_moves_to_control") in one_site.Migration.dependencies
    [step] = [op for op in one_site.Migration.operations if op.__class__.__name__ == "RunPython"]
    assert step.code is one_site.drop_rows_of_other_businesses
    assert step.reverse_code is one_site.name_the_business_again


# 0002 and 0003 ran while several businesses shared the table


FOREST = {"palette": "forest", "custom": None, "mode": "auto"}


@pytest.mark.parametrize(
    ("function", "theme", "expected"),
    [
        (migration.to_palettes, OLD, NEW),
        (overrides.to_overrides, {"palette": "custom", "custom": TWEAK, "mode": "dark"}, {"palette": "ocean", "custom": TWEAK, "mode": "dark"}),
    ],
)
def test_a_site_is_never_written_with_the_theme_of_another_row(database, function, theme, expected):
    alias = database.alias
    old = migrate(database, BEFORE)
    OldSite = old.get_model(APP, "Site")
    changed = OldSite.objects.using(alias).create(hub_id=uuid.uuid7(), theme=theme)
    untouched = OldSite.objects.using(alias).create(hub_id=uuid.uuid7(), theme=FOREST)
    with database.schema_editor() as editor:
        function(old, editor)
    assert dict(OldSite.objects.using(alias).values_list("id", "theme")) == {changed.id: expected, untouched.id: FOREST}
