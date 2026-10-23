"""The admin in Spanish speaks Spanish all through, also where Django's own catalogue has a hole.

Django ships its Spanish catalogues with holes: a message new in a release keeps ``msgstr ""`` until its translators
reach it, and the admin of ``hubs.erplora.com`` shows it in English (6.1.2: «Run» on the actions of every list and
«- Select an option -» in its select; APP-ACCOUNTS-6). This reads every Spanish catalogue of Django that the admin
uses and asks that each empty entry comes out translated anyway: the platform's catalogue (``base/locale/es``; Django
leaves out an empty entry, so ``base`` fills the hole whatever the order of ``INSTALLED_APPS``) covers it. An upgrade
of Django that opens a new hole fails here, naming the message to translate; so does a ``makemessages`` of ``base``
that marks these entries obsolete (their messages are Django's, not in ``base``'s code).
"""

import re
from pathlib import Path

import django
import pytest
from django.utils import translation
from django.utils.translation.trans_real import DjangoTranslation

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
ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


def _text(quoted: str) -> str:
    return re.sub(r"\\(.)", lambda match: ESCAPES.get(match.group(1), match.group(1)), quoted)


def entries(path: Path) -> list[dict]:
    """The live entries of a ``.po``: ``context``, ``msgid``, ``plural``, ``msgstr`` (a list) and ``fuzzy``."""
    found, entry, field = [], None, None
    for line in [*path.read_text(encoding="utf-8").splitlines(), ""]:
        line = line.strip()
        if not line:
            if entry and entry.get("msgid"):
                found.append(entry)
            entry, field = None, None
            continue
        entry = entry or {"context": None, "msgid": "", "plural": None, "msgstr": {}, "fuzzy": False}
        if line.startswith("#~"):
            entry["obsolete"] = True
        elif line.startswith("#,"):
            entry["fuzzy"] = entry["fuzzy"] or "fuzzy" in line
        elif line.startswith("#"):
            continue
        elif match := re.fullmatch(r'(msgctxt|msgid_plural|msgid|msgstr(?:\[(\d+)\])?) "(.*)"', line):
            keyword, index, text = match.groups()
            field = {"msgctxt": "context", "msgid_plural": "plural", "msgid": "msgid"}.get(keyword, ("msgstr", index or "0"))
            if isinstance(field, tuple):
                entry["msgstr"][field[1]] = _text(text)
            else:
                entry[field] = _text(text)
        elif line.startswith('"') and field is not None:
            if isinstance(field, tuple):
                entry["msgstr"][field[1]] += _text(line[1:-1])
            else:
                entry[field] = (entry[field] or "") + _text(line[1:-1])
    return [entry for entry in found if not entry.get("obsolete")]


def holes(path: Path) -> list[dict]:
    """The entries the compiled catalogue leaves out: every ``msgstr`` empty, or fuzzy (``msgfmt`` drops those)."""
    return [entry for entry in entries(path) if entry["fuzzy"] or not any(entry["msgstr"].values())]


def untranslated(entry: dict, domain: str) -> bool:
    """Whether ``entry`` still comes out in English with the Spanish catalogues of this project."""
    catalogue = DjangoTranslation("es", domain=domain) if domain != "django" else None
    with translation.override("es"):
        if catalogue is None:
            if entry["plural"]:
                if entry["context"]:
                    said = [translation.npgettext(entry["context"], entry["msgid"], entry["plural"], n) for n in (1, 2)]
                else:
                    said = [translation.ngettext(entry["msgid"], entry["plural"], n) for n in (1, 2)]
            elif entry["context"]:
                said = [translation.pgettext(entry["context"], entry["msgid"])]
            else:
                said = [translation.gettext(entry["msgid"])]
        elif entry["plural"]:
            said = [catalogue.ngettext(entry["msgid"], entry["plural"], n) for n in (1, 2)]
        else:
            said = [catalogue.gettext(entry["msgid"])]
    english = [entry["msgid"], entry["plural"]] if entry["plural"] else [entry["msgid"]]
    return said == english


def test_the_scan_reads_djangos_catalogues():
    """The parser finds Django's translations: «Log out» is «Cerrar sesión» in the admin's own catalogue."""
    path, _ = CATALOGUES["contrib/admin django"]
    log_out = next(entry for entry in entries(path) if entry["msgid"] == "Log out")

    assert log_out["msgstr"] == {"0": "Cerrar sesión"}
    assert all(path.exists() for path, _ in CATALOGUES.values())


@pytest.mark.parametrize("name", CATALOGUES)
def test_every_hole_of_djangos_spanish_is_translated_by_ours(name):
    path, domain = CATALOGUES[name]

    missing = [
        entry["msgid"]
        for entry in holes(path)
        if entry["msgid"] not in SAME_IN_SPANISH and untranslated(entry, domain)
    ]

    assert missing == [], f"translate in base/locale/es ({domain}.po): {missing}"
