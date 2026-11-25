"""The QA journeys walk every flow that is done on a screen, cite only flows that are done, and keep their format; and the
WORKBOOKs say what the assistant does in each of those flows.

A journey (``qa/journeys/<slug>.md``, its contract in ``qa/README.md``) refers to the WORKBOOKs' flows only by id, so a
change to a WORKBOOK that adds, drops or finishes a flow without updating the journeys fails here. The made-up
WORKBOOKs and journeys below show each check catching what it guards, and the command's report and ledger read.
"""

import io
import re
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from live.operations import registry

from base import qa_assistant, qa_coverage
from base.catalog import known_verticals
from base.qa_coverage import Walk

REPO = Path(__file__).resolve().parent.parent
VERTICALS = ("hair_salon", "restaurant")

SAMPLE = """\
# Workbook — Ejemplo
Prefijo: SAMPLE

## Para qué sirve

Un ejemplo.

## Flujos

### SAMPLE-F01 Hecho en una pantalla
Estado: hecho
Pantalla: Lista
Operaciones: las de la lista, ninguna más

### SAMPLE-F02 Hecho con una nota
Estado: hecho — también por la API
Actor: responsable,
  asistente
Pantalla: Lista, Ficha

### SAMPLE-F03 Parcial
Estado: parcial — falta la ficha
Pantalla: Ficha

### SAMPLE-F04 No hecho
Estado: no hecho
Pantalla: Lista

### SAMPLE-F05 Lo hace el sistema
Estado: hecho
Pantalla: ninguna (se ve en la Lista)

### SAMPLE-F06 Tampoco tiene pantalla
Estado: hecho
Pantalla: Ninguna; la dirección sigue igual

### SAMPLE-F08 Hecho y sin recorrido
Estado: hecho
Pantalla: Ficha
Operaciones: ninguna (solo lleva a otra pantalla)

## Para quien lo mantiene

### SAMPLE-F07 Solo lo lee quien lo mantiene
Estado: hecho
Pantalla: Lista
"""

BASE = """\
# Workbook — Plataforma

## Para qué sirve

La plataforma.

### BASE-F01 Entrar
Estado: hecho
Pantalla: Acceso

## Para quien lo mantiene
"""

TRANSLATION = """\
# Workbook — Sample

## What it is for

### SAMPLE-F99 Only in the translation
Status: done
Screen: List

## Para quien lo mantiene
"""

JOURNEY = """\
---
title: Un día de ejemplo
vertical: restaurant
roles: responsable, empleado
---

Para qué: comprobar el recorrido de ejemplo.

## Punto de partida

- Un negocio con la app de ejemplo.

## Recorrido

1. SAMPLE-F01 — el responsable crea «Mesa 1».
2. SAMPLE-F02, BASE-F01
3. SAMPLE-F05 — «Mesa 1» sale en la lista.
"""

LEDGER_HEADER = "flow,date,device,app_version,result,issue,channel,phrase,model_result\n"
OLD_LEDGER_HEADER = "flow,date,device,app_version,result,issue\n"
COUNTS = re.compile(r"^(\w+): (\d+) in a journey, (\d+) in none, (\d+) out of visual scope$")


@pytest.fixture
def tree(tmp_path):
    """A repository with base's WORKBOOK, one module's WORKBOOK and its translation, and one journey."""
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "WORKBOOK.md").write_text(BASE, encoding="utf-8")
    app = tmp_path / "apps" / "sample"
    app.mkdir(parents=True)
    (app / "WORKBOOK.md").write_text(SAMPLE, encoding="utf-8")
    (app / "WORKBOOK.en.md").write_text(TRANSLATION, encoding="utf-8")
    journeys = tmp_path / "qa" / "journeys"
    journeys.mkdir(parents=True)
    (journeys / "sample-day.md").write_text(JOURNEY, encoding="utf-8")
    return tmp_path


@pytest.fixture
def ledger(tmp_path):
    return tmp_path / "walks.csv"


def report_of(**options):
    """The lines ``manage.py qa_coverage`` writes."""
    out = io.StringIO()
    call_command("qa_coverage", stdout=out, **options)
    return out.getvalue().splitlines()


