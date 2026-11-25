"""base.help.get: the help of an app whose help is ready, a module's or the Hub's own screens', read from its WORKBOOK in
the person's language, or in the source's while that language has no current file.

A stand-in for Tables is the module with its help ready: its name and menu are the real ones, and its WORKBOOK is the
made-up one of ``help_workbooks`` (floor plan, zones and the settings Tables shows as its fifth tab).
"""

from collections import Counter

import pytest
from django.apps import apps
from live.assistant import is_tool
from live.context import OperationContext
from live.errors import NotFound
from live.meta import Help, all_live_app_configs
from live.operations import AI, get

from base import workbook_help
from base.queries import app_help
from base.schemas.app_help import AppHelpIn
from base.tenancy.tests.business import HUB_DB, A, in_business_a
from base.tests.help_workbooks import EN, ready_platform, ready_tables, write_workbooks

__all__ = ["in_business_a"]

pytestmark = HUB_DB

VIDEO_ES, VIDEO_EN = "dQw4w9WgXcQ", "M7lc1UVf-VE"


def ask(app: str = "table", language: str = "es", *also: str) -> dict:
    """The help of ``app`` for a person who sees the Home and ``also`` holds those permissions."""
    op = get("base.help.get")
    ctx = OperationContext(scope=A, actor="ana", permissions=frozenset({"base.view_home", *also}), language=language)
    return op(ctx, AppHelpIn(app=app)).model_dump(mode="json")


def titles(answer: dict) -> list[str]:
    return [screen["title"] for screen in answer["screens"]]


@pytest.fixture
def table(monkeypatch, tmp_path):
    """Tables with its help ready (a Spanish video), its WORKBOOK the made-up one with a current English file."""
    return ready_tables(monkeypatch, tmp_path, Help(videos={"es": VIDEO_ES}))


def test_it_is_a_read_of_whoever_sees_the_home_that_holds_no_database_and_is_a_tool():
    op = get("base.help.get")
    assert (op.kind, op.permission, op.database) == ("query", "base.view_home", False)
    assert isinstance(op.ai, AI) and is_tool(op)
    assert set(op.ai.asks) == {"en", "es"}


@pytest.fixture
def no_help(monkeypatch):
    """No app declares its help, whichever ones already have it."""
    for config in all_live_app_configs():
        monkeypatch.setattr(config, "help", None)


class TestWhichApps:
    def test_no_module_has_its_help_ready_until_it_declares_it(self, no_help):
        assert app_help.ready_apps() == []

    def test_a_module_that_declares_its_help_is_ready(self, no_help, monkeypatch):
        monkeypatch.setattr(apps.get_app_config("table"), "help", Help())
        assert app_help.ready_apps() == ["table"]

    @pytest.mark.parametrize("app", ["table", "base", "nope"])
    def test_an_app_without_its_help_ready_is_not_found_in_the_person_s_language(self, no_help, app):
        with pytest.raises(NotFound) as refused:
            ask(app)
        assert (refused.value.code, refused.value.message) == ("base.help_missing", "Esta app aún no tiene ayuda.")


    def test_the_hub_s_own_screens_are_ready_and_an_app_that_declares_no_help_is_not(self):
        assert "base" in app_help.ready_apps()
        assert not {"demo", "control"} & set(app_help.ready_apps())

    @pytest.mark.parametrize("app", ["demo", "control"])
    def test_an_app_that_declares_no_help_has_none_for_anyone(self, app):
        with pytest.raises(NotFound) as refused:
            ask(app, "es", "*")
        assert refused.value.code == "base.help_missing"


