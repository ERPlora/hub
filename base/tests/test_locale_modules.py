"""A module's Spanish is its own: no earlier app's translation of the same message speaks for it.

Django joins every catalogue of a language in one, and for each message the first app in ``INSTALLED_APPS`` that
translates it wins. A module that says a message an earlier one already translates otherwise comes out in Spanish
with the other's words: the cash register's ``by`` read the customers' «por» where it means «quién». The case counts
against the later module: that is the one Spanish gets wrong, and its cure lives there — the text with a sense of its
own goes through ``pgettext_lazy`` with a context of its own, or says it the earlier way when the sense is the same.
The earlier module says it first and is right; moving a module in ``INSTALLED_APPS`` would only move its cases onto
another. Django's own apps (``admin``, ``auth``…) come before every module and count here too (``auth``'s ``active``
is «activo»); the platform's (``control``, ``base``) and ``live``'s messages without context against the modules
are ``base/tests/test_locale_platform.py`` and ``tests/test_live_translations.py``, and their contexted ones count
here. A contexted message only meets the same message with the same context; plural forms are left out.

The catalogue is not all a module says: its code may say a message its catalogue does not translate — a text it put
back without its context (``_("active")`` where the catalogue keeps only ``pgettext``'s ``pricing`` one), or one it
never wrote down —, and then Spanish says it with the words of whichever app translates it. So the count also reads
each module's code (``said_in_code``: the messages it hands the gettext family as written, outside its tests and
migrations) and counts each one its catalogue lacks that another app translates, by the same rule.
"""

import ast
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext

from base.tests.test_locale_platform import PLATFORM, catalogue

SPANISH = Path("locale", "es", "LC_MESSAGES", "django.mo")

#: The messages each module says (in its catalogue or only in its code) and Spanish shows in another app's words, by
#: module. Only ever lower: a module
#: that gives such a text its own context (or the earlier wording) lowers its number here, and none comes in.
SHADOWED = {
    "appointment": 7,
    "cash_register": 5,
    "combo": 1,
    "flow": 7,
    "invoice": 9,
    "kitchen": 7,
    "modifier": 2,
    "online_booking": 1,
    "reservation": 2,
    "sale": 6,
    "service": 4,
    "task": 1,
    "tax": 1,
    "verifactu": 7,
    "website": 5,
    "whatsapp_inbox": 3,
}


def spoken() -> list[tuple[str, str, str, str, str]]:
    """Every message each module says: ``(module, message, its text, first app, Spanish's text)``, the first app being
    the earliest in ``INSTALLED_APPS`` that translates the message (the module itself, or one before it)."""
    modules = Path(settings.BASE_DIR, "apps")
    first: dict[str, tuple[str, str]] = {}
    said: list[tuple[str, str, str, str, str]] = []
    for config in apps.get_app_configs():
        path = Path(config.path, SPANISH)
        if not path.exists():
            continue
        module = Path(config.path).parent == modules
        for message, text in catalogue(path).items():
            app, shown = first.setdefault(message, (config.label, text))
            if module:
                said.append((config.label, message, text, app, shown))
    assert len({module for module, *_ in said}) > 1, "fewer than two modules have a Spanish catalogue: the check would pass on nothing"
    return said


#: The gettext family by what it takes: a message, or a context and a message (``ngettext``'s plurals are left out).
SAYS = {"gettext", "gettext_lazy", "gettext_noop"}
SAYS_IN_CONTEXT = {"pgettext", "pgettext_lazy"}


def said_in(source: str) -> list[str]:
    """The messages ``source`` hands the gettext family as written (a literal, not a variable): imported from
    ``django.utils.translation`` under any name (``gettext_lazy as _``) or called on ``translation``; a contexted one
    keyed ``context\x04message``, as the catalogue keeps it."""
    tree = ast.parse(source)
    names = {
        alias.asname or alias.name: alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "django.utils.translation"
        for alias in node.names
    }
    said: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = node.func
        if isinstance(called, ast.Name):
            function = names.get(called.id)
        elif isinstance(called, ast.Attribute) and isinstance(called.value, ast.Name) and called.value.id == "translation":
            function = called.attr
        else:
            continue
        texts = [arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None for arg in node.args]
        if function in SAYS and texts[:1] and texts[0] is not None:
            said.append(texts[0])
        elif function in SAYS_IN_CONTEXT and len(texts) >= 2 and None not in texts[:2]:
            said.append(f"{texts[0]}\x04{texts[1]}")
    return said


def said_in_code(config) -> set[str]:
    """Every message the module ``config`` hands the gettext family in its own code, outside its tests and
    migrations (they are no text a person reads)."""
    root = Path(config.path)
    return {
        message
        for path in sorted(root.rglob("*.py"))
        if path.relative_to(root).parts[0] not in ("tests", "migrations")
        for message in said_in(path.read_text(encoding="utf-8"))
    }