def journey_from(tmp_path, text):
    path = tmp_path / "journey.md"
    path.write_text(text, encoding="utf-8")
    return qa_coverage.read_journey(path, VERTICALS)


@pytest.fixture(scope="module")
def repo_flows():
    return qa_coverage.workbook_flows(REPO)


@pytest.fixture(scope="module")
def repo_journeys():
    return qa_coverage.read_journeys(REPO, known_verticals())


@pytest.fixture(scope="module")
def repo_answers(repo_flows):
    return qa_assistant.report(REPO, repo_flows, registry)


class TestTheRepository:
    def test_every_journey_keeps_the_format(self, repo_journeys):
        assert repo_journeys, "qa/journeys holds no journey"
        assert [f"{journey.name}: {problem}" for journey in repo_journeys for problem in journey.problems] == []

    def test_every_flow_a_journey_cites_is_in_a_workbook_and_done(self, repo_flows, repo_journeys):
        assert qa_coverage.citation_problems(repo_flows, repo_journeys) == []

    def test_every_flow_done_on_a_screen_is_in_some_journey(self, repo_flows, repo_journeys):
        report = qa_coverage.coverage(repo_flows, repo_journeys)
        assert {app: apps.not_walked for app, apps in report.items() if apps.not_walked} == {}


class TestWhatTheRepositorySaysOfTheAssistant:
    def test_every_flow_done_on_a_screen_has_a_group(self, repo_answers):
        assert [one.flow.id for one in repo_answers.flows if one.group is None] == []

    def test_no_flow_contradicts_itself(self, repo_answers):
        assert [one.flow.id for one in repo_answers.flows if one.contradicts] == []

    def test_every_flow_and_operation_the_manuals_cite_exists(self, repo_answers):
        assert repo_answers.broken_citations == ()

    def test_every_tool_of_the_assistant_is_cited_by_some_flow(self, repo_answers):
        assert repo_answers.uncited_tools == ()


class TestTheWorkbooks:
    def test_a_flow_is_walkable_when_it_is_done_and_someone_does_it_on_a_screen(self, tree):
        flows = qa_coverage.workbook_flows(tree)
        walkable = {flow_id for flow_id, flow in flows.items() if flow.walkable}
        assert walkable == {"BASE-F01", "SAMPLE-F01", "SAMPLE-F02", "SAMPLE-F08"}

    def test_a_flow_with_no_screen_is_done_but_out_of_reach(self, tree):
        flows = qa_coverage.workbook_flows(tree)
        for flow_id in ("SAMPLE-F05", "SAMPLE-F06"):
            assert flows[flow_id].done
            assert not flows[flow_id].on_screen

    def test_a_flow_says_that_it_uses_no_operation(self, tree):
        flows = qa_coverage.workbook_flows(tree)
        assert [flow_id for flow_id, flow in flows.items() if flow.no_operations] == ["SAMPLE-F08"]

    def test_a_partial_flow_and_one_not_done_are_not_done(self, tree):
        flows = qa_coverage.workbook_flows(tree)
        assert not flows["SAMPLE-F03"].done
        assert not flows["SAMPLE-F04"].done

    def test_each_flow_belongs_to_the_folder_of_its_workbook(self, tree):
        flows = qa_coverage.workbook_flows(tree)
        assert flows["BASE-F01"].app == "base"
        assert flows["SAMPLE-F01"].app == "sample"

    def test_each_flow_says_who_does_it_and_where_on_one_line(self, tree):
        flows = qa_coverage.workbook_flows(tree)
        assert (flows["SAMPLE-F02"].actor, flows["SAMPLE-F02"].screen) == ("responsable, asistente", "Lista, Ficha")
        assert (flows["SAMPLE-F01"].actor, flows["SAMPLE-F01"].screen) == ("", "Lista")

    def test_only_the_customers_part_of_the_source_is_read(self, tree):
        flows = qa_coverage.workbook_flows(tree)
        assert "SAMPLE-F07" not in flows
        assert "SAMPLE-F99" not in flows