class TestTheHubsOwnScreens:
    """base's help: a section per screen of the Hub, each for whoever can see that screen."""

    @pytest.fixture
    def platform(self, monkeypatch, tmp_path):
        return ready_platform(monkeypatch, tmp_path)

    def test_it_answers_as_a_module_does_named_as_the_product(self, platform):
        answer = ask("base", "es", "*")
        assert {key: answer[key] for key in ("app", "name", "language", "video", "purpose")} == {
            "app": "base",
            "name": "ERPlora",
            "language": "es",
            "video": None,
            "purpose": "Lo que el Hub trae **siempre**, sin activar nada.",
        }

    def test_a_screen_s_text_is_its_summary_and_a_section_that_is_no_screen_is_left_out(self, platform):
        assert [(screen["id"], screen["title"], screen["path"], screen["text"]) for screen in ask("base", "es", "*")["screens"]] == [
            ("home", "Inicio · Resumen", "/", "El negocio de un vistazo."),
            ("files", "Archivos", "/files", "Los documentos del negocio."),
            ("system_logs", "Sistema · Registros", "/system#logs", "Lo que ha pasado."),
        ]

    def test_in_another_language_it_reads_its_current_file(self, platform):
        answer = ask("base", "en", "*")
        assert (answer["language"], answer["name"]) == ("en", "ERPlora")
        assert titles(answer) == ["Home · Summary", "Files", "System · Logs"]

    def test_its_tasks_are_not_published(self, platform):
        assert ask("base", "es", "*")["flows"] == []

    @pytest.mark.parametrize(
        ("also", "seen"),
        [
            ((), ["Inicio · Resumen"]),
            (("base.view_files",), ["Inicio · Resumen", "Archivos"]),
            (("base.administer_hub",), ["Inicio · Resumen", "Sistema · Registros"]),
            (("base.*",), ["Inicio · Resumen", "Archivos", "Sistema · Registros"]),
        ],
    )
    def test_whoever_cannot_see_a_screen_gets_no_help_of_it(self, platform, also, seen):
        assert titles(ask("base", "es", *also)) == seen

    def test_what_one_person_may_see_is_not_kept_for_the_next(self, platform):
        assert titles(ask("base")) == ["Inicio · Resumen"]
        assert titles(ask("base", "es", "base.*")) == ["Inicio · Resumen", "Archivos", "Sistema · Registros"]
        assert titles(ask("base")) == ["Inicio · Resumen"]


class TestTheRealScreens:
    """base's own WORKBOOK, in each language."""

    OWNER = ("base.*", "printing.manage_settings")
    EVERYONES_ES = [
        "Inicio · Resumen",
        "Inicio · Actividad",
        "Empleados · Personal",
        "Empleados · Roles",
        "Empleados · Roles · Qué permite",
        "Apps",
        "Ajustes · General",
        "Ajustes · Negocio",
        "Mi perfil",
    ]

    def test_whoever_runs_the_business_gets_every_screen_in_spanish(self):
        answer = ask("base", "es", *self.OWNER)
        assert answer["language"] == "es"
        assert titles(answer) == [
            "Inicio · Resumen",
            "Inicio · Actividad",
            "Empleados · Personal",
            "Empleados · Roles",
            "Empleados · Roles · Qué permite",
            "Empleados · API keys",
            "Empleados · Aprobaciones",
            "Ficha de una persona",
            "Archivos",
            "Apps",
            "Sistema · Uso y plan",
            "Sistema · Actualizaciones",
            "Sistema · Eventos caídos",
            "Sistema · Registros",
            "Ajustes · General",
            "Ajustes · Negocio",
            "Ajustes · Impresión",
            "Ajustes · Datos y copias",
            "Mi perfil",
        ]
        assert all(screen["text"] for screen in answer["screens"])

    def test_and_in_english(self):
        answer = ask("base", "en", *self.OWNER)
        assert answer["language"] == "en"
        assert titles(answer) == [
            "Home · Summary",
            "Home · Activity",
            "Employees · Staff",
            "Employees · Roles",
            "Employees · Roles · What it allows",
            "Employees · API keys",
            "Employees · Approvals",
            "A person's page",
            "Files",
            "Apps",
            "System · Usage and plan",
            "System · Updates",
            "System · Failed events",
            "System · Logs",
            "Settings · General",
            "Settings · Business",
            "Settings · Printing",
            "Settings · Data and backups",
            "My profile",
        ]
        assert all(screen["text"] for screen in answer["screens"])

    def test_an_accountant_gets_the_screens_everyone_has(self):
        assert titles(ask("base")) == self.EVERYONES_ES

    @pytest.mark.parametrize(
        ("permission", "more"),
        [
            ("base.view_files", {"Archivos"}),
            ("printing.manage_settings", {"Ajustes · Impresión"}),
            (
                "base.administer_hub",
                {
                    "Empleados · API keys",
                    "Empleados · Aprobaciones",
                    "Ficha de una persona",
                    "Sistema · Uso y plan",
                    "Sistema · Actualizaciones",
                    "Sistema · Eventos caídos",
                    "Sistema · Registros",
                    "Ajustes · Datos y copias",
                },
            ),
        ],
    )
    def test_each_permission_adds_the_screens_it_opens(self, permission, more):
        assert set(titles(ask("base", "es", permission))) - set(self.EVERYONES_ES) == more