def counts(app: str, message: str) -> bool:
    """Whether a message ``app`` translates counts against a module here: the platform's and ``live``'s without
    context are their own tests'."""
    return app not in (*PLATFORM, "live") or "\x04" in message


def said_only_in_code() -> list[tuple[str, str, str, str]]:
    """Every message a module's code says that its catalogue does not translate and another app does: ``(module,
    message, that app, Spanish's text)``."""
    modules = Path(settings.BASE_DIR, "apps")
    first: dict[str, tuple[str, str]] = {}
    own: dict[str, dict[str, str]] = {}
    for config in apps.get_app_configs():
        path = Path(config.path, SPANISH)
        entries = catalogue(path) if path.exists() else {}
        for message, text in entries.items():
            first.setdefault(message, (config.label, text))
        if Path(config.path).parent == modules:
            own[config.label] = entries
    return [
        (module, message, *first[message])
        for module in own
        for message in sorted(said_in_code(apps.get_app_config(module)))
        if message not in own[module] and message in first and first[message][1] != message.rpartition("\x04")[2]
    ]


def shadowed() -> dict[str, list[str]]:
    """Each module's messages that Spanish shows in another app's words, by module: one of its catalogue an earlier
    app translates otherwise, or one only its code says that another app translates; the platform's and ``live``'s
    without context are their own tests' (which leave the contexted ones out)."""
    cases: dict[str, list[str]] = {}
    for module, message, text, app, shown in spoken():
        if shown != text and counts(app, message):
            cases.setdefault(module, []).append(f"{module}: {message!r} «{text}», Spanish says {app}'s «{shown}»")
    for module, message, app, shown in said_only_in_code():
        if counts(app, message):
            cases.setdefault(module, []).append(
                f"{module}: {message!r} said in its code with no Spanish of its own, Spanish says {app}'s «{shown}»"
            )
    return cases


def test_spanish_says_what_the_first_app_translates():
    """The count's premise, against Django's own catalogue: each module's message reads the first app's text."""
    with translation.override("es"):
        differ = sorted(
            f"{module}: {message!r} counted as {app}'s «{shown}», Spanish says «{gettext(message)}»"
            for module, message, _, app, shown in spoken()
            if gettext(message) != shown
        )
    assert differ == []


def test_no_module_says_a_message_an_earlier_app_translates_otherwise_but_the_known_ones():
    """A new message an earlier app translates otherwise fails here; a fixed one lowers its module's number."""
    cases = shadowed()
    found = {module: len(lines) for module, lines in sorted(cases.items())}
    changed = [
        line
        for module in sorted(found.keys() | SHADOWED.keys())
        if found.get(module, 0) != SHADOWED.get(module, 0)
        for line in [f"{module}: {found.get(module, 0)} now, {SHADOWED.get(module, 0)} known", *cases.get(module, [])]
    ]
    assert found == SHADOWED, "\n".join(changed)


SOURCE = """
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop, ngettext, pgettext_lazy

ACTIVE = _("active")
TITLE = gettext_noop("Price list")
SINCE = pgettext_lazy("pricing", "valid from")
NOW = translation.gettext("now")
SAID = _(f"{ACTIVE}")
MANY = ngettext("one price", "%(count)s prices", 2)
OTHER = render("not a message")
"""


def test_the_code_s_messages_are_read_as_the_catalogue_keeps_them():
    """Any name the gettext family is imported under, or called on ``translation``; a contexted one as
    ``context\x04message``; a variable, a plural or another function's text is no message here."""
    assert said_in(SOURCE) == ["active", "Price list", "pricing\x04valid from", "now"]


def test_the_code_of_every_module_is_read():
    """Positive control of the count: the code of the modules says messages, pricing's contexted ones among them."""
    said = {config.label: said_in_code(config) for config in apps.get_app_configs() if Path(config.path).parent.name == "apps"}
    assert sum(1 for messages in said.values() if messages) > 10
    assert {"pricing\x04active", "Price list"} <= said["pricing"]


def test_a_message_only_the_code_says_counts_against_its_module(monkeypatch):
    """Pricing's «active» put back without its context (``_("active")``): its catalogue keeps only the contexted one,
    so Spanish says auth's «activo». The catalogue alone left it out (review of hub#473)."""
    read = said_in_code
    monkeypatch.setitem(globals(), "said_in_code", lambda config: read(config) | ({"active"} if config.label == "pricing" else set()))
    assert shadowed()["pricing"] == [
        "pricing: 'active' said in its code with no Spanish of its own, Spanish says auth's «activo»"
    ]