class TestAJourney:
    def test_a_well_formed_journey_gives_the_flows_of_each_step(self, tree):
        journey = qa_coverage.read_journey(tree / "qa" / "journeys" / "sample-day.md", VERTICALS)
        assert journey.problems == ()
        assert journey.name == "sample-day.md"
        assert journey.vertical == "restaurant"
        assert journey.steps == (("SAMPLE-F01",), ("SAMPLE-F02", "BASE-F01"), ("SAMPLE-F05",))

    def test_any_vertical_is_accepted(self, tmp_path):
        assert journey_from(tmp_path, JOURNEY.replace("vertical: restaurant", "vertical: any")).problems == ()

    @pytest.mark.parametrize(
        ("old", "new", "problem"),
        [
            ("---\ntitle: Un día de ejemplo\nvertical: restaurant\nroles: responsable, empleado\n---\n", "", "header"),
            ("roles: responsable, empleado\n", "", "roles"),
            ("roles: responsable, empleado", "roles:", "roles"),
            ("title: Un día de ejemplo", "title Un día de ejemplo", "title Un día de ejemplo"),
            ("vertical: restaurant", "vertical: bakery", "bakery"),
            ("Para qué: comprobar el recorrido de ejemplo.\n", "", "Para qué"),
            ("Para qué: comprobar el recorrido de ejemplo.", "Para qué:", "Para qué"),
            ("## Punto de partida", "## Antes de empezar", "sections"),
            ("## Recorrido\n", "## Recorrido\n\n## Notas\n", "sections"),
            ("- Un negocio con la app de ejemplo.\n", "", "Punto de partida"),
            ("2. SAMPLE-F02", "3. SAMPLE-F02", "number 2"),
            ("3. SAMPLE-F05 — «Mesa 1» sale en la lista.", "3. Mirar la lista (SAMPLE-F05).", "not a step"),
            ("2. SAMPLE-F02, BASE-F01", "2. SAMPLE-F02 BASE-F01", "not a step"),
            ("1. SAMPLE-F01 — el responsable crea «Mesa 1».", "1. SAMPLE-F01 —", "not a step"),
        ],
        ids=[
            "no-header",
            "no-roles",
            "empty-roles",
            "header-line",
            "vertical",
            "no-purpose",
            "empty-purpose",
            "other-section",
            "extra-section",
            "empty-start",
            "numbering",
            "id-not-first",
            "ids-without-comma",
            "dash-without-note",
        ],
    )
    def test_each_broken_rule_is_reported(self, tmp_path, old, new, problem):
        assert old in JOURNEY
        problems = journey_from(tmp_path, JOURNEY.replace(old, new)).problems
        assert problems
        assert problem in " | ".join(problems)

    def test_a_journey_without_steps_is_reported(self, tmp_path):
        text = JOURNEY.split("1. SAMPLE-F01")[0]
        assert "it has no steps" in journey_from(tmp_path, text).problems

    def test_every_journey_of_the_folder_is_read_in_order(self, tree):
        (tree / "qa" / "journeys" / "another-day.md").write_text(JOURNEY, encoding="utf-8")
        (tree / "qa" / "journeys" / "notes.txt").write_text("not a journey", encoding="utf-8")
        names = [journey.name for journey in qa_coverage.read_journeys(tree, VERTICALS)]
        assert names == ["another-day.md", "sample-day.md"]


class TestTheCoverage:
    def test_each_app_splits_its_flows_into_walked_not_walked_and_out_of_reach(self, tree):
        flows = qa_coverage.workbook_flows(tree)
        report = qa_coverage.coverage(flows, qa_coverage.read_journeys(tree, VERTICALS))
        assert report["sample"] == qa_coverage.Coverage(
            walked=("SAMPLE-F01", "SAMPLE-F02"),
            not_walked=("SAMPLE-F08",),
            out_of_reach=("SAMPLE-F03", "SAMPLE-F04", "SAMPLE-F05", "SAMPLE-F06"),
        )
        assert report["base"] == qa_coverage.Coverage(walked=("BASE-F01",), not_walked=(), out_of_reach=())

    def test_citing_a_flow_out_of_reach_does_not_count_it_as_walked(self, tree):
        flows = qa_coverage.workbook_flows(tree)
        report = qa_coverage.coverage(flows, qa_coverage.read_journeys(tree, VERTICALS))
        assert "SAMPLE-F05" not in report["sample"].walked

    def test_a_cited_flow_that_is_in_no_workbook_or_not_done_is_reported(self, tree, tmp_path):
        flows = qa_coverage.workbook_flows(tree)
        steps = "1. SAMPLE-F03\n2. SAMPLE-F04, SAMPLE-F05\n3. SAMPLE-F07\n4. SAMPLE-F99\n"
        journey = journey_from(tmp_path, JOURNEY.split("1. SAMPLE-F01")[0] + steps)
        assert qa_coverage.citation_problems(flows, [journey]) == [
            "journey.md step 1: SAMPLE-F03 is not done",
            "journey.md step 2: SAMPLE-F04 is not done",
            "journey.md step 3: SAMPLE-F07 is in no WORKBOOK",
            "journey.md step 4: SAMPLE-F99 is in no WORKBOOK",
        ]