class TestTheAnswer:
    def test_in_the_source_language_it_reads_workbook_md_with_the_menu_s_tabs(self, table):
        answer = ask(language="es")
        assert {key: answer[key] for key in ("app", "name", "language", "video")} == {
            "app": "table",
            "name": "Mesas",
            "language": "es",
            "video": VIDEO_ES,
        }
        assert answer["purpose"].startswith("Mesas es el **plano de la sala**")
        assert [(screen["id"], screen["title"], screen["path"]) for screen in answer["screens"]] == [
            ("floor_plan", "Plano de sala", "/table/floor-plan"),
            ("zones", "Zonas", "/table/zones"),
            ("settings", "Ajustes", "/table/settings"),
        ]
        assert [(flow["id"], flow["title"], flow["screens"]) for flow in answer["flows"]] == [
            ("TABLE-F01", "Crear una zona", ["zones"]),
            ("TABLE-F02", "Cobrar una mesa desde el plano", ["floor_plan"]),
            ("TABLE-F03", "Cobrar desde la ventana de cobro", ["floor_plan", "zones"]),
        ]
        assert answer["flows"][0]["failure"].startswith("Sin nombre, el botón no se activa. Un nombre repetido dice «Ya")

    def test_in_another_language_it_reads_its_current_file_with_the_tabs_in_that_language(self, table):
        answer = ask(language="en")
        assert (answer["language"], answer["name"]) == ("en", "Tables")
        assert [screen["title"] for screen in answer["screens"]] == ["Floor plan", "Zones", "Settings"]
        assert [flow["title"] for flow in answer["flows"]][0] == "Create a zone"

    def test_a_regional_variant_reads_its_language(self, table):
        assert ask(language="en-GB")["language"] == "en"

    def test_a_regional_language_of_the_deployment_without_a_file_reads_its_base_language_s(self, table, settings):
        settings.LANGUAGES = [*settings.LANGUAGES, ("en-gb", "British English")]
        assert ask(language="en-gb")["language"] == "en"

    def test_a_language_without_a_current_file_reads_the_source(self, table, tmp_path):
        (tmp_path / "WORKBOOK.en.md").unlink()
        answer = ask(language="en")
        assert (answer["language"], answer["name"], answer["screens"][0]["title"]) == ("es", "Mesas", "Plano de sala")

    def test_a_language_the_hub_does_not_speak_reads_the_source(self, table):
        assert ask(language="eo")["language"] == "es"

    def test_any_language_of_the_deployment_reads_its_own_file(self, table, tmp_path, settings):
        # A third language: its catalogues do not exist, so its labels and words are the code's own, as its file says.
        settings.LANGUAGES = [*settings.LANGUAGES, ("eo", "Esperanto")]
        write_workbooks(tmp_path, {"eo": EN})
        assert ask(language="eo")["language"] == "eo"


class TestWhatTheWindowReads:
    """What a module's window reads in a language, with the flows it leaves out: an app's own tests check theirs."""

    def test_it_says_the_language_served_and_reads_with_the_tabs_in_that_language(self, table):
        served, read = app_help.help_of(table, "en")
        assert served == "en"
        assert [screen.title for screen in read.screens] == ["Floor plan", "Zones", "Settings"]

    def test_it_keeps_the_flows_the_window_leaves_out(self, table):
        _served, read = app_help.help_of(table, "es")
        assert [draft.id for draft in read.unpublished] == ["TABLE-F04", "TABLE-F05"]

    def test_without_a_current_file_it_reads_the_source(self, table, tmp_path):
        (tmp_path / "WORKBOOK.en.md").unlink()
        served, read = app_help.help_of(table, "en")
        assert (served, read.screens[0].title) == ("es", "Plano de sala")


