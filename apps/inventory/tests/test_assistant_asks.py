"""What layer 1 of the assistant's QA does not say of Inventory: how many tools it offers, and that the owner's requests
of the real-model QA, in the owner's own words, are offered their existing operation.

Every ask of every tool of inventory bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (inventory is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over
the asks and the guard that no ask copies a probe of layer 2.
"""

import pytest
from django.apps import apps
from live import assistant as shared
from live.context import OperationContext
from live.operations import AI, get, registry

from base import assistant
from base.models import Membership
from base.permissions import permissions_for
from base.tenancy.tests.business import A
from base.tests.test_assistant_asks import assert_its_words_name
from base.tests.test_assistant_asks import (
    TOP,
    assert_offered_with_room,
    comparable,
    offered_to,
    place_of_no_ask,
    probe_phrases,
)

from .conftest import HUB_DB

#: The requests of the real-model QA (``qa20261108.owner.es.inventory.*``), as the owner said them: each is offered its
#: existing operation (among the ``MAX_TOOLS`` a turn offers, so the model can choose it), without being one of its
#: asks.
REPORTED = [
    ("inventory.movement.list", "pásame el historial reciente de entradas, salidas y ajustes de almacén"),
    ("inventory.product_category.list", "dime en qué familia está clasificado cada artículo que sale en el TPV"),
    (
        "inventory.unit.list",
        "¿qué unidades tengo configuradas ahora mismo en Inventario para vender y medir productos, sin consultar la "
        "documentación?",
    ),
    ("inventory.stock.receive", "registra que entran 20 cafés más a 0,55 € la unidad con el albarán ALB-QA-01"),
    ("inventory.product_category.add", "clasifica el Café dentro de Cafetería QA para que aparezca ahí en el TPV"),
    ("inventory.product.set_sold_out", "marca Té QA como agotado para que deje de ofrecerse sin darlo de baja"),
    ("inventory.stock.write_off", "da de baja 2 unidades de Café por rotura durante la limpieza, motivo «mermas QA»"),
]


def test_inventory_offers_at_least_30_tools():
    """Inventory's tools are at least 30 (``AI``, never ``INTERNAL``): a silent drop of tools fails."""
    tools = {name for name, op in registry.items() if op.app_label == "inventory" and isinstance(op.ai_spec(), AI)}
    assert len(tools) >= 30


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, phrase in REPORTED] == [
        f"qa20261108.owner.es.{name}" for name, _ in REPORTED
    ]


def test_the_hub_reads_units_as_units_and_a_delivery_note_as_goods_received():
    """``InventoryConfig.assistant_synonyms`` (gathered by ``base.assistant.relevance.synonyms``): «unidades» are the
    units of measure of ``inventory.unit.*`` and «el albarán» or «la mercancía que entra» what
    ``inventory.stock.receive`` records, so the owner's words reach those tools without their own asks; the platform's
    own words (``base.assistant.relevance.SYNONYMS``) do not say it, and without the Hub's groups none of them does (positive
    control)."""
    unit, receive = shared.stem("unit"), shared.stem("receive")
    assert_its_words_name(
        "inventory",
        [
            ("¿qué unidades tengo configuradas?", unit),
            ("registra el albarán del proveedor", receive),
            ("entran 20 cafés más", receive),
        ],
    )


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_inventory_request_offers_its_existing_operation(catalog_of, name, phrase):
    assert place_of_no_ask(catalog_of(Membership.Role.OWNER, "es"), name, phrase) is not None


#: Goods received said as a business says it, in words that are none of the tool's asks nor a probe: «la mercancía» is
#: what ``inventory.stock.receive`` records only through Inventory's ``assistant_synonyms`` (37th of 40 without them),
#: and «han entrado» is read as its present «entran» (152nd, behind the cart's items, before live read it so).
GOODS_IN = [
    ("inventory.stock.receive", "apunta la mercancía que nos ha traído hoy el proveedor"),
    ("inventory.stock.receive", "apunta que han entrado 12 unidades de tarta"),
]


@HUB_DB
@pytest.mark.parametrize(("name", "phrase"), GOODS_IN)
def test_goods_received_in_the_hubs_words_bring_the_reception_among_the_first_ten(catalog_of, name, phrase):
    assert comparable(phrase) not in probe_phrases()
    assert_offered_with_room(catalog_of(Membership.Role.OWNER, "es"), name, phrase, room=TOP)


