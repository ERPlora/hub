#!/usr/bin/env python3
"""The report of the Hub's nightly e2e run (scripts/nightly_e2e.py): lists what came out red, from Playwright's
JSON report, in its output, and keeps ONE open issue about it: a red night opens it (or comments on it when it is
already open) and the first green night closes it.

  RESULT=<success|anything else> SHA=<commit of main> RUN_DIR=<the night's folder> [REPORT=<json report>] \
    [STEP=<the step before the specs that failed>] PUBLISH=true|false GH_REPO=<owner/repo> \
    python3 scripts/e2e_report.py

Every result other than `success` is red. A missing or unreadable report is said, not hidden: the night stopped before
or outside the specs, and STEP names where when it is known. Only PUBLISH=true writes issues; otherwise the output is
all. A gh call that fails fails the report with gh's exit code. RUN_DIR is written from ~ (the Mac's user path never
reaches GitHub). Optional: DAY (the night's date, default today in local time).

The report is read with jq's rules, which the output and the issue keep: a value is written as jq writes it (null,
numbers, objects as compact JSON), a list may also be an object, and a value jq could not index or iterate stops the
report with jq's exit code, 5. Only the standard library: the Mac runs it with its own python3.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

TITLE = "Pruebas de navegador del Hub en rojo en la pasada nocturna"
SETTINGS = ("RESULT", "SHA", "RUN_DIR")
REFUSED = 5
COLOUR = re.compile(r"\x1b\[[0-9;]*m")
BLANK = re.compile(r"[ \t\n\r]*")

STEPPED = "La pasada no llegó a las specs: falló «{step}». Lo que dijo está en `{folder}/night.log`.\n"
NO_REPORT = (
    "La ejecución terminó en `{result}` sin informe de las pruebas: lo que falló está antes o fuera de las specs"
    " (servidores, tiempo agotado). Lo dice `{folder}/night.log`.\n"
)
NOTHING_RED = (
    "\nEl informe no tiene ninguna prueba en rojo, pero la ejecución terminó en `{result}`: `{folder}/night.log` dice"
    " por qué.\n"
)
ISSUE_OPENING = (
    "## Qué pasa\n"
    "Cada noche se prueban solas, en un navegador, todas las pantallas del Hub sobre la última versión, y esta noche"
    " alguna ha fallado. Puede ser un fallo real que ya está en producción o una prueba que se ha quedado vieja: hasta"
    " que alguien lo mire no se sabe.\n"
    "\n"
    "## Propuesta\n"
    "Mirar cada prueba de la lista: si el fallo es del producto, arreglarlo con su prueba; si la prueba se quedó vieja,"
    " ponerla al día. Esta issue se cierra sola la primera noche en que la pasada salga entera en verde.\n"
    "\n"
    "## Detalle técnico\n"
    "- Pasada del {day} sobre `main` (commit `{commit}`), en el Mac. El registro de la noche (`night.log`) y las trazas"
    " y capturas de cada fallo (`test-results/`), en `{folder}`.\n"
    "- Una spec se repite en una pila propia (`tests/e2e/README.md`, «Varias ejecuciones a la vez») con `CI=1 pnpm e2e"
    " tests/e2e/<spec>`, o con la misma pila de la noche: `python3 scripts/nightly_e2e.py --no-publish --spec"
    " tests/e2e/<spec>`.\n"
    "\n"
)
ISSUE_CLOSING = (
    "\n"
    "## Origen\n"
    "- Cómo se llegó: la pasada nocturna de las pruebas de navegador del Hub (`scripts/nightly_e2e.py`, que"
    " lanza launchd en el Mac).\n"
    "- Sale de #877\n"
    "- La introdujo una PR: no comprobado — la pasada no sabe qué cambio la rompió; se busca entre los commits desde la"
    " última noche en verde.\n"
    "\n"
    "## Cómo se reproduce\n"
    "- Test: las specs de la lista, que fallan sobre `origin/main@{commit}` (`CI=1 pnpm e2e tests/e2e/<spec>` en una"
    " pila propia).\n"
    "\n"
    "## Flujo\n"
    "- Flujo: ninguno — la pasada no sabe qué flujo prueba cada spec; el triaje lo pone al leerla.\n"
)


class Refused(Exception):
    """Stops the report with an exit code: a value jq could not read through, or a gh call that failed."""

    def __init__(self, code: int, message: str = "") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Night:
    result: str
    commit: str
    day: str
    folder: str
    publish: bool


def field(value, key: str):
    """jq's `.key`: null on null and for a missing key; anything but an object or null is refused."""
    if isinstance(value, dict):
        return value.get(key)
    if value is None:
        return None
    raise Refused(REFUSED, f"cannot index {type(value).__name__} with {key!r}")