class TestTheVideo:
    def test_the_person_s_language_has_the_source_s_while_it_has_none_of_its_own(self, table):
        assert ask(language="en")["video"] == VIDEO_ES

    def test_the_person_s_language_has_its_own(self, table, monkeypatch):
        monkeypatch.setattr(table, "help", Help(videos={"es": VIDEO_ES, "en": VIDEO_EN}))
        assert (ask(language="en")["video"], ask(language="es")["video"]) == (VIDEO_EN, VIDEO_ES)

    def test_a_module_without_videos_has_none(self, table, monkeypatch):
        monkeypatch.setattr(table, "help", Help())
        assert ask()["video"] is None

    def test_a_regional_language_has_its_base_language_s_while_it_has_none_of_its_own(self, table, monkeypatch, settings):
        settings.LANGUAGES = [*settings.LANGUAGES, ("en-gb", "British English")]
        monkeypatch.setattr(table, "help", Help(videos={"es": VIDEO_ES, "en": VIDEO_EN}))
        assert ask(language="en-gb")["video"] == VIDEO_EN


class TestTheFlowVideos:
    """Each task of the window carries the short videos the module declares for its flow, in the person's language."""

    CREATE, CHARGE = "L4LipaZOq40", "hzMXqJHeFos"

    def videos(self, language: str) -> dict[str, list[str]]:
        return {flow["id"]: flow["videos"] for flow in ask(language=language)["flows"]}

    def test_a_flow_has_the_videos_of_the_person_s_language(self, table, monkeypatch):
        flows = {"TABLE-F01": {"es": [VIDEO_ES, self.CREATE], "en": [VIDEO_EN]}}
        monkeypatch.setattr(table, "help", Help(flow_videos=flows))
        assert self.videos("es")["TABLE-F01"] == [VIDEO_ES, self.CREATE]
        assert self.videos("en")["TABLE-F01"] == [VIDEO_EN]

    def test_a_flow_without_videos_in_the_person_s_language_has_the_source_s(self, table, monkeypatch):
        monkeypatch.setattr(table, "help", Help(flow_videos={"TABLE-F02": {"es": [self.CHARGE]}}))
        assert self.videos("en")["TABLE-F02"] == [self.CHARGE]

    def test_a_regional_language_has_its_base_language_s(self, table, monkeypatch, settings):
        settings.LANGUAGES = [*settings.LANGUAGES, ("en-gb", "British English")]
        monkeypatch.setattr(table, "help", Help(flow_videos={"TABLE-F02": {"es": [self.CHARGE], "en": [VIDEO_EN]}}))
        assert self.videos("en-gb")["TABLE-F02"] == [VIDEO_EN]

    def test_a_flow_without_videos_has_none_and_the_others_keep_theirs(self, table, monkeypatch):
        monkeypatch.setattr(table, "help", Help(flow_videos={"TABLE-F02": {"es": [self.CHARGE]}}))
        assert self.videos("es") == {"TABLE-F01": [], "TABLE-F02": [self.CHARGE], "TABLE-F03": []}


class TestReadOnce:
    """A module's WORKBOOKs only change with a new image: each module and language is read and cut once per process."""

    @pytest.fixture
    def calls(self, monkeypatch):
        counted = Counter()
        for name in ("workbook", "parse"):
            real = getattr(workbook_help, name)
            monkeypatch.setattr(workbook_help, name, lambda *args, _real=real, _name=name: counted.update([_name]) or _real(*args))
        return counted

    def test_a_second_call_reads_and_cuts_nothing_again(self, table, calls):
        first = ask(language="en")
        assert ask(language="en") == first
        assert calls == {"workbook": 1, "parse": 1}

    def test_each_language_is_read_once(self, table, calls):
        ask(language="en"), ask(language="es"), ask(language="en"), ask(language="es")
        assert calls == {"workbook": 2, "parse": 2}

    def test_with_debug_every_call_reads_the_workbook_so_an_edit_shows_at_once(self, table, calls, settings, tmp_path):
        settings.DEBUG = True
        before = ask(language="es")["purpose"]
        (tmp_path / "WORKBOOK.md").write_text((tmp_path / "WORKBOOK.md").read_text().replace("sus zonas", "sus salas"))
        assert ask(language="es")["purpose"] == before.replace("sus zonas", "sus salas")
        assert calls == {"workbook": 2, "parse": 2}
