"""Tests of scripts/e2e_report.py: the output of the Hub's nightly e2e run and the one open issue it keeps about it.

The script runs as .github/scripts/nightly-e2e.sh runs it, with Playwright JSON reports written here and a fake gh CLI
on the PATH that answers the open issues and records its calls and the bodies it is given.
"""

import datetime
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "e2e_report.py"


def load_script():
    """The script as a module, registered under its name: its dataclass looks its own module up while it is built."""
    spec = importlib.util.spec_from_file_location("e2e_report", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["e2e_report"] = module
    spec.loader.exec_module(module)
    return module


e2e_report = load_script()
TITLE = "Pruebas de navegador del Hub en rojo en la pasada nocturna"
SEARCH = f'gh issue list --state open --search "{TITLE}" in:title --limit 50 --json number,title'
CREATE = f"gh issue create --title {TITLE} --label prio:P1 --body-file <body>"
SETTINGS = ("RESULT", "SHA", "RUN_DIR")
NIGHT = ".erplora/hub-nightly-e2e/runs/20261114-021700"
FOLDER = f"~/{NIGHT}"

FAKE_GH = """\
import os
import sys

args = sys.argv[1:]
call = " ".join(args)
with open(os.environ["CALLS_LOG"], "a", encoding="utf-8") as calls:
    calls.write("gh " + call + "\\n")
if os.environ.get("GH_FAILS") and os.environ.get("GH_FAILS_ON", "") in call:
    print("HTTP 502", file=sys.stderr)
    sys.exit(int(os.environ["GH_FAILS"]))
with open(os.environ["BODIES_LOG"], "a", encoding="utf-8") as bodies:
    for flag, value in zip(args, args[1:]):
        if flag == "--body-file":
            with open(value, encoding="utf-8") as body:
                bodies.write(body.read())
        elif flag == "--comment":
            bodies.write(value + "\\n")
if args[:2] == ["issue", "list"]:
    print(os.environ.get("OPEN_ISSUES", "[]"))
if args[:2] == ["issue", "create"]:
    print("https://github.com/ERPlora/hub/issues/99")
"""


def spec(title, line, tests, file="a.spec.ts"):
    return {"title": title, "file": file, "line": line, "tests": tests}


def red(*results, project=""):
    """A test that came out red, with the results Playwright gave it (none when not given)."""
    test = {"projectName": project, "status": "unexpected"}
    return {**test, "results": list(results)} if results else test


def error(message):
    return {"status": "failed", "error": {"message": message}}


STATS = {"expected": 1, "skipped": 0, "unexpected": 1, "flaky": 0}


def suite_of(*specs):
    return {"suites": [{"title": "a.spec.ts", "file": "a.spec.ts", "specs": list(specs)}], "errors": [], "stats": STATS}


def lines_of(test):
    return suite_of(spec("t", 1, [test]))


# A red test inside a describe, a timed-out test, a passing and a skipped one, as Playwright's json reporter writes
# them for the Hub's single project, whose name is empty (colours in the messages included).
RED = {
    "suites": [
        {
            "title": "sale-sales.spec.ts", "file": "sale-sales.spec.ts", "line": 0,
            "specs": [spec("passes", 2, [{"projectName": "", "status": "expected"}], "sale-sales.spec.ts")],
            "suites": [{
                "title": "SALE-F01 the sale", "file": "sale-sales.spec.ts", "line": 3,
                "specs": [spec("charges in cash", 4, [red(error(
                    "Error: \u001b[2mexpect(\u001b[22mlocator).toBeVisible()\n\nExpected: visible"))],
                    "sale-sales.spec.ts")],
            }],
        },
        {
            "title": "staff-flows.spec.ts", "file": "staff-flows.spec.ts", "line": 0,
            "specs": [
                spec("skipped one", 2, [{"projectName": "", "status": "skipped"}], "staff-flows.spec.ts"),
                spec("adds a member", 9, [red(error("Test timeout of 180000ms exceeded."))], "staff-flows.spec.ts"),
            ],
        },
    ],
    "errors": [],
    "stats": {"expected": 1, "skipped": 1, "unexpected": 2, "flaky": 0, "duration": 1000},
}
# A run that stopped in globalSetup: no test ran, the error is the run's.
SETUP = {"suites": [], "errors": [{"message": "Error: unapplied migrations (sale.0042)\n    at globalSetup"}],
         "stats": {"expected": 0, "skipped": 0, "unexpected": 0, "flaky": 0, "duration": 10}}
OPEN = json.dumps([{"number": 43, "title": f"{TITLE} (otra)"}, {"number": 42, "title": TITLE}])

RED_DETAILS = (
    "2 en rojo · 1 bien · 1 saltadas\n\n"
    "- `sale-sales.spec.ts:4` › SALE-F01 the sale › charges in cash — Error: expect(locator).toBeVisible()\n"
    "- `staff-flows.spec.ts:9` › adds a member — Test timeout of 180000ms exceeded.\n"
)
RED_HEADING = (
    f"## Pruebas de navegador del Hub: en rojo\n\nLa pasada del 2026-11-14, commit `0123456`, en `{FOLDER}`.\n\n"
)
GREEN_OUTPUT = (
    "## Pruebas de navegador del Hub: en verde\n\nLa pasada del 2026-11-14 ha salido en verde (commit `0123456`).\n"
)
UNPUBLISHED = "\nSin publicar: no se escribe ninguna issue.\n"
CREATED = "https://github.com/ERPlora/hub/issues/99\n"
ISSUE_BODY = (
    "## Qué pasa\n"
    "Cada noche se prueban solas, en un navegador, todas las pantallas del Hub sobre la última versión, y esta noche"
    " alguna ha fallado. Puede ser un fallo real que ya está en producción o una prueba que se ha quedado vieja: hasta"
    " que alguien lo mire no se sabe.\n\n"
    "## Propuesta\n"
    "Mirar cada prueba de la lista: si el fallo es del producto, arreglarlo con su prueba; si la prueba se quedó vieja,"
    " ponerla al día. Esta issue se cierra sola la primera noche en que la pasada salga entera en verde.\n\n"
    "## Detalle técnico\n"
    "- Pasada del 2026-11-14 sobre `main` (commit `0123456`), en el Mac. El registro de la noche (`night.log`) y las"
    f" trazas y capturas de cada fallo (`test-results/`), en `{FOLDER}`.\n"
    "- Una spec se repite en una pila propia (`tests/e2e/README.md`, «Varias ejecuciones a la vez») con `CI=1 pnpm e2e"
    " tests/e2e/<spec>`, o con la misma pila de la noche: `bash .github/scripts/nightly-e2e.sh --no-publish --spec"
    " tests/e2e/<spec>`.\n\n"
    f"{RED_DETAILS}\n"
    "## Origen\n"
    "- Cómo se llegó: la pasada nocturna de las pruebas de navegador del Hub (`.github/scripts/nightly-e2e.sh`, que"
    " lanza launchd en el Mac).\n"
    "- Sale de #877\n"
    "- La introdujo una PR: no comprobado — la pasada no sabe qué cambio la rompió; se busca entre los commits desde la"
    " última noche en verde.\n\n"
    "## Cómo se reproduce\n"
    "- Test: las specs de la lista, que fallan sobre `origin/main@0123456` (`CI=1 pnpm e2e tests/e2e/<spec>` en una"
    " pila propia).\n\n"
    "## Flujo\n"
    "- Flujo: ninguno — la pasada no sabe qué flujo prueba cada spec; el triaje lo pone al leerla.\n"
)


def night(result="failure"):
    return e2e_report.Night(result=result, commit="0123456", day="2026-11-14", folder=FOLDER, publish=False)


class NightCase(unittest.TestCase):
    """Runs e2e_report.py in a folder of its own; gh's calls and the bodies it was given stay readable after."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.work = Path(folder.name)
        (self.work / "bin").mkdir()
        gh = self.work / "bin" / "gh"
        gh.write_text(f"#!{sys.executable}\n{FAKE_GH}")
        gh.chmod(0o755)
        self.home = self.path("home")
        self.red_report = self.write("red.json", RED)

    def write(self, name, content):
        path = self.work / name
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
        return str(path)

    def report(self, **settings):
        """Runs the script with the night's settings, each overridable; None leaves one out. Returns its exit code."""
        for log in ("calls.log", "bodies.log"):
            (self.work / log).write_text("")
        env = {key: value for key, value in os.environ.items() if not key.startswith(("GH_", "DAY", "STEP", "REPORT"))}
        env |= {
            "PATH": f"{self.work / 'bin'}{os.pathsep}{os.environ['PATH']}", "GH_REPO": "ERPlora/hub", "HOME": self.home,
            "SHA": "0123456789abcdef", "RUN_DIR": f"{self.home}/{NIGHT}", "DAY": "2026-11-14", "PUBLISH": "true",
            "RESULT": "failure", "REPORT": self.red_report, "OPEN_ISSUES": "[]",
            "CALLS_LOG": self.path("calls.log"), "BODIES_LOG": self.path("bodies.log"),
        }
        env |= settings
        env = {key: value for key, value in env.items() if value is not None}
        done = subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, check=False)
        self.stdout, self.stderr = done.stdout.decode("utf-8"), done.stderr.decode("utf-8")
        return done.returncode

    def path(self, name):
        return str(self.work / name)

    def read(self, name):
        return (self.work / name).read_text(encoding="utf-8")

    @property
    def calls(self):
        return re.sub(r"--body-file \S+/body\.md", "--body-file <body>", self.read("calls.log")).splitlines()

    @property
    def bodies(self):
        return self.read("bodies.log")