def each(value) -> list:
    """jq's `.[]`: the items of a list or the values of an object; anything else is refused."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    raise Refused(REFUSED, f"cannot iterate over {type(value).__name__}")


def each_if_any(value) -> list:
    """jq's `.[]?`: like each, with nothing for what cannot be iterated."""
    return each(value) if isinstance(value, (list, dict)) else []


def last(value):
    """jq's `last`: the last item of a list, null for an empty one or for null; anything else is refused."""
    if isinstance(value, list):
        return value[-1] if value else None
    if value is None:
        return None
    raise Refused(REFUSED, f"cannot index {type(value).__name__} with a number")


def or_empty(value):
    """jq's `// ""`."""
    return "" if value is None or value is False else value


def text(value) -> str:
    """A value inside a jq string: a string as it is, anything else as compact JSON."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def joined(titles: list) -> str:
    """jq's `join(" › ")`: null as nothing, numbers and booleans as JSON; a list or an object is refused."""
    for title in titles:
        if isinstance(title, (list, dict)):
            raise Refused(REFUSED, f"cannot join a {type(title).__name__}")
    return " › ".join("" if title is None else text(title) for title in titles)


def plain(message):
    """The first line of a message without colour codes, cut at 200 characters; null when nothing is left."""
    if not isinstance(message, str):
        raise Refused(REFUSED, f"{type(message).__name__} cannot be matched, as it is not a string")
    message = COLOUR.sub("", message)
    return message.split("\n")[0][:200] if message else None


def project(test) -> str:
    """The test's project in brackets, or nothing when it has no name (the Hub runs a single, unnamed one)."""
    name = or_empty(field(test, "projectName"))
    return "" if name == "" else f"[{text(name)}] "


def specs(suite, path: list):
    """Each spec of a suite and of the describes inside it, with the titles that lead to it."""
    for spec in each_if_any(field(suite, "specs")):
        yield [*path, field(spec, "title")], spec
    for child in each_if_any(field(suite, "suites")):
        yield from specs(child, [*path, field(child, "title")])


def tests(report):
    """Each test of a report, with its spec and the titles that lead to it; a file's own title is left out."""
    for suite in each_if_any(field(report, "suites")):
        for path, spec in specs(suite, []):
            for test in each(field(spec, "tests")):
                yield path, spec, test


def red_line(path: list, spec, test) -> str | None:
    """The markdown line of a test that came out red, with the first line of its error; None for any other test."""
    if field(test, "status") != "unexpected":
        return None
    message = plain(or_empty(field(field(last(field(test, "results")), "error"), "message")))
    where = f"{project(test)}{text(field(spec, 'file'))}:{text(field(spec, 'line'))}"
    line = f"- `{where}` › {joined(path)}"
    return line if message == "" else f"{line} — {text(message)}"


def red_lines(report) -> list[str]:
    """The red tests of a report and the run's own errors, one markdown line each."""
    lines = [line for line in (red_line(*found) for found in tests(report)) if line is not None]
    errors = each_if_any(field(report, "errors"))
    return lines + [f"- Error de la ejecución: {text(plain(or_empty(field(error, 'message'))))}" for error in errors]


def counts(report) -> str:
    stats = field(report, "stats")
    red, passed, skipped = (text(field(stats, key)) for key in ("unexpected", "expected", "skipped"))
    return f"{red} en rojo · {passed} bien · {skipped} saltadas"


def listing(night: Night, documents: list) -> str:
    """The counts and a line per failure of the report's documents, or why a red night lists none."""
    found = "".join(f"{counts(document)}\n" for document in documents) + "\n"
    found += "".join(f"{line}\n" for document in documents for line in red_lines(document))
    if night.result != "success" and not any(line.startswith("- ") for line in found.split("\n")):
        found += NOTHING_RED.format(result=night.result, folder=night.folder)
    return found


def details(night: Night, step: str, report: str) -> str:
    """What came out red, for the output and the issue: the step that failed before the specs, the report's listing,
    or why there is no report."""
    if step:
        return STEPPED.format(step=step, folder=night.folder)
    documents = read_report(report) if report else None
    if documents is None:
        return NO_REPORT.format(result=night.result, folder=night.folder)
    return listing(night, documents)


def documents_of(raw: str) -> list:
    """The JSON documents of a text, one after another; ValueError when one of them is no JSON."""
    decoder = json.JSONDecoder()
    found = []
    at = BLANK.match(raw).end()
    while at < len(raw):
        document, at = decoder.raw_decode(raw, at)
        found.append(document)
        at = BLANK.match(raw, at).end()
    return found


