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
"""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext

from base.tests.test_locale_platform import PLATFORM, catalogue

SPANISH = Path("locale", "es", "LC_MESSAGES", "django.mo")

#: The messages each module says and Spanish shows in an earlier app's words, by module. Only ever lower: a module
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
    "pricing": 6,
    "printing": 3,
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


def shadowed() -> dict[str, list[str]]:
    """Each module's messages that Spanish shows in an earlier app's words, by module; the platform's and ``live``'s
    without context are their own tests' (which leave the contexted ones out)."""
    cases: dict[str, list[str]] = {}
    for module, message, text, app, shown in spoken():
        if shown != text and (app not in (*PLATFORM, "live") or "\x04" in message):
            cases.setdefault(module, []).append(f"{module}: {message!r} «{text}», Spanish says {app}'s «{shown}»")
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