class RedNightTest(NightCase):
    def test_with_no_open_issue_it_opens_one_with_what_came_out_red(self):
        self.assertEqual(0, self.report())
        self.assertEqual([SEARCH, CREATE], self.calls)
        self.assertEqual(ISSUE_BODY, self.bodies)
        self.assertNotIn("\x1b", self.bodies)
        self.assertNotIn(self.home, self.bodies)
        self.assertEqual(RED_HEADING + RED_DETAILS + CREATED, self.stdout)

    def test_with_the_issue_open_it_comments_on_it_and_writes_nothing_else(self):
        self.assertEqual(0, self.report(OPEN_ISSUES=OPEN))
        self.assertEqual([SEARCH, "gh issue comment 42 --body-file <body>"], self.calls)
        self.assertEqual(
            "La pasada del 2026-11-14 sigue en rojo, sobre `main` (commit `0123456`); su registro y sus trazas, en"
            f" `{FOLDER}`.\n\n{RED_DETAILS}",
            self.bodies,
        )
        self.assertEqual(RED_HEADING + RED_DETAILS, self.stdout)

    def test_without_a_usable_report_it_says_so_and_how_the_night_ended(self):
        said = (
            "La ejecución terminó en `cancelled` sin informe de las pruebas: lo que falló está antes o fuera de las"
            f" specs (servidores, tiempo agotado). Lo dice `{FOLDER}/night.log`.\n"
        )
        for report in (None, "", self.path("missing.json"), self.write("broken.json", "not json"), self.path("bin")):
            with self.subTest(REPORT=report):
                self.assertEqual(0, self.report(REPORT=report, RESULT="cancelled"))
                self.assertEqual(RED_HEADING + said + CREATED, self.stdout)
                self.assertEqual([SEARCH, CREATE], self.calls)

    def test_a_night_that_never_reached_the_specs_names_the_step_and_reads_no_report(self):
        for report in (self.red_report, self.write("array.json", "[]")):
            with self.subTest(REPORT=report):
                self.assertEqual(0, self.report(STEP="la BD del SaaS", REPORT=report, PUBLISH="false"))
                self.assertEqual(
                    RED_HEADING + "La pasada no llegó a las specs: falló «la BD del SaaS». Lo que dijo está en"
                    f" `{FOLDER}/night.log`.\n" + UNPUBLISHED,
                    self.stdout,
                )

    def test_a_run_stopped_in_global_setup_lists_its_own_error(self):
        self.assertEqual(0, self.report(REPORT=self.write("setup.json", SETUP), PUBLISH="false"))
        self.assertEqual(
            RED_HEADING + "0 en rojo · 0 bien · 0 saltadas\n\n- Error de la ejecución: Error: unapplied migrations"
            " (sale.0042)\n" + UNPUBLISHED,
            self.stdout,
        )

    def test_a_red_end_with_no_red_test_in_the_report_points_at_the_log(self):
        green = self.write("green.json", suite_of(spec("ok", 1, [{"projectName": "", "status": "expected"}])))
        self.assertEqual(0, self.report(REPORT=green, RESULT="timedout", PUBLISH="false"))
        self.assertEqual(
            RED_HEADING + "1 en rojo · 1 bien · 0 saltadas\n\n\nEl informe no tiene ninguna prueba en rojo, pero la"
            f" ejecución terminó en `timedout`: `{FOLDER}/night.log` dice por qué.\n" + UNPUBLISHED,
            self.stdout,
        )

    def test_unpublished_only_the_output_is_written(self):
        for publish in ("false", None, "", "TRUE"):
            with self.subTest(PUBLISH=publish):
                self.assertEqual(0, self.report(PUBLISH=publish, OPEN_ISSUES=OPEN))
                self.assertEqual([], self.calls)
                self.assertEqual(RED_HEADING + RED_DETAILS + UNPUBLISHED, self.stdout)


