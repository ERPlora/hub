"""What layer 1 of the assistant's QA says of Cart & Checkout (erplora-next docs/plans/2026-10-31-asistente-conocimiento-y-
qa.md): which tools it offers, to whom, and the requests the real-model QA found unreachable (hub#1100).

Every ask of every tool of cart_checkout bringing its tool among the first ten, role by role, in English and in Spanish,
out of the catalogue of a business with every app on and ranked as a turn ranks, is ``base/tests/test_assistant_asks.py``'s
(cart_checkout is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over its asks.
"""

import json
import re
import unicodedata
from pathlib import Path

import pytest
from django.conf import settings
from live import assistant as shared
from live.context import OperationContext, Scope
from live.operations import AI, Operation, registry

from base import assistant
from base.models import Membership
from base.permissions import permissions_for

A = Scope("host", "a")
#: Cart & Checkout's reads: its carts, their lines and the orders made from them.
READS = {
    "cart_checkout.cart.list",
    "cart_checkout.cart.get",
    "cart_checkout.item.list",
    "cart_checkout.item.get",
    "cart_checkout.order.list",
    "cart_checkout.order.get",
}
#: Its assistant tools: the reads, and every change of a cart, a line, an order and a customer's personal data.
TOOLS = READS | {
    "cart_checkout.cart.create",
    "cart_checkout.cart.mark_abandoned",
    "cart_checkout.cart.delete",
    "cart_checkout.cart.clear",
    "cart_checkout.cart.cleanup_expired",
    "cart_checkout.item.add",
    "cart_checkout.item.update",
    "cart_checkout.item.remove",
    "cart_checkout.checkout.initiate",
    "cart_checkout.order.mark_paid",
    "cart_checkout.order.fail",
    "cart_checkout.order.complete",
    "cart_checkout.customer.erase",
}
#: The probes of layer 2 (``tests/e2e/qa/assistant-probes.spec.ts``) that hub#1100's QA ran on Cart & Checkout.
PROBES = Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes"


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``."""

    def of(role: str, language: str) -> dict[str, Operation]:
        user = make_user(f"asker-{role}", host=A.key, role=role)
        ctx = OperationContext(scope=A, actor=user.username, permissions=permissions_for(user, A), language=language)
        return assistant.catalog(ctx)

    return of


def test_cart_checkout_offers_its_nineteen_tools():
    """Cart & Checkout's assistant tools (``AI``, never ``INTERNAL``): a silent drop of a tool fails."""
    tools = {name for name, op in registry.items() if op.app_label == "cart_checkout" and isinstance(op.ai_spec(), AI)}
    assert tools == TOOLS


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
def test_who_manages_the_carts_is_offered_every_tool_and_an_employee_only_the_reads(catalog_of):
    """``CartCheckoutConfig.role_permissions``: the owner, the admin and the manager hold every tool; an employee only
    looks (``cart_checkout.view_cart``)."""
    for role in (Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MANAGER):
        assert {name for name in catalog_of(role, "es") if name.startswith("cart_checkout.")} == TOOLS, role
    employee = catalog_of(Membership.Role.EMPLOYEE, "es")
    assert {name for name in employee if name.startswith("cart_checkout.")} == READS


