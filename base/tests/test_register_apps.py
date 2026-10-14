"""register_apps: the Hub writes its modules into the SaaS's ``shared`` schema (round 16, PLAN §21; spec §4.2).

One transaction on the ``shared`` alias: the advisory lock, the tables and the columns of the mirror
checked against the database, then the upsert of ``shared.app``, the retired apps unlisted (never deleted) and the
documents that changed. A newer release is never overwritten unless ``--force``; anything that fails
leaves nothing written. ``--check`` stops after ``build_registry``, without opening a connection.
Tables the SaaS has not created yet (``SharedSchemaNotReady``) are not a contract error: the worker
waits for them (``test_worker.py``); a missing column is.

The writing tests run against ``test_hub_next_shared``, where ``shared_schema`` builds the schema
from the mirror. The others carry no database mark on purpose: pytest-django refuses any connection
there, on every alias, so they prove that what they check happens before the database is touched.
"""

import logging
import uuid
from datetime import datetime, timedelta

import pytest
from django.core.management import CommandError, call_command
from django.db import connections

from base import catalog
from base.catalog import (
    CatalogError,
    RegistryError,
    SharedSchemaNotReady,
    build_registry,
    register_apps,
    source_hash,
)
from base.tests.test_catalog import ICONS, USER_PART, WORKBOOK, module, translated
from shared.models import App, AppDoc

RELEASE = {"APP_VERSION": "4da2a10", "APP_RELEASED_AT": "2026-10-13T20:50:00+02:00"}
RELEASED_AT = datetime.fromisoformat(RELEASE["APP_RELEASED_AT"])
EN_BODY = "## What it is for\n\nKeeps **things**.\n"
SHARED_DB = [pytest.mark.django_db(databases=["default", "shared"]), pytest.mark.usefixtures("shared_schema")]


@pytest.fixture(autouse=True)
def release(settings):
    """A production release, as the image fixes it."""
    settings.DEBUG = False
    settings.APP_VERSION = RELEASE["APP_VERSION"]
    settings.APP_RELEASED_AT = RELEASE["APP_RELEASED_AT"]
    return settings


@pytest.fixture
def modules(tmp_path):
    """Two modules on disk: ``things`` translated, ``stock`` premium and only in Spanish."""
    return [
        module(tmp_path, "things", en=translated(USER_PART, EN_BODY), verticals=["restaurant"]),
        module(tmp_path, "stock", premium=True, requires=["things"]),
    ]


def registry(configs):
    return build_registry(configs, icons=ICONS)


def rewritten(tmp_path, sentence: str, **fields):
    """``things`` again, its WORKBOOK saying ``sentence`` and without its English translation."""
    return module(tmp_path / "next", "things", workbook=WORKBOOK.replace("Guarda **cosas**.", sentence), **fields)


def rows():
    """Every row of both tables, every column: what a second run must leave identical."""
    apps = list(App.objects.order_by("id").values())
    docs = list(AppDoc.objects.order_by("app_id", "lang").values())
    return apps, docs


def broken_registry(*args, **kwargs):
    raise RegistryError(["things: icon: 'lucide:box' is not baked"])