def read_report(path: str) -> list | None:
    """The report's JSON documents; None when there is none to read: missing, empty, no JSON, or ending in null or
    false."""
    try:
        documents = documents_of(Path(path).read_bytes().decode("utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    if not documents or documents[-1] is None or documents[-1] is False:
        return None
    return documents


def newest_issue(answer: str) -> str:
    """The number of the newest open issue of exactly TITLE in gh's answer, or "" when there is none."""
    try:
        documents = documents_of(answer)
    except ValueError as error:
        raise Refused(REFUSED, f"gh's answer is no JSON: {error}") from error
    newest = []
    for document in documents:
        number = max((field(issue, "number") for issue in each(document) if field(issue, "title") == TITLE),
                     default=None)
        if number is not None and number is not False:
            newest.append(text(number))
    return "\n".join(newest)


def open_issue() -> str:
    """The open issue of exactly that title: searched by its title, never among the latest issues, where a busy repo
    would bury it and a second one would be opened."""
    search = ["issue", "list", "--state", "open", "--search", f'"{TITLE}" in:title', "--limit", "50"]
    answer = subprocess.run(["gh", *search, "--json", "number,title"], stdout=subprocess.PIPE, check=False)
    number = newest_issue(answer.stdout.decode("utf-8", errors="replace"))
    if answer.returncode != 0:
        raise Refused(answer.returncode)
    return number


def gh(*args: str) -> None:
    """A gh call that writes an issue; its output follows the report's, and its failure fails the report."""
    done = subprocess.run(["gh", *args], check=False)
    if done.returncode != 0:
        raise Refused(done.returncode)


def gh_with_body(args: list[str], body: str) -> None:
    with tempfile.TemporaryDirectory() as work:
        path = Path(work) / "body.md"
        path.write_text(body, encoding="utf-8")
        gh(*args, "--body-file", str(path))


def say(content: str) -> None:
    """Writes to the output before gh does: gh's own output comes after it, as in a terminal."""
    sys.stdout.write(content)
    sys.stdout.flush()


def green(night: Night) -> None:
    say(f"## Pruebas de navegador del Hub: en verde\n\nLa pasada del {night.day} ha salido en verde (commit"
        f" `{night.commit}`).\n")
    if not night.publish:
        return
    number = open_issue()
    if number:
        closing = f"La pasada del {night.day} ha salido entera en verde sobre `main` (commit `{night.commit}`)."
        gh("issue", "close", number, "--reason", "completed", "--comment", f"{closing} Se cierra.")


def red(night: Night, found: str) -> None:
    say(f"## Pruebas de navegador del Hub: en rojo\n\nLa pasada del {night.day}, commit `{night.commit}`, en"
        f" `{night.folder}`.\n\n{found}")
    if not night.publish:
        say("\nSin publicar: no se escribe ninguna issue.\n")
        return
    number = open_issue()
    if number:
        still = (f"La pasada del {night.day} sigue en rojo, sobre `main` (commit `{night.commit}`); su registro y sus"
                 f" trazas, en `{night.folder}`.\n\n")
        gh_with_body(["issue", "comment", number], still + found)
        return
    opening = ISSUE_OPENING.format(day=night.day, commit=night.commit, folder=night.folder)
    body = opening + found + ISSUE_CLOSING.format(commit=night.commit)
    gh_with_body(["issue", "create", "--title", TITLE, "--label", "prio:P1"], body)


def from_home(folder: str, home: str) -> str:
    """The folder from ~ when it is inside HOME, so the Mac's user path never reaches GitHub."""
    inside = f"{home}/"
    return f"~/{folder[len(inside):]}" if folder.startswith(inside) else folder


def main() -> int:
    # The output is UTF-8 whatever the locale says: the issue's text is Spanish, and the night's log keeps it.
    sys.stdout.reconfigure(encoding="utf-8")
    env = os.environ
    for name in SETTINGS:
        if not env.get(name):
            print(f"e2e_report.py: {name}: parameter null or not set", file=sys.stderr)
            return 1
    if "HOME" not in env:
        print("e2e_report.py: HOME: unbound variable", file=sys.stderr)
        return 1
    night = Night(
        result=env["RESULT"],
        commit=env["SHA"][:7],
        day=env.get("DAY") or datetime.date.today().isoformat(),
        folder=from_home(env["RUN_DIR"], env["HOME"]),
        publish=env.get("PUBLISH") == "true",
    )
    try:
        found = details(night, env.get("STEP", ""), env.get("REPORT", ""))
        if night.result == "success":
            green(night)
        else:
            red(night, found)
    except Refused as refusal:
        if str(refusal):
            print(f"e2e_report.py: {refusal}", file=sys.stderr)
        return refusal.code
    return 0


if __name__ == "__main__":
    sys.exit(main())
