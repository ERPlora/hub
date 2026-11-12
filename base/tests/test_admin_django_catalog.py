"""The admin in Spanish speaks Spanish all through, also where Django's own catalogue has a hole.

Django ships its Spanish catalogues with holes: a message new in a release keeps ``msgstr ""`` until its translators
reach it, and the admin of ``hubs.erplora.com`` shows it in English (6.1.2: «Run» on the actions of every list and
«- Select an option -» in its select). This reads every Spanish catalogue of Django that the admin
uses and asks that each empty entry comes out translated anyway: the platform's catalogue (``base/locale/es``; Django
leaves out an empty entry, so ``base`` fills the hole whatever the order of ``INSTALLED_APPS``) covers it. An upgrade
of Django that opens a new hole fails here, naming the message to translate; so does a ``makemessages`` of ``base``
that marks these entries obsolete (their messages are Django's, not in ``base``'s code).
"""

from pathlib import Path

import django
import pytest
from babel.messages.catalog import Message
from django.utils import translation
from django.utils.translation.trans_real import DjangoTranslation

from base.tests.po import po_messages

DJANGO = Path(django.__file__).parent
#: The Spanish catalogues of Django behind the admin: its own (pages and JavaScript) and Django's core (forms, fields).
CATALOGUES = {
    "contrib/admin django": (DJANGO / "contrib/admin/locale/es/LC_MESSAGES/django.po", "django"),
    "contrib/admin djangojs": (DJANGO / "contrib/admin/locale/es/LC_MESSAGES/djangojs.po", "djangojs"),
    "conf django": (DJANGO / "conf/locale/es/LC_MESSAGES/django.po", "django"),
}
#: Empty entries left as they are, each with why: what Django shows for them is already right in Spanish.
SAME_IN_SPANISH = {
    ", ": "the separator of a list of objects reads the same in Spanish",
}


def messages(path: Path) -> list[Message]:
    """Django's catalogues are not ours: ``djangojs.po`` declares two plural forms and writes three."""
    return po_messages(path, strict=False)


def msgid(message: Message) -> str:
    return message.id[0] if message.pluralizable else message.id


def holes(path: Path) -> list[Message]:
    """The entries the compiled catalogue leaves out: every ``msgstr`` empty, or fuzzy (``msgfmt`` drops those)."""
    return [message for message in messages(path) if message.fuzzy or not any(message.string)]


def untranslated(message: Message, domain: str) -> bool:
    """Whether ``message`` still comes out in English with the Spanish catalogues of this project."""
    catalogue = DjangoTranslation("es", domain=domain) if domain != "django" else None
    text, plural = message.id if message.pluralizable else (message.id, None)
    with translation.override("es"):
        if catalogue is None:
            if plural:
                if message.context:
                    said = [translation.npgettext(message.context, text, plural, n) for n in (1, 2)]
                else:
                    said = [translation.ngettext(text, plural, n) for n in (1, 2)]
            elif message.context:
                said = [translation.pgettext(message.context, text)]
            else:
                said = [translation.gettext(text)]
        elif plural:
            said = [catalogue.ngettext(text, plural, n) for n in (1, 2)]
        else:
            said = [catalogue.gettext(text)]
    english = [text, plural] if plural else [text]
    return said == english


def test_the_scan_reads_djangos_catalogues():
    """The parser finds Django's translations: «Log out» is «Cerrar sesión» in the admin's own catalogue."""
    path, _ = CATALOGUES["contrib/admin django"]
    log_out = next(message for message in messages(path) if msgid(message) == "Log out")

    assert log_out.string == "Cerrar sesión"
    assert all(path.exists() for path, _ in CATALOGUES.values())


def test_a_hole_is_an_empty_or_fuzzy_entry(tmp_path):
    """The list below would pass on nothing if this found nothing; how many holes Django has today is up to Django."""
    po = tmp_path / "django.po"
    po.write_text(
        'msgid ""\nmsgstr ""\n"Plural-Forms: nplurals=2; plural=n != 1;\\n"\n\n'
        'msgid "Translated"\nmsgstr "Traducida"\n\n'
        'msgid "Empty"\nmsgstr ""\n\n'
        '#, fuzzy\nmsgid "Fuzzy"\nmsgstr "Dudosa"\n\n'
        'msgid "One"\nmsgid_plural "Many"\nmsgstr[0] ""\nmsgstr[1] ""\n\n'
        'msgid "Half"\nmsgid_plural "Halves"\nmsgstr[0] "Media"\nmsgstr[1] ""\n',
        encoding="utf-8",
    )
    assert [msgid(message) for message in holes(po)] == ["Empty", "Fuzzy", "One"]


@pytest.mark.parametrize("name", CATALOGUES)
def test_every_hole_of_djangos_spanish_is_translated_by_ours(name):
    path, domain = CATALOGUES[name]

    missing = [
        msgid(message)
        for message in holes(path)
        if msgid(message) not in SAME_IN_SPANISH and untranslated(message, domain)
    ]

    assert missing == [], f"translate in base/locale/es ({domain}.po): {missing}"