class GreenNightTest(NightCase):
    def test_a_green_night_closes_the_open_issue(self):
        self.assertEqual(0, self.report(OPEN_ISSUES=OPEN, RESULT="success", REPORT=self.path("missing.json")))
        closing = "La pasada del 2026-11-14 ha salido entera en verde sobre `main` (commit `0123456`). Se cierra."
        self.assertEqual([SEARCH, f"gh issue close 42 --reason completed --comment {closing}"], self.calls)
        self.assertEqual(closing + "\n", self.bodies)
        self.assertEqual(GREEN_OUTPUT, self.stdout)

    def test_a_green_night_with_no_open_issue_writes_none(self):
        self.assertEqual(0, self.report(RESULT="success", STEP="ignored"))
        self.assertEqual([SEARCH], self.calls)
        self.assertEqual(GREEN_OUTPUT, self.stdout)

    def test_an_unpublished_green_night_only_writes_its_output(self):
        self.assertEqual(0, self.report(OPEN_ISSUES=OPEN, RESULT="success", PUBLISH="false"))
        self.assertEqual([], self.calls)
        self.assertEqual(GREEN_OUTPUT, self.stdout)


class FailureTest(NightCase):
    def test_a_gh_that_fails_fails_the_report_with_its_exit_code_after_the_output(self):
        cases = [
            ({"GH_FAILS": "1"}, 1, [SEARCH], RED_HEADING + RED_DETAILS),
            ({"GH_FAILS": "4"}, 4, [SEARCH], RED_HEADING + RED_DETAILS),
            ({"GH_FAILS": "3", "RESULT": "success", "OPEN_ISSUES": OPEN}, 3, [SEARCH], GREEN_OUTPUT),
            ({"GH_FAILS": "7", "GH_FAILS_ON": "issue create"}, 7, [SEARCH, CREATE], RED_HEADING + RED_DETAILS),
            ({"GH_FAILS": "8", "GH_FAILS_ON": "issue comment", "OPEN_ISSUES": OPEN}, 8,
             [SEARCH, "gh issue comment 42 --body-file <body>"], RED_HEADING + RED_DETAILS),
            ({"GH_FAILS": "6", "GH_FAILS_ON": "issue close", "OPEN_ISSUES": OPEN, "RESULT": "success"}, 6, None,
             GREEN_OUTPUT),
        ]
        for settings, code, calls, output in cases:
            with self.subTest(**settings):
                self.assertEqual(code, self.report(**settings))
                self.assertIn("HTTP 502", self.stderr)
                self.assertEqual(output, self.stdout)
                if calls is not None:
                    self.assertEqual(calls, self.calls)

    def test_an_answer_of_gh_that_is_no_list_of_issues_stops_the_report(self):
        for answer in ("not json", "5", "[5]"):
            with self.subTest(answer=answer):
                self.assertEqual(5, self.report(OPEN_ISSUES=answer))
                self.assertEqual([SEARCH], self.calls)

    def test_a_missing_or_empty_setting_stops_it_before_anything(self):
        for name in SETTINGS:
            for value in (None, ""):
                with self.subTest(setting=name, value=value):
                    self.assertEqual(1, self.report(**{name: value}))
                    self.assertIn(name, self.stderr)
                    self.assertEqual(([], ""), (self.calls, self.stdout))

    def test_without_a_home_it_stops_before_anything(self):
        self.assertEqual(1, self.report(HOME=None, RUN_DIR="/srv/night"))
        self.assertIn("HOME", self.stderr)
        self.assertNotIn("Traceback", self.stderr)
        self.assertEqual(([], ""), (self.calls, self.stdout))

    def test_a_report_it_cannot_read_through_stops_it_before_the_output(self):
        for result in ("failure", "success"):
            with self.subTest(RESULT=result):
                self.assertEqual(5, self.report(REPORT=self.write("array.json", "[]"), RESULT=result))
                self.assertEqual(([], ""), (self.calls, self.stdout))
                self.assertIn("stats", self.stderr)