class TestTheLedger:
    def test_the_last_walk_of_each_flow_on_each_channel_is_its_latest_date(self, ledger):
        ledger.write_text(
            LEDGER_HEADER
            + "SAMPLE-F01,2026-11-02,tablet,1.4.0,ok,,screen,,\n"
            + "SAMPLE-F01,2026-11-20,phone,1.5.0,fail,ERPlora/hub#1,screen,,\n"
            + "SAMPLE-F01,2026-11-10,desktop,1.4.2,ok,,screen,,\n"
            + "SAMPLE-F01,2026-11-22,tablet,1.6.0,ok,,assistant-es,whole,partial\n"
            + "SAMPLE-F01,2026-11-21,tablet,1.5.0,partial,ERPlora/hub#2,assistant-es,partial,ok\n"
            + "SAMPLE-F01,2026-11-05,tablet,1.4.0,fail,,assistant-en,partial,fail\n"
            + "SAMPLE-F02,2026-11-03,tablet,1.4.0,ok,,assistant-en,whole,ok\n",
            encoding="utf-8",
        )
        walks = qa_coverage.last_walks(ledger)
        assert walks["SAMPLE-F01"] == {
            "screen": Walk("2026-11-20", "phone", "1.5.0", "fail", "ERPlora/hub#1", "screen", "", ""),
            "assistant-es": Walk("2026-11-22", "tablet", "1.6.0", "ok", "", "assistant-es", "whole", "partial"),
            "assistant-en": Walk("2026-11-05", "tablet", "1.4.0", "fail", "", "assistant-en", "partial", "fail"),
        }
        assert set(walks["SAMPLE-F02"]) == {"assistant-en"}
        assert "SAMPLE-F08" not in walks

    def test_of_two_walks_on_the_same_date_the_last_one_is_the_one_written_later(self, ledger):
        ledger.write_text(
            LEDGER_HEADER
            + "SAMPLE-F01,2026-11-20,tablet,1.5.0,fail,ERPlora/hub#1,screen,,\n"
            + "SAMPLE-F01,2026-11-20,tablet,1.5.1,ok,,screen,,\n",
            encoding="utf-8",
        )
        assert qa_coverage.last_walks(ledger)["SAMPLE-F01"]["screen"].app_version == "1.5.1"

    @pytest.mark.parametrize(
        ("header", "missing"),
        [
            ("flow,date,device,result,channel,phrase,model_result\n", "no column app_version, issue$"),
            (OLD_LEDGER_HEADER, "no column channel, phrase, model_result$"),
        ],
        ids=["two-columns-short", "without-the-channel"],
    )
    def test_a_ledger_without_a_column_is_refused_naming_it(self, ledger, header, missing):
        ledger.write_text(header, encoding="utf-8")
        with pytest.raises(qa_coverage.LedgerError, match=missing):
            qa_coverage.last_walks(ledger)

    def test_a_date_that_is_not_iso_is_refused_naming_its_line(self, ledger):
        ledger.write_text(LEDGER_HEADER + "SAMPLE-F01,20/11/2026,tablet,1.4.0,ok,,screen,,\n", encoding="utf-8")
        with pytest.raises(qa_coverage.LedgerError, match=r"line 2: '20/11/2026'"):
            qa_coverage.last_walks(ledger)

    @pytest.mark.parametrize(
        ("row", "channel"),
        [
            ("SAMPLE-F01,2026-11-20,tablet,1.4.0,ok,,assistant,,", "'assistant'"),
            ("SAMPLE-F01,2026-11-20,tablet,1.4.0,ok,,,,", "''"),
            ("SAMPLE-F01,2026-11-20,tablet,1.4.0,ok,", "''"),
        ],
        ids=["another-channel", "empty", "row-of-six-columns"],
    )
    def test_a_channel_that_is_none_of_the_three_is_refused_naming_its_line(self, ledger, row, channel):
        walked = "SAMPLE-F01,2026-11-20,tablet,1.4.0,ok,,screen,,\n"
        ledger.write_text(LEDGER_HEADER + walked + row + "\n", encoding="utf-8")
        with pytest.raises(qa_coverage.LedgerError, match=rf"line 3: {channel} .*screen, assistant-es, assistant-en"):
            qa_coverage.last_walks(ledger)


