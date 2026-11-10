"""What layer 1 of the assistant's QA does not say of Customers (erplora-next docs/plans/2026-10-31-asistente-
conocimiento-y-qa.md): how many tools it offers, and what an employee is never offered.

Every ask of every tool of customer bringing its tool among the first ten, role by role, in English and in Spanish, out
of the catalogue of a business with every app on and ranked as a turn ranks, is ``base/tests/test_assistant_asks.py``'s
(customer is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over its asks and the place a turn gives
each.
"""

import pytest
from live.context import OperationContext, Scope
from live.errors import Conflict
from live.operations import AI, Operation, registry

from apps.customer.models import Customer
from apps.customer.schemas import MergeIn
from base import assistant
from base.models import Membership
from base.permissions import permissions_for

from .conftest import ctx_for

A = Scope("host", "a")
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


def test_customer_offers_at_least_30_tools():
    """Customer's tools are at least 30 (``AI``, never ``INTERNAL``): a silent drop of tools fails."""
    tools = {name for name, op in registry.items() if op.app_label == "customer" and isinstance(op.ai_spec(), AI)}
    assert len(tools) >= 30


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_an_employee_is_never_offered_what_only_the_owner_may_do(catalog_of):
    owner = catalog_of(Membership.Role.OWNER, "es")
    employee = catalog_of(Membership.Role.EMPLOYEE, "es")
    assert NOT_THE_EMPLOYEES <= set(owner)
    assert NOT_THE_EMPLOYEES.isdisjoint(employee)
    assert "customer.customer.create" in employee  # positive control: the employee's own writes are there


#: What the owner or a manager asks about a customer's orders, with the tool of Customers that answers it: its own asks
#: and phrases nobody wrote yet. With every app on, these tools tied on the tenth place with other apps' order tools and
#: got in only by name (hub#594): one more phrase about «pedido» elsewhere left them out.
ORDER_ASKS = [
    ("en", "customer.order.list", "what orders does Pedro have?"),
    ("en", "customer.order.list", "show me Pedro's orders"),
    ("es", "customer.order.list", "¿qué pedidos tiene el cliente Pedro?"),
    ("es", "customer.order.list", "¿qué pedidos ha hecho Ana?"),
    ("en", "customer.order.customer", "who's on this order?"),
    ("en", "customer.order.customer", "which customer is this order for?"),
    ("es", "customer.order.customer", "¿de quién es este pedido?"),
    ("es", "customer.order.customer", "¿a qué cliente pertenece este pedido?"),
]
#: The first places a turn offers that these tools come within: three short of the QA's first ten
#: (``base/tests/test_assistant_asks.py``), so three more tools may climb past them, or tie with them and go first by
#: name, before they are left out.
WITH_ROOM = 7


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.MANAGER])
@pytest.mark.parametrize(("language", "name", "phrase"), ORDER_ASKS)
def test_a_customers_orders_bring_the_tool_of_customers_with_room_to_spare(catalog_of, role, language, name, phrase):
    tools = catalog_of(role, language)
    assert name in tools  # positive control: the role holds the tool, so its place is known
    offered = [op.name for op in assistant.relevant(tools, [phrase], language)]
    assert name in offered[:WITH_ROOM], (offered.index(name) + 1 if name in offered else None, offered[:WITH_ROOM])


#: A merge asked by the two phones, in words that are none of its ``asks``: the Spanish one is the phrase of the
#: real-model QA that ended without a card (hub#1084, ``qa20261108.owner.es.customer.customer.merge``), 20th of the
#: tools offered before the merge's ``asks`` said «A into B»; the English one, its twin, was 9th.
MERGE_BY_TWO_PHONES = [
    (
        "es",
        (
            "junta la ficha con móvil 611 222 444 dentro de la ficha con móvil 611 222 333, que es la buena, y "
            "traslada todo su historial"
        ),
    ),
    (
        "en",
        (
            "fold the customer with phone 611 222 444 into the one with 611 222 333, that one is the right card, and "
            "move all her history"
        ),
    ),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "phrase"), MERGE_BY_TWO_PHONES)
def test_a_merge_by_two_phones_offers_the_existing_operation_with_room_to_spare(catalog_of, language, phrase):
    tools = catalog_of(Membership.Role.OWNER, language)
    name = "customer.customer.merge"
    assert name in tools  # positive control: the owner holds it, so the model can receive it
    offered = [op.name for op in assistant.relevant(tools, [phrase], language)]
    assert name in offered[:WITH_ROOM], (offered.index(name) + 1 if name in offered else None, offered[:WITH_ROOM])


def test_the_merge_instruction_completes_the_action_with_human_references():
    description = assistant.description(registry["customer.customer.merge"])
    for expected in (
        "Use this tool once both cards are known",
        "do not stop at reading or explaining",
        "`customer` is the card that stays",
        "`absorbed` is the duplicate",
        "customer.customer.by_phone",
        "customer.customer.list",
        "never ask the person for an internal id",
        # The ids those reads return go in the id fields: an id in `customer` or `absorbed` is no name, phone or email.
        "their ids in `id` and `absorbed_id`",
    ):
        assert expected in description


def test_the_merge_schema_distinguishes_the_survivor_from_the_duplicate():
    properties = MergeIn.model_json_schema()["properties"]
    for name in ("id", "customer"):
        assert "card that stays" in properties[name]["description"]
    for name in ("absorbed_id", "absorbed"):
        assert "duplicate" in properties[name]["description"]


@pytest.mark.django_db
def test_the_reported_merge_keeps_its_confirmation_and_absorbs_the_right_card():
    survivor = Customer.objects.create(name="Ana QA", phone="+34611222333")
    duplicate = Customer.objects.create(name="Ana QA copia", phone="+34611222444")
    op = registry["customer.customer.merge"]
    arguments = {"customer": "611 222 333", "absorbed": "611 222 444"}
    ctx = ctx_for("hub_owner", language="es")

    card = assistant.card(op, arguments, "es", ctx)
    assert op.ai_spec().risk == "high"
    assert [(field["name"], field["value"]) for field in card["fields"]] == [
        ("customer", "Ana QA"),
        ("absorbed", "Ana QA copia"),
    ]

    op(ctx, op.input.model_validate(arguments))
    survivor.refresh_from_db()
    duplicate.refresh_from_db()
    assert duplicate.merged_into_id == survivor.id
    assert survivor.name == "Ana QA"


@pytest.mark.django_db
def test_a_merge_whose_survivor_fits_two_cards_leaves_it_out_of_the_card_and_merges_nothing():
    """The written reference is no name: with two «Ana» the card cannot say which one stays, so it leaves that datum
    out (as an id it cannot name), and the merge refuses: it never merges into the first card that fits."""
    Customer.objects.create(name="Ana", phone="+34611222555")
    Customer.objects.create(name="Ana", phone="+34611222666")
    duplicate = Customer.objects.create(name="Ana QA copia", phone="+34611222444")
    op = registry["customer.customer.merge"]
    arguments = {"customer": "Ana", "absorbed": "611 222 444"}
    ctx = ctx_for("hub_owner", language="es")

    card = assistant.card(op, arguments, "es", ctx)
    assert [(field["name"], field["value"]) for field in card["fields"]] == [("absorbed", "Ana QA copia")]

    with pytest.raises(Conflict) as excinfo:
        op(ctx, op.input.model_validate(arguments))
    assert excinfo.value.code == "customer.customer_ambiguous"
    duplicate.refresh_from_db()
    assert duplicate.merged_into_id is None
