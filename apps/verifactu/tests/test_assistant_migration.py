"""What the assistant is told of continuing the chain of another application (VERIFACTU-F29). Given the last invoice of
the owner's previous program with its number, date and fingerprint, the model answered with several questions at once
and asked again for the date already said, instead of the card: the description told it «Only during a migration, and
only with no pending records», which it took as conditions of its own to check (a chain already holding a test ticket
read as one it must not continue), and it looked the old invoice up in Invoicing, where it never is.
"""

import re

import pytest
from live.assistant import description
from live.errors import Conflict
from live.operations import get

from apps.verifactu.tests.conftest import HUB_DB, ctx_for, run
from apps.verifactu.tests.test_services import create, ticket
from base import assistant
from base.tests.test_assistant_asks import offered_to

MIGRATION = "verifactu.chain.recover_manual"
OWNER_SAYS = (
    "Antes facturaba con otro programa. La última factura fue la A-2026-0456 del 20 de noviembre y su huella es "
    f"{'3f9a' * 16}. Quiero seguir la cadena desde ahí."
)


def said() -> str:
    return description(get(MIGRATION))


def test_the_migration_sets_the_model_no_condition_to_check_before_calling_it():
    sentences = re.split(r"(?<=[.:;])\s+", said())
    assert [sentence for sentence in sentences if sentence.startswith("Only")] == []
    assert "It refuses by itself while records of the chain wait to go out." in sentences


@HUB_DB
def test_the_refusal_it_names_is_the_tools_own(issuer):
    create(ticket())
    data = {"fingerprint": "ab" * 32, "invoice_number": "A-2026-0456", "issue_date": "2026-11-20"}
    with pytest.raises(Conflict) as refused:
        run(MIGRATION, data)
    assert refused.value.code == "verifactu.pending_in_chain"


def test_the_migration_says_the_previous_invoice_is_not_in_invoicing():
    assert "as the person gives them (that invoice is not in Invoicing: there is nothing to look up)" in said()


def test_the_migration_says_what_becomes_of_the_chain_held_here():
    assert "in the chain of the environment it is in now (testing or production; the other is not touched)" in said()
    assert "instead of to the chain's last record; the records already sealed here stay as they are" in said()


def test_the_migration_is_called_once_its_three_data_are_said():
    required = get(MIGRATION).input.model_json_schema()["required"]
    assert sorted(required) == ["fingerprint", "invoice_number", "issue_date"]
    assert "With those three said, call it: its card shows them and the person confirms there." in said()


@HUB_DB
def test_the_owners_words_of_a_migration_are_handed_the_migration(issuer):
    """The phrase of the owner offers the tool whose description says the above, among the first."""
    tools = assistant.tools.catalog(ctx_for("hub_owner", language="es"))
    assert MIGRATION in offered_to(tools, OWNER_SAYS, "es")[:5]