#: The requests of hub#1100's QA as the owner said them (``tests/e2e/qa/probes/owner-es-cart_checkout-2026-11-08.json``),
#: and nothing of the tools' ``asks``: before Cart & Checkout said its asks, emptying a cart was not among the tools a
#: turn offers (``MAX_TOOLS``) and changing a line's quantity came 16th, below Inventory's product, so the model said it
#: had no tool or changed the product. The others, which the QA found reachable, stay so. Their words stay the person's,
#: never the asks' (``test_no_ask_copies_a_qa_probe_or_names_a_qa_record``).
REPORTED = [
    (
        "cart_checkout.cart.clear",
        "vacía QA-WEB-1 quitando todas sus líneas pero conserva la cesta activa",
    ),
    (
        "cart_checkout.item.update",
        "cambia el Café de QA-WEB-1 a tres unidades manteniendo su precio",
    ),
    ("cart_checkout.item.remove", "quita la línea del Café de QA-WEB-1 y recalcula el total"),
    (
        "cart_checkout.item.get",
        "muéstrame la línea del Café en la cesta QA-WEB-1, con cantidad y precio guardado",
    ),
    (
        "cart_checkout.item.list",
        "detalla todas las líneas de la cesta QA-WEB-1 con SKU, cantidad y subtotal",
    ),
    ("cart_checkout.item.add", "añade a QA-WEB-1 dos Cafés a 1,80 € cada uno"),
    ("cart_checkout.cart.get", "abre la cesta QA-WEB-1 con todas sus líneas, precios y total"),
    (
        "cart_checkout.cart.list",
        "lista las cestas web activas, abandonadas y convertidas, sin mezclarlas con las cuentas del TPV",
    ),
    (
        "cart_checkout.cart.create",
        "crea una cesta web con sesión QA-WEB-1 para Web QA, email web.qa@example.com",
    ),
    (
        "cart_checkout.cart.cleanup_expired",
        "marca como caducadas todas las cestas activas cuya fecha de caducidad ya pasó",
    ),
    (
        "cart_checkout.cart.delete",
        "elimina la cesta QA-WEB-1 y conserva los pedidos que nacieron de ella",
    ),
    (
        "cart_checkout.cart.mark_abandoned",
        "marca QA-WEB-1 como abandonada porque la clienta no terminó el pedido, conservando sus líneas",
    ),
    (
        "cart_checkout.checkout.initiate",
        "inicia el pedido de QA-WEB-1 con pago por transferencia y nota «pedido QA»",
    ),
    (
        "cart_checkout.order.get",
        "abre el pedido OS-20261109-0001 con direcciones, pago, estado y notas",
    ),
    (
        "cart_checkout.order.list",
        "lista los pedidos web con número, email, estado, forma de pago y total, sin sacar ventas fiscales del TPV",
    ),
    (
        "cart_checkout.order.mark_paid",
        "el pedido OS-20261109-0001 ya está pagado por transferencia, márcalo como pagado sin crear venta ni factura",
    ),
    (
        "cart_checkout.order.fail",
        "registra que el pago del pedido de QA-WEB-1 falló porque el banco lo rechazó",
    ),
    (
        "cart_checkout.order.complete",
        "completa el pedido pagado de QA-WEB-1 y deja su cesta convertida",
    ),
    (
        "cart_checkout.customer.erase",
        "borra los datos personales de web.qa@example.com de cestas y pedidos, conservando números, totales y estados",
    ),
]


def comparable(text: str) -> str:
    """``text`` as layer 2 compares a probe with the asks: lower case, without accents, punctuation or extra spaces."""
    bare = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^\w]+|_", " ", bare).split())


def test_the_reported_requests_are_the_owners_probes_of_layer_2():
    """Each phrase above is word for word the owner's probe of its tool, one per tool: the test measures what layer 2
    measures, over every tool of the app."""
    probes = {
        comparable(probe["phrase"]): probe["id"]
        for path in sorted(PROBES.glob("*-es-cart_checkout-*.json"))
        for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
    }
    assert len(probes) >= len(REPORTED)  # positive control: the probes of Cart & Checkout are read
    assert [probes.get(comparable(phrase)) for _, phrase in REPORTED] == [f"owner.es.{name}" for name, _ in REPORTED]
    assert {name for name, _ in REPORTED} == TOOLS


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_cart_request_is_offered_its_tool_without_being_its_asks(catalog_of, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, language := "es")
    assert name in tools  # positive control: the owner holds it, so the model can receive it
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get(language, ())}
    offered = [op.name for op in assistant.relevant(tools, [phrase], language)]
    assert name in offered, offered


#: What the QA's model ran instead of the cart's tool (hub#1100): asked to change the units of a cart's line, it changed
#: Inventory's product, which came before it.
CHOSEN_INSTEAD = [("cart_checkout.item.update", "inventory.product.update")]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "instead"), CHOSEN_INSTEAD)
def test_the_reported_cart_request_offers_its_tool_before_the_one_the_model_ran(catalog_of, name, instead):
    tools = catalog_of(Membership.Role.OWNER, "es")
    assert instead in tools  # positive control: the rival is offered to the owner too
    phrase = dict(REPORTED)[name]
    offered = [op.name for op in assistant.relevant(tools, [phrase], "es")]
    assert name in offered, offered
    if instead in offered:
        assert offered.index(name) < offered.index(instead), offered


