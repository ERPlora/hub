"""Layer 1 of the assistant's QA for Customers (erplora-next docs/plans/2026-10-31-asistente-conocimiento-y-qa.md):
every tool of customer says what a person would type to ask for it (``AI.asks``, English and Spanish), and each of
those phrases, asked alone, brings its tool among the first ten a turn of the Hub offers, out of the real catalogue of
the person asking: an owner, a manager and an employee of a business with every app on, so the customer tools compete
with the hundreds of the others (sale, staff, appointments…). No model and no network: the same selection a turn makes
(``base.assistant.relevant``), with what it always offers first.

What a role may not run is not in its catalogue at all: an employee is never offered deleting a card.
"""

import pytest
from django.test import override_settings
from live import assistant as shared
from live.assistant import app_words
from live.assistant_qa import misses, uncovered
from live.checks import check_assistant_asks
from live.context import OperationContext, Scope
from live.operations import AI, Operation, registry

from base import assistant
from base.models import Membership
from base.permissions import permissions_for

A = Scope("host", "a")
ROLES = (Membership.Role.OWNER, Membership.Role.MANAGER, Membership.Role.EMPLOYEE)
LANGUAGES = ("en", "es")
#: How far down a turn's tools an ask may bring its own, counting what the turn always offers first.
TOP = 10
#: Writes on cards and settings that only the owner and the admin hold, none of them a manager approves: an employee's
#: assistant is never offered them (an approvable write is, as its button on the screen: running it asks a manager).
NOT_THE_EMPLOYEES = {
    "customer.customer.delete",
    "customer.customer.erase",
    "customer.group.delete",
    "customer.tag.delete",
}


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``."""

    def of(role: str, language: str) -> dict[str, Operation]:
        user = make_user(f"asker-{role}", host=A.key, role=role)
        ctx = OperationContext(
            scope=A, actor=user.username, permissions=permissions_for(user, A), language=language
        )
        return assistant.catalog(ctx)

    return of


def customers(tools: dict[str, Operation]) -> dict[str, Operation]:
    return {name: op for name, op in tools.items() if op.app_label == "customer"}


def customer_tools() -> set[str]:
    """Every operation of customer that is an assistant tool, as declared (``AI``, never ``INTERNAL``)."""
    return {name for name, op in registry.items() if op.app_label == "customer" and isinstance(op.ai_spec(), AI)}


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_the_owner_is_offered_every_tool_of_customer(catalog_of):
    """Positive control: the owner's catalogue holds every customer tool, so the layer below checks all of them."""
    assert len(customer_tools()) >= 30
    assert set(customers(catalog_of(Membership.Role.OWNER, "en"))) == customer_tools()


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("role", ROLES)
def test_every_ask_of_customer_brings_its_tool_among_the_first_offered(catalog_of, role, language):
    tools = catalog_of(role, language)
    mine = customers(tools)
    assert mine  # every role holds some customer tool
    assert uncovered(mine, language) == []
    missed = misses(tools, language=language, top=TOP, app_words=app_words, always=assistant.ALWAYS)
    assert [miss for miss in missed if miss.tool_name.startswith("customer__")] == []


#: A phrase of five customer tools, each with the tool it asks for: reads and writes, both languages.
SAMPLE = [
    ("es", "customer.customer.create", "apúntame a Ana con su teléfono 600 111 222"),
    ("es", "customer.customer.detail", "¿qué sabemos de Marta?"),
    ("es", "customer.customer.delete", "borra a este cliente"),
    ("en", "customer.note.add", "add a note to Luis"),
    ("en", "customer.consent.withdraw", "unsubscribe Marta from WhatsApp messages"),
]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("language", "name", "phrase"), SAMPLE)
def test_the_layer_ranks_each_phrase_where_a_turn_of_the_hub_offers_its_tool(catalog_of, language, name, phrase):
    """``misses`` above is given the Hub's turn's ``always`` and app words: the place it gives a tool is the one the
    turn (``base.assistant.relevant``) offers it at, so a turn that ranks otherwise fails here."""
    tools = catalog_of(Membership.Role.OWNER, language)
    assert phrase in shared.asks_of(tools[name])[language]  # positive control: the phrase is one of its asks
    turn = [op.name for op in assistant.relevant(tools, [phrase], language)]
    assert name in turn  # offered by the turn, so its place is known
    tool = shared.tool_name(name)
    # Every ask whose tool is not first in the turn is a miss with ``top=1``: its place, as the layer computes it.
    places = {
        miss.ask: miss.position
        for miss in misses(tools, language=language, top=1, app_words=app_words, always=assistant.ALWAYS)
        if miss.tool_name == tool
    }
    # With what is always at hand in front, none of these is first: the layer reports each one's place.
    assert places[phrase] == turn.index(name) + 1


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_an_employee_is_never_offered_what_only_the_owner_may_do(catalog_of):
    owner = catalog_of(Membership.Role.OWNER, "es")
    employee = catalog_of(Membership.Role.EMPLOYEE, "es")
    assert NOT_THE_EMPLOYEES <= set(owner)
    assert NOT_THE_EMPLOYEES.isdisjoint(employee)
    assert "customer.customer.create" in employee  # positive control: the employee's own writes are there


def test_every_tool_of_customer_says_its_asks_as_the_check_requires():
    """``live.E020`` with customer listed: two distinct phrases at least in each language, none its own name."""
    with override_settings(LIVE_ASSISTANT_ASKS_REQUIRED=("customer",)):
        assert check_assistant_asks() == []