class TestWrite:
    pytestmark = SHARED_DB

    def test_the_first_registration_writes_every_module_and_its_documents(self, modules):
        result = register_apps(registry(modules))

        assert (result.written, result.retired, result.docs_changed, result.skipped) == (2, 0, 3, False)
        things = App.objects.get(id="things")
        assert (things.name_en, things.name_es, things.summary_es) == ("Things", "Cosas", "Guarda tus cosas.")
        assert (things.icon, things.icon_svg, things.category) == ("ion:cube-outline", ICONS["ion:cube-outline"], "catalog")
        assert (things.premium, things.requires, things.verticals, things.listed) == (False, [], ["restaurant"], True)
        assert (things.hub_version, things.registered_at) == ("4da2a10", RELEASED_AT)
        stock = App.objects.get(id="stock")
        assert (stock.premium, stock.requires, stock.verticals) == (True, ["things"], [])
        docs = {(doc.app_id, doc.lang): doc for doc in AppDoc.objects.all()}
        assert set(docs) == {("things", "es"), ("things", "en"), ("stock", "es")}
        assert docs["things", "es"].markdown == USER_PART
        assert (docs["things", "en"].markdown, docs["things", "en"].source_hash) == (EN_BODY, source_hash(EN_BODY))
        assert docs["things", "es"].id.version == 7

    def test_the_same_release_twice_changes_nothing(self, modules):
        register_apps(registry(modules))
        before = rows()

        result = register_apps(registry(modules))

        assert rows() == before
        assert (result.written, result.retired, result.docs_changed, result.skipped) == (2, 0, 0, False)

    def test_a_changed_document_changes_its_hash_and_its_time_and_nothing_else(self, tmp_path, modules):
        register_apps(registry(modules))
        before = {(doc.app_id, doc.lang): doc for doc in AppDoc.objects.all()}
        changed = rewritten(tmp_path, "Guarda **objetos**.", en=translated(USER_PART.replace("**cosas**", "**objetos**"), EN_BODY))

        result = register_apps(registry([changed, modules[1]]))

        after = {(doc.app_id, doc.lang): doc for doc in AppDoc.objects.all()}
        assert result.docs_changed == 1
        assert after["things", "es"].source_hash == source_hash(USER_PART.replace("**cosas**", "**objetos**"))
        assert after["things", "es"].updated_at > before["things", "es"].updated_at
        for unchanged in (("things", "en"), ("stock", "es")):
            assert after[unchanged].updated_at == before[unchanged].updated_at

    def test_a_newer_release_already_registered_is_not_overwritten(self, modules, caplog):
        register_apps(registry(modules))
        App.objects.filter(id="things").update(registered_at=RELEASED_AT + timedelta(hours=1), name_en="Newer")
        before = rows()

        with caplog.at_level(logging.INFO, logger="base.catalog"):
            result = register_apps(registry(modules[:1]))

        assert result.skipped is True
        assert rows() == before
        assert "newer release" in caplog.text

    def test_the_command_exits_zero_when_a_newer_release_registered(self, modules, monkeypatch):
        register_apps(registry(modules))
        App.objects.filter(id="things").update(registered_at=RELEASED_AT + timedelta(hours=1))
        monkeypatch.setattr(catalog, "build_registry", lambda *args, **kwargs: registry(modules))

        call_command("register_apps")  # no CommandError: exit code 0

        assert App.objects.get(id="things").registered_at == RELEASED_AT + timedelta(hours=1)

    def test_force_writes_over_a_newer_release(self, modules):
        register_apps(registry(modules))
        App.objects.filter(id="things").update(registered_at=RELEASED_AT + timedelta(hours=1), name_en="Newer")

        result = register_apps(registry(modules), force=True)

        assert result.skipped is False
        things = App.objects.get(id="things")
        assert (things.name_en, things.registered_at) == ("Things", RELEASED_AT)

    def test_a_retired_app_is_unlisted_and_keeps_its_row_and_documents(self, modules, settings):
        register_apps(registry(modules))
        settings.APP_VERSION, settings.APP_RELEASED_AT = "5eb3c21", "2026-10-14T09:00:00+02:00"

        result = register_apps(registry(modules[:1]))

        assert result.retired == 1
        stock = App.objects.get(id="stock")
        assert (stock.listed, stock.hub_version) == (False, "5eb3c21")
        assert stock.registered_at == datetime.fromisoformat("2026-10-14T09:00:00+02:00")
        assert stock.name_es == "Cosas"
        assert AppDoc.objects.get(app_id="stock", lang="es").markdown == USER_PART

    def test_a_retired_translation_is_left_empty_never_deleted(self, tmp_path, modules):
        register_apps(registry(modules))
        untranslated = module(tmp_path / "next", "things", verticals=["restaurant"])

        result = register_apps(registry([untranslated, modules[1]]))

        assert result.docs_changed == 1
        en = AppDoc.objects.get(app_id="things", lang="en")
        assert (en.markdown, en.source_hash) == ("", source_hash(""))

    def test_a_failure_halfway_leaves_nothing_written(self, modules, monkeypatch, caplog):
        def broken(*args, **kwargs):
            raise CatalogError("the documents could not be written")

        monkeypatch.setattr(catalog, "_write_documents", broken)

        with caplog.at_level(logging.ERROR, logger="base.catalog"), pytest.raises(CatalogError):
            register_apps(registry(modules))

        assert not App.objects.exists() and not AppDoc.objects.exists()
        assert "the documents could not be written" in caplog.text

    def test_a_column_the_saas_has_not_migrated_yet_fails_naming_it_and_writes_nothing(self, modules):
        with connections["shared"].cursor() as cursor:
            cursor.execute('ALTER TABLE "shared"."app" DROP COLUMN "verticals"')

        with pytest.raises(CatalogError, match=r"shared\.app\.verticals.*migrate the SaaS first") as raised:
            register_apps(registry(modules))

        # A contract gap (spec §3.5), not a schema still to come: the worker does not wait for it.
        assert not isinstance(raised.value, SharedSchemaNotReady)
        with connections["shared"].cursor() as cursor:
            cursor.execute('SELECT count(*) FROM "shared"."app"')
            assert cursor.fetchone() == (0,)

    @pytest.mark.parametrize(
        ("missing", "tables"),
        [
            ('DROP TABLE "shared"."app_doc"', ["shared.app_doc"]),
            # Its foreign key from app_doc goes with it; app_doc stays.
            ('DROP TABLE "shared"."app" CASCADE', ["shared.app"]),
            ('DROP SCHEMA "shared" CASCADE', ["shared.app", "shared.app_doc"]),
        ],
        ids=["app_doc", "app", "schema"],
    )
    def test_tables_the_saas_has_not_created_yet_are_not_ready_not_a_contract_error(
        self, modules, caplog, missing, tables
    ):
        # The first deploy: the Hub's worker starts before saas-migrate creates the schema.
        with connections["shared"].cursor() as cursor:
            cursor.execute(missing)

        with caplog.at_level(logging.INFO, logger="base.catalog"), pytest.raises(
            SharedSchemaNotReady, match="not migrated the shared schema yet"
        ) as raised:
            register_apps(registry(modules))

        assert raised.value.tables == tables
        # The caller says how loud it is (the worker waits and warns): no error logged per attempt.
        assert not [record for record in caplog.records if record.levelno >= logging.ERROR]

    @pytest.mark.parametrize(
        ("grants", "lacking"),
        [
            ([], "USAGE on schema shared; SELECT, INSERT, UPDATE on shared.app; SELECT, INSERT, UPDATE on shared.app_doc"),
            (
                ["GRANT USAGE ON SCHEMA shared TO {role}", 'GRANT SELECT ON "shared"."app", "shared"."app_doc" TO {role}'],
                "INSERT, UPDATE on shared.app; INSERT, UPDATE on shared.app_doc",
            ),
            (
                ["GRANT USAGE ON SCHEMA shared TO {role}", 'GRANT SELECT, INSERT, UPDATE ON "shared"."app" TO {role}'],
                "SELECT, INSERT, UPDATE on shared.app_doc",
            ),
        ],
        ids=["nothing", "read-only", "app-only"],
    )
    def test_tables_the_role_may_not_write_fail_naming_the_grants_not_a_column(
        self, modules, caplog, grants, lacking
    ):
        # bootstrap_databases not run (or not again): the tables exist, hub_shared has no grant on them.
        # A real role, created and assumed inside the test's transaction, which undoes both.
        role = f"test_hub_shared_{uuid.uuid4().hex[:8]}"
        with connections["shared"].cursor() as cursor:
            cursor.execute(f'CREATE ROLE "{role}" NOLOGIN')
            for grant in grants:
                cursor.execute(grant.format(role=f'"{role}"'))
            cursor.execute(f'SET LOCAL ROLE "{role}"')

        with caplog.at_level(logging.ERROR, logger="base.catalog"), pytest.raises(CatalogError) as raised:
            register_apps(registry(modules))

        message = str(raised.value)
        assert f"role {role} lacks {lacking}: run bootstrap_databases" in message
        assert "no column" not in message
        # Fatal, never waited for: a grant does not come by itself.
        assert not isinstance(raised.value, SharedSchemaNotReady)
        assert f"role {role} lacks" in caplog.text

    def test_a_column_the_saas_has_added_already_is_no_error(self, modules):
        with connections["shared"].cursor() as cursor:
            cursor.execute("""ALTER TABLE "shared"."app" ADD COLUMN "rating" integer NOT NULL DEFAULT 0""")

        assert register_apps(registry(modules)).written == 2

    def test_locally_the_release_is_dev_written_now(self, modules, settings):
        settings.DEBUG, settings.APP_VERSION, settings.APP_RELEASED_AT = True, "", ""
        before = datetime.now().astimezone()

        register_apps(registry(modules))

        things = App.objects.get(id="things")
        assert things.hub_version == "dev"
        assert things.registered_at >= before

    def test_the_command_registers_the_real_modules(self, capsys):
        call_command("register_apps")

        demo = App.objects.get(id="demo")
        assert (demo.name_en, demo.listed, demo.hub_version) == ("Demo", False, "4da2a10")
        assert set(AppDoc.objects.filter(app_id="demo").values_list("lang", flat=True)) == {"es", "en"}
        assert "demo" in capsys.readouterr().out


