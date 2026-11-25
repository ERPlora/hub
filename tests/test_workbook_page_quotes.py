"""A quote in «…» in a WORKBOOK's «Cómo son las páginas» is a text the screen paints, word for word.

That section tells whoever maintains an app how its pages are built, and it names a tab, button, title, field or
notice by quoting it. A quote with a suffix, a cut or an old word sends the reader looking for a text that is not
there. So every quote is, whole, one of the Spanish texts painted on the app's pages: the app's own, ``base``'s or
those of the shared components of ``@erplora/ui``, from the frontend (``es.json``) or the server (``django.po``).
Another app's word is not quoted: its flow is cited by id, so renaming it there leaves no stale copy here. What is
not a text of the screen (an example amount, a test's name, a search term) goes without the quotes.

The section lives in the maintainers' part, which the English translation does not carry.
"""

import json
import re
from pathlib import Path

from base.catalog.workbooks import WORKBOOK
from base.tests.po import po_entries

REPO = Path(__file__).resolve().parent.parent
HEADING = re.compile(r"^(#{2,3}) Cómo son las páginas\b.*$", re.MULTILINE)
QUOTE = re.compile(r"«([^«»]*)»")

SAMPLE = """## Pantallas

«Guardar cambios» is a customer's line, not the section.

### Cómo son las páginas

- The footer says «Guardar» and «Ajustes
  guardados.»; the list opens on «Activas» and the form on «Ajustes guardados».
- A cut quote can wrap a line too: «Ajustes
  guardad».

#### A smaller heading stays inside: «Cargando»

## Lo que NO hace

«Borrar todo» is after the section.
"""


def words(value) -> set[str]:
    """Every text of a JSON catalogue, at any depth, with its spaces as the screen lays them out."""
    if isinstance(value, dict):
        return set().union(*map(words, value.values()))
    if isinstance(value, list):
        return set().union(*map(words, value))
    return {" ".join(value.split())} if isinstance(value, str) else set()


def spanish_words(folder: Path) -> set[str]:
    """The Spanish texts of a module: its frontend catalogue and the translations of its server one."""
    found: set[str] = set()
    for catalogue in [*folder.glob("frontend/locale/es.json"), *folder.glob("locales/es.json")]:
        found |= words(json.loads(catalogue.read_text(encoding="utf-8")))
    for po in folder.glob("locale/es/LC_MESSAGES/django.po"):
        found |= {" ".join(text.split()) for text, _fuzzy in po_entries(po).values()}
    return found


def shared_words() -> set[str]:
    """What ``base`` and the components of ``@erplora/ui`` paint on every app's pages."""
    components = (REPO / "packages" / "ui" / "src").rglob("locales")
    return set().union(spanish_words(REPO / "base"), *(spanish_words(folder.parent) for folder in components))


def misquotes(text: str, known: set[str]) -> list[tuple[int, str]]:
    """Each quote of the «Cómo son las páginas» section of ``text`` that no text of ``known`` says, whole."""
    heading = HEADING.search(text)
    if heading is None:
        return []
    level = len(heading.group(1))
    following = re.compile(rf"^#{{1,{level}}} ", re.MULTILINE).search(text, heading.end())
    end = following.start() if following else len(text)
    return [
        (text.count("\n", 0, quote.start()) + 1, said)
        for quote in QUOTE.finditer(text, heading.end(), end)
        if (said := " ".join(quote.group(1).split())) not in known
    ]


def test_only_a_quote_of_the_section_that_no_screen_text_says_whole_is_reported():
    known = {"Guardar", "Ajustes guardados.", "Activas", "Cargando…"}

    assert misquotes(SAMPLE, known) == [(8, "Ajustes guardados"), (9, "Ajustes guardad"), (12, "Cargando")]
    assert misquotes(SAMPLE.replace("### Cómo son", "### Cómo eran"), known) == []


def test_a_module_s_words_are_the_spanish_of_its_frontend_and_server_catalogues(tmp_path):
    (tmp_path / "frontend" / "locale").mkdir(parents=True)
    (tmp_path / "frontend" / "locale" / "es.json").write_text('{"a": {"save": "Guardar"}, "b": ["Mis\\n ausencias"]}', encoding="utf-8")
    (tmp_path / "frontend" / "locale" / "en.json").write_text('{"a": {"save": "Save"}}', encoding="utf-8")
    (tmp_path / "locale" / "es" / "LC_MESSAGES").mkdir(parents=True)
    (tmp_path / "locale" / "es" / "LC_MESSAGES" / "django.po").write_text(
        'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\nmsgid "Settings"\nmsgstr "Ajustes"\n',
        encoding="utf-8",
    )

    assert spanish_words(tmp_path) == {"Guardar", "Mis ausencias", "Ajustes"}


def test_the_shared_components_words_count_on_every_app_s_screen():
    data_table = REPO / "packages" / "ui" / "src" / "components" / "DataTable" / "locales" / "es.json"

    assert words(json.loads(data_table.read_text(encoding="utf-8"))) <= shared_words()


def test_every_quote_of_a_workbook_s_pages_section_is_a_text_its_screen_paints():
    shared = shared_words()
    scanned, problems = [], []
    for workbook in [REPO / "base" / WORKBOOK, *sorted((REPO / "apps").glob(f"*/{WORKBOOK}"))]:
        text = workbook.read_text(encoding="utf-8")
        if HEADING.search(text):
            scanned.append(workbook)
        problems += [
            f"{workbook.relative_to(REPO)}, line {line}: «{said}»"
            for line, said in misquotes(text, spanish_words(workbook.parent) | shared)
        ]

    assert scanned, "no WORKBOOK has a «Cómo son las páginas» section: has its heading changed?"
    assert not problems, (
        "These quotes are not, whole, a text the app's screen paints in Spanish. Quote the exact text, cite "
        "another app's flow by its id, or drop the quotes from what is not a text of the screen:\n"
        + "\n".join(problems)
    )
