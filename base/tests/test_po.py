"""The one reader of ``.po`` catalogues behind every app's translation guard, and that every app really goes through it.

The reader lived in 26 copies, one per ``apps/<app>/tests/test_i18n.py``, and the same hole (blind to a ``#, fuzzy``,
which gettext skips, so the screen says the English) was closed copy by copy (hub#486, hub#627, hub#726, hub#728). Its
behaviour is tested here, once; what each app keeps is its own guard, and the last tests here prove that guard goes red.
"""

import ast
from importlib import import_module
from pathlib import Path

import pytest
from babel.messages.pofile import PoFileError
from django.utils import translation
from django.utils.translation import gettext_lazy, pgettext_lazy

from base.tests.po import catalogue_key, missing_from_catalogue, po_entries, po_messages

ROOT = Path(__file__).resolve().parents[2]
HEADER = 'msgid ""\nmsgstr ""\n"Language: es\\n"\n'
CATALOGS = sorted(ROOT.glob("apps/*/locale/es/LC_MESSAGES/django.po"))
#: Who may spell out gettext's keywords: the reader itself and this file, which writes catalogues to test it.
READER = {Path(__file__).resolve(), ROOT / "base" / "tests" / "po.py"}


def write_po(tmp_path: Path, text: str) -> Path:
    po = tmp_path / "django.po"
    po.write_text(text, encoding="utf-8")
    return po


def test_a_fuzzy_mark_is_seen_on_its_own_entry_and_nothing_behind_it_inherits_it(tmp_path):
    """Neither the entry behind a mark nor the one behind a fuzzy header (what ``makemessages`` writes in a new catalog)
    is fuzzy, and the mark is seen above a ``msgctxt`` too."""
    po = write_po(
        tmp_path,
        "#, fuzzy\n"
        f"{HEADER}"
        "\n"
        'msgid "Behind the header"\n'
        'msgstr "Tras la cabecera"\n'
        "\n"
        "#, fuzzy\n"
        'msgid "Marked"\n'
        'msgstr "Marcada"\n'
        "\n"
        'msgid "Behind the mark"\n'
        'msgstr "Tras la marca"\n'
        "\n"
        "#, fuzzy\n"
        'msgctxt "a context"\n'
        'msgid "Marked with a context"\n'
        'msgstr "Marcada con contexto"\n'
        "\n"
        'msgid "Behind the context"\n'
        'msgstr "Tras el contexto"\n',
    )
    assert po_entries(po) == {
        "Behind the header": ("Tras la cabecera", False),
        "Marked": ("Marcada", True),
        "Behind the mark": ("Tras la marca", False),
        "a context\x04Marked with a context": ("Marcada con contexto", True),
        "Behind the context": ("Tras el contexto", False),
    }


def test_a_fuzzy_mark_is_seen_among_other_comments_and_without_blank_lines_between_entries(tmp_path):
    """``msgmerge`` writes the mark with the other flags and above the previous text (``#|``)."""
    po = write_po(
        tmp_path,
        f"{HEADER}"
        "\n"
        "#, fuzzy\n"
        'msgid "Plain"\n'
        'msgstr "Llano"\n'
        'msgid "Right after a fuzzy one"\n'
        'msgstr "Justo después"\n'
        "\n"
        "#. A note for the translator\n"
        "#: apps/demo/services.py:1\n"
        "#, fuzzy, python-format\n"
        '#| msgid "Before %(name)s"\n'
        'msgid "With comments %(name)s"\n'
        'msgstr "Con comentarios %(name)s"\n'
        "\n"
        "#, python-format, fuzzy\n"
        'msgid "Flag last %(name)s"\n'
        'msgstr "Marca al final %(name)s"\n'
        "\n"
        "#, python-format\n"
        'msgid "Only another flag %(name)s"\n'
        'msgstr "Solo otra marca %(name)s"\n'
        "\n"
        "#, fuzzy\n"
        'msgctxt "a menu"\n'
        'msgid "Clock in"\n'
        'msgstr "Fichar entrada"\n'
        'msgctxt "a menu"\n'
        'msgid "Clock out"\n'
        'msgstr ""\n'
        '"Fichar salida"\n',
    )
    assert po_entries(po) == {
        "Plain": ("Llano", True),
        "Right after a fuzzy one": ("Justo después", False),
        "With comments %(name)s": ("Con comentarios %(name)s", True),
        "Flag last %(name)s": ("Marca al final %(name)s", True),
        "Only another flag %(name)s": ("Solo otra marca %(name)s", False),
        "a menu\x04Clock in": ("Fichar entrada", True),
        "a menu\x04Clock out": ("Fichar salida", False),
    }


