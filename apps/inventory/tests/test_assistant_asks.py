"""What layer 1 of the assistant's QA does not say of Inventory (docs plan 2026-10-31, the assistant's knowledge and
QA, §3): how many tools it offers and the phrases the owner types for the ones the real-model QA found left out of
the turn (hub#1080).

Every ask of every tool of inventory bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (inventory is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over
the asks.
"""

import pytest
from live.context import OperationContext, Scope
from live.operations import AI, Operation, registry

from base import assistant
from base.models import Membership
from base.permissions import permissions_for

A = Scope("host", "a")
#: How far down the tools a turn offers the tool of an ask may come: the QA's first ten (``base/tests/test_assistant_asks.py``).
TOP = 10

#: What the owner typed in the real-model QA of hub#1080 (``qa20261108.owner.es.inventory.*``), whose tool a turn did
#: not offer, with the tool each one asks for, and the same asks in English.
QA_ASKS = [
    ("es", "inventory.movement.list", "¿qué entradas, salidas y ajustes de stock ha habido esta semana?"),
    ("en", "inventory.movement.list", "show me the history of stock coming in and going out"),
    ("es", "inventory.product_category.list", "¿en qué familia está cada artículo del TPV?"),
    ("en", "inventory.product_category.list", "which category is each till item in?"),
    ("es", "inventory.unit.list", "¿qué unidades de medida tengo configuradas en este negocio?"),
    ("en", "inventory.unit.list", "what units of measure are set up in this business?"),
    ("es", "inventory.stock.receive", "ha llegado un pedido: recibe 20 cafés con el albarán A-123"),
    ("en", "inventory.stock.receive", "I just received 20 coffees, delivery note A-123"),
    ("es", "inventory.product_category.add", "clasifica el Café en la categoría Cafetería QA"),
    ("en", "inventory.product_category.add", "put the Coffee in the Cafetería QA category"),
    ("es", "inventory.product.set_sold_out", "marca el Té QA como agotado"),
    ("en", "inventory.product.set_sold_out", "mark the Tea as sold out for today"),
    ("es", "inventory.stock.write_off", "da de baja 2 cafés que se han roto"),
    ("en", "inventory.stock.write_off", "write off 2 coffees, they broke"),
]


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


def test_inventory_offers_at_least_30_tools():
    """Inventory's tools are at least 30 (``AI``, never ``INTERNAL``): a silent drop of tools fails."""
    tools = {name for name, op in registry.items() if op.app_label == "inventory" and isinstance(op.ai_spec(), AI)}
    assert len(tools) >= 30


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("language", "name", "phrase"), QA_ASKS)
def test_what_the_owner_asked_in_the_qa_brings_its_tool_among_the_first_ten(catalog_of, language, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, language)
    assert name in tools  # positive control: the owner holds the tool, so its place is known
    offered = [op.name for op in assistant.relevant(tools, [phrase], language)]
    assert name in offered[:TOP], (offered.index(name) + 1 if name in offered else None, offered[:TOP])
