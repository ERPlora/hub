"""No server catalogue of the Hub spells a plural with «(s)» (hub#1147): a count says «1 cart» or «2 carts».

The SPA's catalogues have the same guard in ``base/frontend/__tests__/catalogue-plurals.test.ts``. A message with a
count goes through ``ngettext``/``npgettext`` with its ``msgid_plural`` (``control/admin.py``), never «cart(s)»: the
parentheses show on screen whatever the number. Read from the compiled catalogues Django uses (``.mo``): the English
message is the key and the Spanish its translation, so both languages are checked. The reader is the one of every
catalogue test, ``base.tests.po.mo_entries``.
"""

import re
from pathlib import Path

from django.conf import settings

from base.tests.po import mo_entries

#: A plural ending glued to a word in parentheses: «record(s)», «opción(es)», «category(ies)» (as the SPA's guard).
IN_PARENTHESES = re.compile(r"[^\W\d_]\((?:s|es|as|os|ies)\)")

#: VeriFactu's messages of the server (fiscal zone), left out of hub#1147 with their own issue: hub#1275. Nothing else
#: may join this list; each one leaves it when hub#1275 gives it its singular and plural.
PENDING_FISCAL = {
    "Rescheduled: %(count)s record(s) go out with the next pass.",
    "Rescheduled: %(count)s chain(s) go out with the next pass.",
    "Corrected: %(count)s new record(s) in the queue.",
    "Not sent to the AEAT yet (%(count)s record(s)): %(why)s.",
    "AEAT (%(environment)s): %(count)s record(s) accepted, CSV %(csv)s.",
    "Fingerprint chain intact: %(total)s record(s) with their SHA-256 chaining verified (%(issuer_nif)s). Amounts "
    "are not re-audited.",
    "AEAT query: %(count)s record(s) retrieved for %(issuer_nif)s.",
    "Chain recovered from the AEAT for %(issuer_nif)s: it continues after invoice %(invoice_number)s (%(found)s "
    "record(s) found).",
}


def hub_catalogues() -> list[Path]:
    """Every compiled Spanish catalogue of the Hub: the platform's (``control``, ``base``) and each app's."""
    root = Path(settings.BASE_DIR)
    return sorted(
        [
            *root.glob("control/locale/es/LC_MESSAGES/django.mo"),
            *root.glob("base/locale/es/LC_MESSAGES/django.mo"),
            *root.glob("apps/*/locale/es/LC_MESSAGES/django.mo"),
        ]
    )


def messages_with_parentheses(path: Path) -> set[str]:
    """The English messages of ``path`` that spell a plural in parentheses, in English or in their Spanish."""
    found = set()
    for key, text in mo_entries(path).items():
        message = key if isinstance(key, str) else key[0]  # A plural form is keyed (message, index).
        message = message.split("\x04", 1)[-1]  # A contexted one is keyed «context\x04message».
        if IN_PARENTHESES.search(message) or IN_PARENTHESES.search(text):
            found.add(message)
    return found


def test_the_catalogues_read_are_the_platforms_and_every_apps():
    read = {path.relative_to(settings.BASE_DIR).parts[:2] for path in hub_catalogues()}
    assert {("control", "locale"), ("base", "locale"), ("apps", "service"), ("apps", "cart_checkout")} <= read
    assert len(read) > 20


def test_no_catalogue_says_a_count_with_parentheses_but_the_fiscal_ones_pending():
    found = {
        f"{path.relative_to(settings.BASE_DIR).parts[1]}: {message}"
        for path in hub_catalogues()
        for message in messages_with_parentheses(path)
    }
    assert found == {f"verifactu: {message}" for message in PENDING_FISCAL}


def test_the_check_catches_a_plural_in_parentheses_in_either_language():
    assert IN_PARENTHESES.search("1 record(s)") and IN_PARENTHESES.search("1 opción(es)")
    assert IN_PARENTHESES.search("2 category(ies)")
    assert not IN_PARENTHESES.search("Price (€)") and not IN_PARENTHESES.search("Slug (optional)")
    assert not IN_PARENTHESES.search("Send the order (3)")