def test_a_header_right_above_the_first_entry_is_left_out(tmp_path):
    po = write_po(tmp_path, f'{HEADER}msgid "First"\nmsgstr "Primera"\n')
    assert po_entries(po) == {"First": ("Primera", False)}


def test_an_entry_without_its_spanish_says_so(tmp_path):
    po = write_po(tmp_path, f'{HEADER}\nmsgid "Empty"\nmsgstr ""\n')
    assert po_entries(po) == {"Empty": ("", False)}


def test_the_same_text_with_and_without_a_context_are_two_entries(tmp_path):
    po = write_po(
        tmp_path,
        f"{HEADER}\n"
        'msgid "Active"\nmsgstr "Activo"\n\n'
        'msgctxt "status"\nmsgid "Active"\nmsgstr "Activa"\n',
    )
    assert po_entries(po) == {"Active": ("Activo", False), "status\x04Active": ("Activa", False)}


def test_a_lazy_text_is_keyed_as_the_compiled_catalog_keys_it():
    """A ``gettext_lazy`` text by its English, a ``pgettext_lazy`` one as ``context\\x04English``: a text that goes back
    to ``_()`` while its entry keeps the context, or whose context has a typo, is missing from its catalogue (it would
    say another app's Spanish, hub#560)."""
    with translation.override("en"):
        assert catalogue_key(gettext_lazy("Open")) == "Open"
        assert catalogue_key(pgettext_lazy("sale", "Open")) == "sale\x04Open"
        assert catalogue_key("Open") == "Open"


def test_no_module_keys_a_lazy_text_by_itself():
    """Five ``test_i18n.py`` kept the same key of a lazy text, each its own copy: every test asks ``base.tests.po``."""
    tests = sorted((ROOT / "apps").glob("*/tests/*.py"))
    assert len(tests) > 100
    assert [str(path.relative_to(ROOT)) for path in tests if '"_args"' in path.read_text(encoding="utf-8")] == []


def statuses_po(tmp_path: Path) -> Path:
    """A catalogue with one text under a context and one without."""
    return write_po(
        tmp_path,
        f'{HEADER}\nmsgctxt "blocked time type"\nmsgid "Other"\nmsgstr "Otro"\n\nmsgid "Holiday"\nmsgstr "Festivo"\n',
    )


def test_a_text_is_looked_up_in_its_catalogue_by_its_whole_key(tmp_path):
    """A context with a typo, a ``pgettext_lazy`` that lost its context, or one whose entry has none: each is missing,
    and on screen it says the English (hub#975)."""
    po = statuses_po(tmp_path)
    found = {"blocked time type\x04Other", "Holiday"}
    assert missing_from_catalogue(found, po, more_than=1, with_context=1) == set()
    for key in ("blocked time types\x04Other", "Other", "blocked time type\x04Holiday"):
        assert missing_from_catalogue(found | {key}, po, more_than=1, with_context=1) == {key}


@pytest.mark.parametrize(
    ("more_than", "with_context"),
    [pytest.param(2, 1, id="too-few-texts"), pytest.param(1, 2, id="too-few-contexts")],
)
def test_a_collection_that_found_too_little_fails_instead_of_passing_blind(tmp_path, more_than, with_context):
    """Positive control: a collection that missed the app's texts, or read them with ``str()`` and so lost their
    contexts, would find nothing missing and pass — so it fails, saying what it found."""
    found = {"blocked time type\x04Other", "Holiday"}
    with pytest.raises(AssertionError, match="found 2 texts, 1 with a context"):
        missing_from_catalogue(found, statuses_po(tmp_path), more_than=more_than, with_context=with_context)


def test_no_catalogue_test_drops_the_context_of_a_key():
    """Eight ``test_i18n.py`` compared the catalogue's keys without their context (``split("\\x04")``) and stayed green
    when a ``pgettext_lazy`` lost its context or had a typo in it (hub#975): every test asks ``missing_from_catalogue``
    or compares whole keys."""
    tests = sorted((ROOT / "apps").glob("*/tests/*.py"))
    assert len(tests) > 100
    assert [
        str(path.relative_to(ROOT)) for path in tests if 'split("\\x04")' in path.read_text(encoding="utf-8")
    ] == []