class TestTheCommand:
    def test_it_reports_each_app_and_totals_that_add_them_up(self, repo_flows):
        lines = report_of()
        counts = {match[1]: tuple(map(int, match.groups()[1:])) for line in lines if (match := COUNTS.match(line))}
        assert set(counts) == {flow.app for flow in repo_flows.values()} | {"total"}
        assert counts.pop("total") == tuple(map(sum, zip(*counts.values(), strict=True)))
        assert lines[-1].startswith("total: ")

    def test_with_a_ledger_it_gives_the_last_walk_of_each_walkable_flow_by_channel(self, tree, ledger, settings):
        settings.BASE_DIR = tree
        ledger.write_text(
            LEDGER_HEADER
            + "BASE-F01,2026-11-21,tablet,1.5.0,ok,,screen,,\n"
            + "SAMPLE-F01,2026-11-20,phone,1.5.0,fail,ERPlora/hub#1,screen,,\n"
            + "SAMPLE-F01,2026-11-23,tablet,1.6.0,ok,,assistant-es,partial,fail\n"
            + "SAMPLE-F01,2026-11-19,tablet,1.4.0,partial,ERPlora/hub#2,assistant-en,whole,ok\n"
            + "SAMPLE-F08,2026-11-22,tablet,1.6.0,ok,,assistant-en,,\n"
            + "SAMPLE-F02,2026-11-20,tablet,1.5.0,ok,,assistant-es,whole,ok\n"
            + "SAMPLE-F05,2026-11-22,tablet,1.6.0,ok,,screen,,\n"
            + "HUB_APP-F02,2026-11-22,tablet,1.6.0,ok,,screen,,\n",
            encoding="utf-8",
        )
        lines = report_of(ledger=str(ledger))
        walks = lines[lines.index("last walks, screen: 2 walked, 2 never") : -1]
        assert walks == [
            "last walks, screen: 2 walked, 2 never",
            "  SAMPLE-F02 never",
            "  SAMPLE-F08 never",
            "  SAMPLE-F01 screen 2026-11-20 fail phone 1.5.0 ERPlora/hub#1",
            "  BASE-F01 screen 2026-11-21 ok tablet 1.5.0",
            "last walks, assistant: 3 walked, 1 never",
            "  BASE-F01 never",
            "  SAMPLE-F01 assistant-en 2026-11-19 partial model:ok phrase:whole tablet 1.4.0 ERPlora/hub#2",
            "  SAMPLE-F02 assistant-es 2026-11-20 ok model:ok phrase:whole tablet 1.5.0",
            "  SAMPLE-F08 assistant-en 2026-11-22 ok tablet 1.6.0",
            "  SAMPLE-F01 assistant-es 2026-11-23 ok model:fail phrase:partial tablet 1.6.0",
            "  the ledger names flows in no WORKBOOK of the Hub: HUB_APP-F02",
        ]
        assert lines[-1].startswith("total: ")

    def test_without_a_ledger_it_says_nothing_about_walks(self, tree, settings):
        settings.BASE_DIR = tree
        assert "last walks" not in "\n".join(report_of())

    def test_a_ledger_it_cannot_read_stops_it_with_the_reason(self, ledger):
        ledger.write_text("flow,date\nSALE-F01,2026-11-20\n", encoding="utf-8")
        with pytest.raises(CommandError, match="device"):
            call_command("qa_coverage", ledger=str(ledger), stdout=io.StringIO())