#: Goods received said as a quantity in a unit, without «mercancía» nor «albarán»: since Cash register reads «una
#: entrada» as a movement of the drawer, its movement came first and the reception fell far out of the tools a turn
#: offers (102nd for the owner, 92nd for the manager, with «registra una entrada de 20 kilos de harina»). Each case
#: says the unit that names the goods.
QUANTITY_IN = [
    ("es", "registra una entrada de 20 kilos de harina", "kilos de"),
    ("es", "apunta una entrada de 20 kilos de harina", "kilos de"),
    ("es", "registra una entrada de 5 cajas de leche", "cajas de"),
    ("es", "apunta una entrada de 12 cajas de leche", "cajas de"),
    ("es", "registra la entrada de 20 kilos de harina", "kilos de"),
    ("en", "record an entry of 20 kilos of flour", "kilos of"),
    ("en", "record an entry of 12 boxes of milk", "boxes of"),
]


def assert_its_words_bring_the_reception(tools, language: str, phrase: str, words: str) -> None:
    """That ``phrase`` brings ``inventory.stock.receive`` among the first ten, and that without ``words`` among the
    Hub's words it does not: they are what names the goods."""
    assert comparable(phrase) not in probe_phrases()
    assert_offered_with_room(tools, "inventory.stock.receive", phrase, language, room=TOP)
    counted = assistant.relevance.ranking(tools)["synonyms"]
    without = tuple(tuple(word for word in group if word != words) for group in counted)
    assert without != counted  # positive control: the words are some of the Hub's
    assert "inventory.stock.receive" not in offered_to(tools, phrase, language, synonyms=without)[:TOP]


@HUB_DB
@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.MANAGER])
@pytest.mark.parametrize(("language", "phrase", "unit"), QUANTITY_IN)
def test_goods_said_as_a_quantity_in_a_unit_bring_the_reception_among_the_first_ten(
    catalog_of, role, language, phrase, unit
):
    assert_its_words_bring_the_reception(catalog_of(role, language), language, phrase, unit)


#: Goods noted down as arrived: «llegar» named nothing, so «apunta que han llegado 12 unidades de tarta» left the
#: reception 149th for the owner, behind a cart's items («apunta que llegan…» 159th, «registra que han llegado…» 88th).
#: Each case says the words that name the goods.
GOODS_ARRIVED = [
    ("apunta que han llegado 12 unidades de tarta", "apunta que llegan"),
    ("apunta que llegan 12 unidades de tarta", "apunta que llegan"),
    ("apúntame que han llegado 24 latas de cerveza", "apuntame que llegan"),
    ("anota que han llegado 12 unidades de tarta", "anota que llegan"),
    ("registra que han llegado 12 unidades de tarta", "registra que llegan"),
    ("registra que han llegado 6 botellas de vino", "registra que llegan"),
]


@HUB_DB
@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.MANAGER])
@pytest.mark.parametrize(("phrase", "words"), GOODS_ARRIVED)
def test_goods_noted_as_arrived_bring_the_reception_among_the_first_ten(catalog_of, role, phrase, words):
    assert_its_words_bring_the_reception(catalog_of(role, "es"), "es", phrase, words)


#: What arrives and is not goods, in Spanish and in English: people (a booking, more diners for a table, the customer of
#: an appointment, staff) and the tickets or invoices that reach somewhere.
NOT_GOODS_ARRIVING = [
    "han llegado los de la reserva de Luis, siéntalos",
    "ya llegan los de la reserva de las nueve, pásalos a su mesa",
    "han llegado dos más para la mesa 7",
    "ha llegado la clienta de la cita de las 10, empieza el servicio",
    "han llegado Pedro y Ana, fíchalos",
    "enséñame las comandas que llegan a cocina",
    "¿han llegado las facturas a Hacienda?",
    "Luis's party has arrived, seat them",
    "two more have arrived for table 7",
    "the 10 o'clock client has arrived, start her service",
    "Pedro and Ana have arrived, clock them in",
    "show me the tickets that arrive in the kitchen",
    "have the invoices arrived at the tax agency?",
]


def test_the_hub_reads_goods_noted_as_arrived_as_goods_and_nothing_else_that_arrives():
    """Inventory's own words: what someone notes down as arrived («apunta que han llegado…», read «apunta que
    llegan…») is goods received and their stock, and without the Hub's groups it is neither (positive control); the
    people who arrive, and what reaches the kitchen or the tax agency, are neither."""
    stock, receive = shared.stem("stock"), shared.stem("receive")
    said = [phrase for phrase, _ in GOODS_ARRIVED]
    assert_its_words_name("inventory", [(phrase, wanted) for phrase in said for wanted in (stock, receive)])
    own = apps.get_app_config("inventory").assistant_synonyms
    named = [
        phrase
        for phrase in NOT_GOODS_ARRIVING
        if any(stock in concept or receive in concept for concept in shared.asked([phrase], own).concepts)
    ]
    assert named == []


