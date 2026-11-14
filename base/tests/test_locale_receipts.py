"""The Hub's Spanish says «tique», never «ticket» nor the Catalan «tiquet» (hub#680): the word the RAE gives the sales
receipt and the one of the invoicing rules (RD 1619/2012).

The SPA's catalogues have the same guard among the shared tests of ``base/frontend/__tests__/app-catalogues.ts``; this
one reads the server's, the compiled catalogues Django uses (``.mo``) of the platform, ``live`` and every app, as
``base/tests/test_locale_plurals.py`` reads them. Only the Spanish counts: the English message is the source. The word
counts in any case but one: TICKET, in capitals and singular, is the code of the receipts' series, a value the business
sees as it is written.
"""

import re
from pathlib import Path

from base.tests.po import mo_entries
from base.tests.test_locale_plurals import compiled, hub_catalogues

#: «ticket» or «tiquet» as a word, in any case, as the SPA's guard reads it.
ANGLICISED_RECEIPT = re.compile(r"\bti(?:ck|qu)ets?\b", re.IGNORECASE)

#: The code of the receipts' series: the one spelling that is let through.
SERIES_CODE = "TICKET"


def anglicised_receipts(path: Path) -> set[str]:
    """Each message of the compiled catalogue ``path`` whose Spanish says «ticket» or «tiquet», as «message → Spanish»."""
    found = set()
    for key, text in mo_entries(path).items():
        message = key if isinstance(key, str) else key[0]  # A plural form is keyed (message, index).
        message = message.split("\x04", 1)[-1]  # A contexted one is keyed «context\x04message».
        if any(word != SERIES_CODE for word in ANGLICISED_RECEIPT.findall(text)):
            found.add(f"{message} → {text}")
    return found


def test_no_catalogue_says_ticket_in_spanish():
    found = {f"{path.parents[3].name}: {said}" for path in hub_catalogues() for said in anglicised_receipts(path)}
    assert found == set()


def test_the_check_catches_ticket_and_tiquet_and_leaves_tique_english_and_the_series_code_alone(tmp_path):
    path = compiled(
        tmp_path,
        """
msgid "Today's tickets"
msgstr "Tickets hoy"

msgctxt "receipt"
msgid "Receipt"
msgstr "Ticket"

msgid "%(count)s ticket"
msgid_plural "%(count)s tickets"
msgstr[0] "%(count)s tique"
msgstr[1] "%(count)s tickets"

msgid "Avg. ticket"
msgstr "Tique medio"

msgid "Receipt: %(number)s"
msgstr "Tiquet: %(number)s"

msgid "Sales number in TICKET."
msgstr "Las ventas numeran en TICKET: TICKET-2026-000031."

msgid "TODAY'S TICKETS"
msgstr "TICKETS DE HOY"

msgid "RECEIPT"
msgstr "TIQUET"

msgid "Series TICKET: a ticket"
msgstr "Serie TICKET: un ticket"
""",
    )
    assert anglicised_receipts(path) == {
        "Today's tickets → Tickets hoy",
        "Receipt → Ticket",
        "%(count)s ticket → %(count)s tickets",
        "Receipt: %(number)s → Tiquet: %(number)s",
        "TODAY'S TICKETS → TICKETS DE HOY",
        "RECEIPT → TIQUET",
        "Series TICKET: a ticket → Serie TICKET: un ticket",
    }