def test_continuation_lines_and_escapes_are_read_as_the_compiled_catalog_says_them(tmp_path):
    po = write_po(
        tmp_path,
        f"{HEADER}\n"
        'msgctxt ""\n"a long "\n"context"\n'
        'msgid ""\n"First line\\n"\n"and \\"the\\" second\\t\\\\"\n'
        'msgstr ""\n"Primera línea\\n"\n"y \\"la\\" segunda\\t\\\\"\n',
    )
    assert po_entries(po) == {
        'a long context\x04First line\nand "the" second\t\\': ('Primera línea\ny "la" segunda\t\\', False)
    }


def test_a_plural_entry_gives_one_entry_per_form_as_the_compiled_catalog_keeps_them(tmp_path):
    po = write_po(
        tmp_path,
        'msgid ""\nmsgstr ""\n"Plural-Forms: nplurals=3; plural=n == 1 ? 0 : 2;\\n"\n\n'
        'msgid "%(n)s review"\nmsgid_plural "%(n)s reviews"\n'
        'msgstr[0] "%(n)s reseña"\nmsgstr[1] "%(n)s reseñas"\nmsgstr[2] ""\n\n'
        '#, fuzzy\nmsgctxt "a card"\nmsgid "%(n)s tip"\nmsgid_plural "%(n)s tips"\n'
        'msgstr[0] "%(n)s propina"\nmsgstr[1] "%(n)s propinas"\nmsgstr[2] "%(n)s propinas"\n',
    )
    assert po_entries(po) == {
        ("%(n)s review", 0): ("%(n)s reseña", False),
        ("%(n)s review", 1): ("%(n)s reseñas", False),
        ("%(n)s review", 2): ("", False),
        ("a card\x04%(n)s tip", 0): ("%(n)s propina", True),
        ("a card\x04%(n)s tip", 1): ("%(n)s propinas", True),
        ("a card\x04%(n)s tip", 2): ("%(n)s propinas", True),
    }


def test_an_obsolete_entry_is_left_out_and_its_fuzzy_mark_goes_with_it(tmp_path):
    """``makemessages`` keeps a message the code no longer says as ``#~``: gettext does not read it."""
    po = write_po(
        tmp_path,
        f"{HEADER}\n"
        'msgid "Live"\nmsgstr "Viva"\n\n'
        '#, fuzzy\n#~ msgid "Gone"\n#~ msgstr "Ida"\n\n'
        'msgid "Behind the obsolete one"\nmsgstr "Tras la obsoleta"\n',
    )
    assert po_entries(po) == {"Live": ("Viva", False), "Behind the obsolete one": ("Tras la obsoleta", False)}


@pytest.mark.parametrize(
    "broken",
    [
        pytest.param('msgid "No translation line"\n\nmsgid "Other"\nmsgstr "Otra"\n', id="msgid-without-msgstr"),
        pytest.param('msgid "A"\nmsgstr "B"\nnonsense\n', id="unknown-line"),
    ],
)
def test_a_catalog_that_cannot_be_read_fails_instead_of_passing(tmp_path, broken):
    with pytest.raises(PoFileError):
        po_entries(write_po(tmp_path, broken))


def test_the_messages_carry_what_a_guard_on_plurals_and_contexts_needs(tmp_path):
    """``po_messages`` is the same reading, entry by entry, for who needs the singular and the plural apart."""
    po = write_po(
        tmp_path,
        "#, fuzzy\n"
        'msgid ""\nmsgstr ""\n"Plural-Forms: nplurals=2; plural=n != 1;\\n"\n\n'
        'msgctxt "a card"\nmsgid "One"\nmsgid_plural "Many"\nmsgstr[0] "Una"\nmsgstr[1] "Muchas"\n\n'
        '#, fuzzy\nmsgid "Plain"\nmsgstr "Llano"\n\n'
        '#~ msgid "Gone"\n#~ msgstr "Ida"\n',
    )
    assert [(message.context, message.id, message.string, message.fuzzy) for message in po_messages(po)] == [
        ("a card", ("One", "Many"), ("Una", "Muchas"), False),
        (None, "Plain", "Llano", True),
    ]


def test_a_catalog_that_is_not_ours_can_be_read_despite_its_header(tmp_path):
    """Django's own ``djangojs.po`` declares two plural forms and writes three: gettext reads it, a guard on ours would
    not let that pass."""
    po = write_po(
        tmp_path,
        'msgid ""\nmsgstr ""\n"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n\n'
        'msgid "One"\nmsgid_plural "Many"\nmsgstr[0] "Una"\nmsgstr[1] "Muchas"\nmsgstr[2] "Muchas"\n',
    )
    with pytest.raises(PoFileError):
        po_messages(po)
    assert [message.string for message in po_messages(po, strict=False)] == [("Una", "Muchas")]


