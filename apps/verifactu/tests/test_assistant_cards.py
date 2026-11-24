"""The cards of VeriFactu's live test from the assistant, as Settings › Live test names its two buttons: the
connection test says «Test the connection» and the test invoice «Create test invoice», each with its own verb and
never «Run» or «Create»; and the test invoice's card says what it will issue, its series, its price and its VAT, before
the person types the word. Saying them sends nothing to the AEAT."""

import json
from pathlib import Path

import pytest
from django.conf import settings
from live.operations import get

from apps.invoice.models import Invoice
from apps.verifactu.models import Event, Record
from apps.verifactu.tests.conftest import HUB_DB, ctx_for, run
from base import assistant
from base.tests.test_assistant import named_actions, verb

#: Saying a card sends nothing anywhere.
pytestmark = [HUB_DB, pytest.mark.usefixtures("offline")]

CONNECTION_TEST = "verifactu.diagnostic.run"
TEST_INVOICE = "verifactu.test_invoice.create"

#: The test invoice's card, as each language says it: its series, its price before VAT and its VAT rate.
TEST_INVOICE_FIELDS = {
    "en": [
        {"name": "series", "label": "Series", "kind": "text", "value": "TICKET"},
        {"name": "price", "label": "Price", "kind": "money", "value": 100},
        {"name": "vat", "label": "VAT", "kind": "text", "value": "21%"},
    ],
    "es": [
        {"name": "series", "label": "Serie", "kind": "text", "value": "TICKET"},
        {"name": "price", "label": "Precio", "kind": "money", "value": 100},
        {"name": "vat", "label": "IVA", "kind": "text", "value": "21 %"},
    ],
}


def screen_words(language: str, screen: str = "settings") -> dict:
    """VeriFactu's ``screen`` (Settings by default), as it says it in ``language``."""
    locale = Path(settings.BASE_DIR) / "apps/verifactu/frontend/locale" / f"{language}.json"
    return json.loads(locale.read_text())["verifactu"][screen]


@pytest.mark.parametrize(
    ("language", "connection", "invoice"),
    [("en", "Test the connection", "Create test invoice"), ("es", "Probar la conexión", "Crear factura de prueba")],
)
def test_each_card_names_its_action_as_the_button_of_its_screen(language, connection, invoice):
    """hub#2183: the connection test read «Ejecutar en VeriFactu:» and the test invoice «Crear en VeriFactu»."""
    verbs = named_actions()[language]
    words = screen_words(language)
    assert (verb(get(CONNECTION_TEST), verbs, language), verb(get(TEST_INVOICE), verbs, language)) == (
        connection,
        invoice,
    )
    assert (words["testRun"], words["testCreate"]) == (connection, invoice)


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_connection_test_sends_no_datum_its_card_could_show(language):
    """It takes nothing: its card is its verb and its app alone, in one line."""
    card = assistant.cards.card(get(CONNECTION_TEST), {}, language, ctx_for(language=language))
    assert (card["risk"], card["fields"], card["confirm_word"]) == ("normal", [], "")


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_test_invoice_card_says_its_series_price_and_vat(language):
    """hub#2183: «Create in VeriFactu. Check each datum before going on.» had no datum under it."""
    card = assistant.cards.card(get(TEST_INVOICE), {}, language, ctx_for(language=language))
    assert (card["risk"], card["fields"]) == ("high", TEST_INVOICE_FIELDS[language])


@pytest.mark.parametrize("write", [CONNECTION_TEST, TEST_INVOICE])
def test_saying_a_card_runs_nothing(issuer, write):
    """The card is drawn before the person answers: no connection test is kept, and no invoice or record is made."""
    assistant.cards.card(get(write), {}, "en", ctx_for())
    assert (Event.objects.count(), Invoice.objects.count(), Record.objects.count()) == (0, 0, 0)


def test_the_test_invoice_card_says_what_the_write_issues(issuer):
    """The card and the ticket come from the same invoice: its series, the price of its one line and its rate."""
    shown = {field["name"]: field["value"] for field in TEST_INVOICE_FIELDS["en"]}
    invoice = Invoice.objects.get(pk=run(TEST_INVOICE).invoice_id)
    (line,) = invoice.lines.all()
    assert (invoice.series_code, line.unit_price, f"{line.tax_rate.normalize()}%") == (
        shown["series"],
        shown["price"],
        shown["vat"],
    )