#: What emptying a cart that stays active is not (hub#1100: the QA's model had no tool to empty it and said it could not
#: remove its lines): deleting the cart, which the person asked to keep, nor removing its lines one by one.
NOT_EMPTYING = ("cart_checkout.cart.delete", "cart_checkout.item.remove")


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("instead", NOT_EMPTYING)
def test_the_reported_request_to_empty_a_cart_offers_emptying_it_before_deleting_it_or_a_line(catalog_of, instead):
    tools = catalog_of(Membership.Role.OWNER, "es")
    offered = [op.name for op in assistant.relevant(tools, [dict(REPORTED)["cart_checkout.cart.clear"]], "es")]
    assert "cart_checkout.cart.clear" in offered, offered
    assert instead in offered, offered  # positive control: the rival is offered too, so their order is measured
    assert offered.index("cart_checkout.cart.clear") < offered.index(instead), offered


#: The cart's reads that give a line's id (``cart_checkout.item.update`` and ``.item.remove`` take it, never a product).
LINE_READS = {"cart_checkout.cart.get", "cart_checkout.item.list"}


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("name", ["cart_checkout.item.update", "cart_checkout.item.remove"])
def test_a_reported_change_of_a_line_is_offered_a_read_that_finds_the_line(catalog_of, name):
    """The person names the line by its product («el Café de QA-WEB-1»), the tool takes its id: the same turn offers a
    read of the cart that gives it, so the model finds the line instead of asking for its id."""
    tools = catalog_of(Membership.Role.OWNER, "es")
    offered = [op.name for op in assistant.relevant(tools, [dict(REPORTED)[name]], "es")]
    assert name in offered, offered
    assert LINE_READS & set(offered), offered


def test_the_hub_reads_a_cesta_as_a_cart_and_units_as_a_quantity():
    """``base.assistant.SYNONYMS``: «la cesta» or «el carrito» is a shopping cart (``cart_checkout.cart``), and «tres
    unidades» or «la cantidad» the quantity a line takes, never only Inventory's unit of measure: «la cantidad» names
    no unit of measure."""
    concepts = shared.asked(["cambia la cesta a tres unidades"], assistant.SYNONYMS).concepts
    assert any(shared.stem("cart") in concept for concept in concepts)
    assert any(shared.stem("quantity") in concept for concept in concepts)
    assert any(shared.stem("unit") in concept for concept in concepts)  # «unidades» still names the unit of measure
    quantity = shared.asked(["cambia la cantidad"], assistant.SYNONYMS).concepts
    assert any(shared.stem("quantity") in concept for concept in quantity)
    assert not any(shared.stem("unit") in concept for concept in quantity)
    assert not any(shared.stem("cart") in concept for concept in shared.asked(["la cesta"]).concepts)  # the Hub's own


#: Phrases nobody wrote as an ask or a probe, in the words a shop uses for its carts, with the tool they ask for: each is
#: among the first ten only because the Hub reads «cesta» as a cart (the first) or «unidades» and «cantidad» as a line's
#: quantity (the other two); without its group of ``SYNONYMS`` it comes 13th or lower.
BY_SYNONYM = [
    ("cart_checkout.cart.list", "¿cuántas cestas se han quedado a medias hoy?"),
    ("cart_checkout.item.update", "en la cesta de Lucía, que sean cuatro unidades de jabón"),
    ("cart_checkout.item.update", "cambia la cantidad del jabón de Lucía a cuatro"),
]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), BY_SYNONYM)
def test_a_cart_named_by_the_shops_words_is_offered_among_the_first_ten(catalog_of, name, phrase):
    tools = catalog_of(Membership.Role.OWNER, language := "es")
    assert comparable(phrase) not in {comparable(ask) for ask in shared.asks_of(tools[name]).get(language, ())}
    offered = [op.name for op in assistant.relevant(tools, [phrase], language)]
    assert name in offered[:10], offered.index(name) + 1 if name in offered else offered