# ── Before any connection: no database mark ────────────────────────────────────────────────────


def test_check_validates_the_real_modules_without_opening_any_connection(capsys):
    call_command("register_apps", "--check")
    assert "demo" in capsys.readouterr().out


def test_check_fails_with_every_problem(monkeypatch):
    monkeypatch.setattr(catalog, "build_registry", broken_registry)
    with pytest.raises(CommandError, match="lucide:box"):
        call_command("register_apps", "--check")


def test_an_invalid_registry_fails_before_any_connection(monkeypatch, caplog):
    monkeypatch.setattr(catalog, "build_registry", broken_registry)
    with caplog.at_level(logging.ERROR, logger="base.catalog"), pytest.raises(RegistryError):
        register_apps()
    assert "lucide:box" in caplog.text


def test_without_the_shared_alias_it_fails_saying_so(modules, settings, monkeypatch):
    # The web service, or a task without SHARED_DB_USER.
    monkeypatch.delitem(settings.DATABASES, "shared")
    with pytest.raises(CatalogError, match="SHARED_DB_USER"):
        register_apps(registry(modules))


@pytest.mark.parametrize("missing", ["APP_VERSION", "APP_RELEASED_AT"])
def test_production_without_the_release_fails(modules, settings, missing):
    setattr(settings, missing, "")
    with pytest.raises(CatalogError, match=missing):
        register_apps(registry(modules))


def test_a_release_time_without_its_offset_fails(modules, settings):
    settings.APP_RELEASED_AT = "2026-10-13T20:50:00"
    with pytest.raises(CatalogError, match="offset"):
        register_apps(registry(modules))


def test_the_command_fails_with_a_non_zero_exit_and_the_reason(settings):
    settings.APP_VERSION = ""
    with pytest.raises(CommandError, match="APP_VERSION"):
        call_command("register_apps")


def test_the_command_forces_only_when_asked(monkeypatch):
    calls = []

    def recorded(**kwargs):
        calls.append(kwargs)
        return catalog.RegisterResult(written=0, retired=0, docs_changed=0, skipped=False)

    monkeypatch.setattr(catalog, "register_apps", recorded)
    call_command("register_apps")
    call_command("register_apps", "--force")
    assert calls == [{"force": False}, {"force": True}]
