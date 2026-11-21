"""The QA journeys walk every flow that is done on a screen, cite only flows that are done, and keep their format.

A journey (``qa/journeys/<slug>.md``, its contract in ``qa/README.md``) refers to the WORKBOOKs' flows only by id, so a
change to a WORKBOOK that adds, drops or finishes a flow without updating the journeys fails here. The made-up
WORKBOOKs and journeys below show each check catching what it guards, and the command's report and ledger read.
"""

import io
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from base import qa_coverage
from base.catalog import known_verticals

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

### SAMPLE-F02 Hecho con una nota
Estado: hecho — también por la API
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

LEDGER_HEADER = "flow,date,device,app_version,result,issue\n"


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


class TestTheRepository:
    def test_every_journey_keeps_the_format(self, repo_journeys):
        assert repo_journeys, "qa/journeys holds no journey"
        assert [f"{journey.name}: {problem}" for journey in repo_journeys for problem in journey.problems] == []

    def test_every_flow_a_journey_cites_is_in_a_workbook_and_done(self, repo_flows, repo_journeys):
        assert qa_coverage.citation_problems(repo_flows, repo_journeys) == []

    def test_every_flow_done_on_a_screen_is_in_some_journey(self, repo_flows, repo_journeys):
        report = qa_coverage.coverage(repo_flows, repo_journeys)
        assert {app: apps.not_walked for app, apps in report.items() if apps.not_walked} == {}


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

    def test_a_partial_flow_and_one_not_done_are_not_done(self, tree):
        flows = qa_coverage.workbook_flows(tree)
        assert not flows["SAMPLE-F03"].done
        assert not flows["SAMPLE-F04"].done

    def test_each_flow_belongs_to_the_folder_of_its_workbook(self, tree):
        flows = qa_coverage.workbook_flows(tree)
        assert flows["BASE-F01"].app == "base"
        assert flows["SAMPLE-F01"].app == "sample"

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
    def test_the_last_walk_of_each_flow_is_its_latest_date(self, tmp_path):
        ledger = tmp_path / "walks.csv"
        ledger.write_text(
            LEDGER_HEADER
            + "SAMPLE-F01,2026-11-02,tablet,1.4.0,ok,\n"
            + "SAMPLE-F01,2026-11-20,phone,1.5.0,fail,ERPlora/hub#1\n"
            + "SAMPLE-F01,2026-11-10,desktop,1.4.2,ok,\n"
            + "SAMPLE-F02,2026-11-03,tablet,1.4.0,ok,\n",
            encoding="utf-8",
        )
        walks = qa_coverage.last_walks(ledger)
        assert walks["SAMPLE-F01"] == qa_coverage.Walk("2026-11-20", "phone", "1.5.0", "fail", "ERPlora/hub#1")
        assert walks["SAMPLE-F02"].date == "2026-11-03"
        assert "SAMPLE-F08" not in walks

    def test_a_ledger_without_a_column_is_refused_naming_it(self, tmp_path):
        ledger = tmp_path / "walks.csv"
        ledger.write_text("flow,date,device,result\nSAMPLE-F01,2026-11-02,tablet,ok\n", encoding="utf-8")
        with pytest.raises(qa_coverage.LedgerError, match="app_version, issue"):
            qa_coverage.last_walks(ledger)

    def test_a_date_that_is_not_iso_is_refused_naming_its_line(self, tmp_path):
        ledger = tmp_path / "walks.csv"
        ledger.write_text(LEDGER_HEADER + "SAMPLE-F01,20/11/2026,tablet,1.4.0,ok,\n", encoding="utf-8")
        with pytest.raises(qa_coverage.LedgerError, match="line 2"):
            qa_coverage.last_walks(ledger)


class TestTheCommand:
    def test_it_reports_each_app_and_the_totals(self):
        out = io.StringIO()
        call_command("qa_coverage", stdout=out)
        lines = out.getvalue().splitlines()
        assert any(line.startswith("sale: ") and "in a journey" in line for line in lines)
        assert any(line.startswith("tip: 0 in a journey, 0 in none, ") for line in lines)
        assert lines[-1].startswith("total: ")

    def test_with_a_ledger_it_says_when_each_walkable_flow_was_last_walked(self, tmp_path):
        ledger = tmp_path / "walks.csv"
        ledger.write_text(
            LEDGER_HEADER + "SALE-F01,2026-11-20,tablet,1.5.0,ok,\nNOPE-F01,2026-11-20,tablet,1.5.0,ok,\n",
            encoding="utf-8",
        )
        out = io.StringIO()
        call_command("qa_coverage", ledger=str(ledger), stdout=out)
        text = out.getvalue()
        assert "SALE-F01 2026-11-20 ok tablet 1.5.0" in text
        assert "SALE-F02 never" in text
        assert "the ledger names flows no WORKBOOK has: NOPE-F01" in text

    def test_a_ledger_it_cannot_read_stops_it_with_the_reason(self, tmp_path):
        ledger = tmp_path / "walks.csv"
        ledger.write_text("flow,date\nSALE-F01,2026-11-20\n", encoding="utf-8")
        with pytest.raises(CommandError, match="device"):
            call_command("qa_coverage", ledger=str(ledger), stdout=io.StringIO())