#: A quantity in a unit written off: the goods it names are also the stock a write-off acts on, so the reception the
#: same words bring never pushes it out of the first ten (24th if they named only the goods).
QUANTITY_OUT = [
    ("es", "da de baja 2 kilos de harina por rotura"),
    ("en", "write off 2 kilos of flour, they got wet"),
]


@HUB_DB
@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.MANAGER])
@pytest.mark.parametrize(("language", "phrase"), QUANTITY_OUT)
def test_a_quantity_in_a_unit_written_off_keeps_the_write_off_among_the_first_ten(catalog_of, role, language, phrase):
    assert comparable(phrase) not in probe_phrases()
    assert_offered_with_room(catalog_of(role, language), "inventory.stock.write_off", phrase, language, room=TOP)


#: What a quantity in a unit is not, in Spanish and in English: money in or out of the drawer, what a sale line or a cart
#: counts, the tills of a place. None of them names the stock nor the goods received.
NO_QUANTITY_OF_GOODS = [
    "apúntame una entrada de 50 €",
    "una salida de 20 € del cajón",
    "añade 2 botellas de agua a la mesa 5",
    "¿cuántas unidades de cada producto lleva el carrito de Nuria?",
    "enséñame las cajas del local",
    "medio kilo de jamón para la mesa 3",
    "record a cash entry of 50 €",
    "add 2 bottles of water to table 5",
    "how many units of each product are in Nuria's cart?",
    "half a kilo of ham for table 3",
]


def test_the_hub_reads_a_quantity_in_a_unit_as_the_stock_of_goods_and_an_amount_as_neither():
    """Inventory's own words (its ``assistant_synonyms``): kilos, grams, litres, boxes or sacks of a product are its
    stock (``inventory.stock``) and goods (``inventory.stock.receive``), and without the Hub's groups neither is
    (positive control); an amount of money, bottles of a sale line, units in a cart and the tills of a place name
    neither."""
    stock, receive = shared.stem("stock"), shared.stem("receive")
    said = [
        "registra una entrada de 20 kilos de harina",
        "apunta una entrada de 12 cajas de leche",
        "han llegado 3 sacos de patatas",
        "apunta una entrada de 500 gramos de azafrán",
        "registra una entrada de 10 litros de aceite",
        "apunta una entrada de 6 kg de queso",
        "record an entry of 20 kg of flour",
        "log 12 boxes of milk",
        "record 500 grams of saffron",
        "log 10 litres of oil",
        "log 10 liters of oil",
    ]
    assert_its_words_name("inventory", [(phrase, wanted) for phrase in said for wanted in (stock, receive)])
    own = apps.get_app_config("inventory").assistant_synonyms
    named = [
        phrase
        for phrase in NO_QUANTITY_OF_GOODS
        if any(stock in concept or receive in concept for concept in shared.asked([phrase], own).concepts)
    ]
    assert named == []


def offered_by_a_turn(make_user, language: str, text: str) -> list[str]:
    """The tools a turn of the assistant offers the owner of business A for ``text``, said alone, by their tool names."""
    user = make_user("olga", host=A.key, role=Membership.Role.OWNER)
    ctx = OperationContext(scope=A, actor=user, permissions=permissions_for(user, A), language=language)
    op = get("base.assistant.turn")
    plan = op(ctx, op.input(messages=[{"role": "user", "content": text}])).model_dump(mode="json")
    return [tool["name"] for tool in plan["tools"]]


@HUB_DB
def test_taking_one_product_off_the_menu_and_repricing_another_brings_both_writes(make_user):
    tools = offered_by_a_turn(make_user, "es", "Quita el flan casero de la carta y pon el café con leche a 1,90 €")

    assert {"inventory__product__delete", "inventory__product__update"} <= set(tools)


@HUB_DB
def test_putting_a_product_with_the_other_desserts_of_the_menu_brings_a_way_to_its_category(make_user):
    tools = offered_by_a_turn(make_user, "es", "Sí, ponla con los otros postres de la carta, como un postre más.")

    assert {"inventory__category__list", "inventory__product_category__add"} & set(tools)


@HUB_DB
def test_bottles_that_got_broken_bring_the_write_off(make_user):
    assert "inventory__stock__write_off" in offered_by_a_turn(make_user, "en", "Three bottles of water got broken")


def test_the_hub_reads_the_menu_as_the_products_and_what_broke_as_breakage():
    """Inventory's own words: a restaurant's «carta» is its products, and «roto» and «broken» are one word, the
    breakage a write-off records; neither the platform's words nor live alone say so (positive control)."""
    assert_its_words_name(
        "inventory",
        [
            ("quita el flan casero de la carta", shared.stem("product")),
            ("se han roto tres botellas de agua", shared.stem("broke")),
            ("three bottles of water got broken", shared.stem("roto")),
        ],
    )