class DefaultsTest(NightCase):
    def test_the_night_is_today_in_local_time_unless_given(self):
        # Fourteen hours ahead of UTC and twelve behind: at any hour one of the two is on another day than UTC.
        for day, zone in ((None, "Etc/GMT-14"), ("", "Etc/GMT+12")):
            with self.subTest(DAY=day, TZ=zone):
                before = datetime.datetime.now(ZoneInfo(zone)).date().isoformat()
                self.assertEqual(0, self.report(DAY=day, TZ=zone, RESULT="success", PUBLISH="false"))
                after = datetime.datetime.now(ZoneInfo(zone)).date().isoformat()
                self.assertIn(self.stdout.split("La pasada del ")[1][:10], (before, after))

    def test_the_folder_is_written_from_home_only_when_it_is_inside_it(self):
        cases = [
            ("/Users/ioan", "/Users/ioan/n/1", "~/n/1"), ("/Users/ioan", "/srv/n", "/srv/n"),
            ("/Users/ioan", "/Users/ioan", "/Users/ioan"), ("/Users/ioan", "/Users/ioanb/n", "/Users/ioanb/n"),
            ("/Users/ioan/", "/Users/ioan/n", "/Users/ioan/n"), ("", "/srv/n", "~/srv/n"), ("/a[b]", "/a[b]/n", "~/n"),
            ("/Users/ioan", "/backup/Users/ioan/n", "/backup/Users/ioan/n"),
        ]
        for home, folder, written in cases:
            with self.subTest(HOME=home, RUN_DIR=folder):
                self.assertEqual(0, self.report(HOME=home, RUN_DIR=folder, PUBLISH="false"))
                self.assertIn(f", en `{written}`.\n", self.stdout)

    def test_the_output_is_utf_8_whatever_the_locale_says(self):
        self.assertEqual(0, self.report(PUBLISH="false", PYTHONIOENCODING="ascii", LC_ALL="C"))
        self.assertEqual(RED_HEADING + RED_DETAILS + UNPUBLISHED, self.stdout)