def first_entry(lines: list[str], keyword: str) -> int | None:
    """The line of the first translated entry that ``keyword`` opens: a ``msgctxt``, or a ``msgid`` with none above."""
    for n, line in enumerate(lines):
        if line.startswith(f"{keyword} ") and line != 'msgid ""':
            if keyword == "msgctxt" or not lines[n - 1].startswith("msgctxt "):
                return n
    return None


#: Every app with a catalogue and what its entries can open with: ``msgid`` and, if it has any, ``msgctxt``.
FUZZY_MARKS = [
    (path.parts[-5], keyword)
    for path in CATALOGS
    for keyword in ("msgid", "msgctxt")
    if first_entry(path.read_text(encoding="utf-8").splitlines(), keyword) is not None
]


def test_the_marks_reach_every_app_with_a_catalog():
    """Positive control of the next test: it runs on every app, not on a pattern that matches nothing."""
    assert len(CATALOGS) >= 27
    assert {app for app, _ in FUZZY_MARKS} == {path.parts[-5] for path in CATALOGS}


@pytest.mark.parametrize(("app", "keyword"), FUZZY_MARKS)
def test_a_fuzzy_translation_turns_the_apps_own_test_red(app, keyword, tmp_path, monkeypatch):
    """Each app's own guard, on its own catalogue with one ``#, fuzzy``: an app without the guard, or with a reader that
    does not see the mark, fails here by name (hub#640, hub#644, hub#648)."""
    module = import_module(f"apps.{app}.tests.test_i18n")
    module.test_every_entry_has_a_spanish_translation()  # green as it ships: the red below is the mark's

    lines = (module.LOCALE / "django.po").read_text(encoding="utf-8").splitlines()
    lines.insert(first_entry(lines, keyword), "#, fuzzy")
    write_po(tmp_path, "\n".join(lines) + "\n")
    monkeypatch.setattr(module, "LOCALE", tmp_path)

    with pytest.raises(AssertionError):
        module.test_every_entry_has_a_spanish_translation()


@pytest.mark.parametrize("label", ["base", "control"])
def test_the_platforms_catalogs_have_no_fuzzy_translation(label):
    """The platform has no ``test_i18n.py``, and its Spanish is on every screen of the shell."""
    entries = po_entries(ROOT / label / "locale" / "es" / "LC_MESSAGES" / "django.po")
    assert entries
    assert [key for key, (_, fuzzy) in entries.items() if fuzzy] == []


def reads_a_po_by_hand(source: str) -> bool:
    """Whether a module parses ``.po`` lines itself: it asks a line for a gettext keyword, by ``startswith`` or by ``re``."""
    asking = {"startswith", "match", "fullmatch", "search", "findall", "compile"}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) in asking:
            literals = [
                leaf.value
                for argument in node.args
                for leaf in ast.walk(argument)
                if isinstance(leaf, ast.Constant) and isinstance(leaf.value, str)
            ]
            if any(keyword in literal for literal in literals for keyword in ("msgid", "msgstr", "msgctxt")):
                return True
    return False


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param('if line.startswith(("msgid ", "msgstr ")):\n    pass\n', True, id="startswith"),
        pytest.param("""re.fullmatch(r'(msgctxt|msgid) "(.*)"', line)\n""", True, id="regex"),
        pytest.param("""assert 'msgid "Log out"' in catalogue\n""", False, id="a-look-at-the-text"),
        pytest.param('if line.startswith("#"):\n    pass\n', False, id="another-prefix"),
    ],
)
def test_the_check_tells_a_reader_of_its_own_from_a_look_at_the_text(source, expected):
    assert reads_a_po_by_hand(source) is expected


def test_no_module_keeps_a_reader_of_its_own():
    """A new copy is how the same fix came to be needed three times: every test asks ``base.tests.po``."""
    modules = [path for root in ("apps", "base", "control", "tests") for path in (ROOT / root).rglob("*.py")]
    assert len(modules) > 100
    copies = [
        str(path.relative_to(ROOT))
        for path in modules
        if path not in READER and "msg" in (text := path.read_text(encoding="utf-8")) and reads_a_po_by_hand(text)
    ]
    assert copies == []