class NewestIssueTest(unittest.TestCase):
    def test_it_is_the_highest_number_among_the_issues_of_exactly_that_title(self):
        def issues(*numbers, title=TITLE):
            return json.dumps([{"number": number, "title": title} for number in numbers])

        cases = [
            ("", ""), ("[]", ""), (issues(7, title=TITLE + " (otra)"), ""), (issues(42, 44), "44"),
            (json.dumps({"a": {"number": 7, "title": TITLE}}), "7"), (issues(0), "0"), (issues(False), ""),
            (issues(None), ""), (issues(3) + "\n" + issues(5), "3\n5"),
        ]
        for answer, number in cases:
            with self.subTest(answer=answer):
                self.assertEqual(number, e2e_report.newest_issue(answer))


class ReadingTest(unittest.TestCase):
    """What the report lists, read from Playwright's JSON with jq's rules."""

    def listing(self, *documents, result="failure"):
        return e2e_report.listing(night(result), list(documents))

    def listed(self, test):
        return self.listing(lines_of(test)).splitlines()[2]

    def test_a_message_keeps_its_first_line_without_colours_cut_at_200_characters(self):
        long = "ñ" * 150 + "\x1b[31m" + "🙂" * 100 + "\nnext"
        self.assertEqual("- `a.spec.ts:1` › t — " + "ñ" * 150 + "🙂" * 50, self.listed(red(error(long))))
        self.assertTrue(self.listed(red(error("a\x1b[1;31mb\x1b[Kc\x1b[mz"))).endswith(" — ab\x1b[Kcz"))

    def test_a_red_test_with_no_message_left_is_written_with_null(self):
        for test in (red(), {**red(), "results": []}, red(error("first"), None), red(error("first"), {}),
                     red(error(None)), red(error(False)), red(error("")), red(error("\x1b[31m\x1b[0m"))):
            with self.subTest(test=test):
                self.assertEqual("- `a.spec.ts:1` › t — null", self.listed(test))

    def test_a_message_whose_first_line_is_empty_gets_no_suffix(self):
        self.assertEqual("- `a.spec.ts:1` › t", self.listed(red(error("\nsecond"))))

    def test_only_the_last_result_counts(self):
        self.assertTrue(self.listed(red(error("first"), error("last"))).endswith("› t — last"))

    def test_a_project_is_named_only_when_it_has_a_name(self):
        for project, prefix in (("", ""), (None, ""), (False, ""), ("móvil", "[móvil] "), (0, "[0] "),
                                ({"a": [1]}, '[{"a":[1]}] ')):
            with self.subTest(project=project):
                self.assertEqual(f"- `{prefix}a.spec.ts:1` › t — m", self.listed(red(error("m"), project=project)))
        self.assertEqual("- `a.spec.ts:1` › t — m", self.listed({"status": "unexpected", "results": [error("m")]}))

    def test_specs_come_before_the_describes_inside_them_and_the_file_title_is_left_out(self):
        nested = {"suites": [{
            "title": "top", "file": "f",
            "suites": [{"title": "d1", "specs": [spec("in d1", 5, [red(error("e1"))])],
                        "suites": [{"title": "d2", "specs": [spec("in d2", 6, [red(error("e2"))])]}]}],
            "specs": [spec("top spec", 2, [red(error("e0"))])],
        }], "stats": STATS}
        self.assertEqual(
            ["- `a.spec.ts:2` › top spec — e0", "- `a.spec.ts:5` › d1 › in d1 — e1",
             "- `a.spec.ts:6` › d1 › d2 › in d2 — e2"],
            self.listing(nested).splitlines()[2:],
        )

    def test_any_value_is_written_as_jq_writes_it(self):
        odd = {"suites": [{"title": "s", "suites": [{"title": None, "suites": [{"title": 7, "suites": [{
            "title": True,
            "specs": [{"title": 1.5, "file": None, "line": "L", "tests": [red(error("m"))]}],
        }]}]}]}], "stats": {"unexpected": {"a": [1, "ñ"]}, "expected": 2.0, "skipped": None}}
        self.assertEqual(
            ['{"a":[1,"ñ"]} en rojo · 2.0 bien · null saltadas', "", "- `null:L` ›  › 7 › true › 1.5 — m"],
            self.listing(odd).splitlines(),
        )
        nulls = self.listing({"stats": None}, result="success")
        self.assertEqual("null en rojo · null bien · null saltadas\n\n", nulls)

    def test_a_run_error_without_a_message_is_written_as_null(self):
        for errors in ([{}], [None], [{"message": ""}], [{"message": None}]):
            with self.subTest(errors=errors):
                self.assertIn("\n- Error de la ejecución: null\n", self.listing({"errors": errors, "stats": STATS}))

    def test_lists_may_be_objects_and_anything_else_lists_nothing(self):
        as_objects = {"suites": {"x": {"title": "x", "specs": {"s": spec("o", 3, {"k": red(error("m"))})}}},
                      "errors": {"e": {"message": "from an object"}}, "stats": STATS}
        self.assertEqual(["- `a.spec.ts:3` › o — m", "- Error de la ejecución: from an object"],
                         self.listing(as_objects).splitlines()[2:])
        nothing = {"suites": [{"title": "s", "specs": 5, "suites": "x"}], "errors": 5, "stats": STATS}
        self.assertEqual(["1 en rojo · 1 bien · 0 saltadas", ""], self.listing(nothing).splitlines()[:2])

    def test_a_line_starting_with_a_dash_anywhere_counts_as_a_listed_failure(self):
        dashed = {"stats": {"unexpected": "a\n- b", "expected": 0, "skipped": 0}}
        self.assertEqual("a\n- b en rojo · 0 bien · 0 saltadas\n\n", self.listing(dashed))
        negative = {"stats": {"unexpected": -1, "expected": 0, "skipped": 0}}
        self.assertIn("El informe no tiene ninguna prueba en rojo", self.listing(negative))

    def test_each_json_document_of_the_report_is_read(self):
        expected = ["0 en rojo · 0 bien · 0 saltadas", "2 en rojo · 1 bien · 1 saltadas", "",
                    "- Error de la ejecución: Error: unapplied migrations (sale.0042)", *RED_DETAILS.splitlines()[2:]]
        self.assertEqual(expected, self.listing(SETUP, RED).splitlines())

    def test_what_jq_could_not_read_through_stops_the_report(self):
        refused = [
            [], "x", 5, True, {"stats": "x"}, suite_of({"title": "t", "file": "f", "line": 1}),
            suite_of(spec("t", 1, None)), suite_of(spec("t", 1, "x")), suite_of(None), suite_of(5),
            {"suites": [5], "stats": STATS}, {"suites": [{"title": "s", "suites": ["x"]}], "stats": STATS},
            suite_of(spec(["a"], 1, [red(error("m"))])), suite_of(spec({"a": 1}, 1, [red(error("m"))])),
            lines_of(red(error(5))), lines_of(red(error(0))), lines_of({**red(), "results": {"a": 1}}),
            lines_of({**red(), "results": "abc"}), lines_of(red({"error": "boom"})), lines_of(5),
            {"errors": ["x"], "stats": STATS}, lines_of(red(5)),
        ]
        for document in refused:
            with self.subTest(document=document), self.assertRaises(e2e_report.Refused) as refusal:
                self.listing(document)
            self.assertEqual(5, refusal.exception.code)


class ReadReportTest(unittest.TestCase):
    def read(self, content):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            path.write_text(content, encoding="utf-8")
            return e2e_report.read_report(str(path))

    def test_no_readable_report_is_no_report(self):
        for content in ("", "  \n\t ", "{not json", "null", "false", "{} null", "{} x"):
            with self.subTest(content=content):
                self.assertIsNone(self.read(content))
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(e2e_report.read_report(folder))
            self.assertIsNone(e2e_report.read_report(str(Path(folder) / "missing.json")))

    def test_a_report_is_read_as_its_json_documents(self):
        self.assertEqual([{"a": 1}], self.read('{"a": 1}'))
        self.assertEqual([{}, []], self.read(" {}\n[] \n"))
        self.assertEqual([True], self.read("true"))


if __name__ == "__main__":
    unittest.main()
