"""What layer 1 of the assistant's QA does not say of Inventory: how many tools it offers, and that the owner's requests
of the real-model QA, in the owner's own words, are offered their existing operation.

Every ask of every tool of inventory bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (inventory is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over
the asks and the guard that no ask copies a probe of layer 2.
"""

import pytest
from live import assistant as shared
from live.operations import AI, registry

from base import assistant
from base.models import Membership
from base.tests.test_assistant_asks import (
    TOP,
    assert_offered_with_room,
    catalog_of,  # noqa: F401 (a fixture: the tests below take it by name)
    comparable,
    place_of_no_ask,
    probe_phrases,
)

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
    """``base.assistant.SYNONYMS``: «unidades» are the units of measure of ``inventory.unit.*`` and «el albarán» or
    «la mercancía que entra» what ``inventory.stock.receive`` records, so the owner's words reach those tools without
    their own asks; without the Hub's groups, none of them does (positive control)."""
    unit, receive = shared.stem("unit"), shared.stem("receive")
    for phrase, wanted in (
        ("¿qué unidades tengo configuradas?", unit),
        ("registra el albarán del proveedor", receive),
        ("entran 20 cafés más", receive),
    ):
        concepts = shared.asked([phrase], assistant.SYNONYMS).concepts
        assert any(wanted in concept for concept in concepts), phrase
        assert not any(wanted in concept for concept in shared.asked([phrase]).concepts), phrase


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_inventory_request_offers_its_existing_operation(catalog_of, name, phrase):
    assert place_of_no_ask(catalog_of(Membership.Role.OWNER, "es"), name, phrase) is not None


#: Goods received said as a business says it, in words that are none of the tool's asks nor a probe: «la mercancía» is
#: what ``inventory.stock.receive`` records only through ``base.assistant.SYNONYMS`` (37th of 40 without them).
GOODS_IN = [("inventory.stock.receive", "apunta la mercancía que nos ha traído hoy el proveedor")]


@pytest.mark.django_db
@pytest.mark.parametrize(("name", "phrase"), GOODS_IN)
def test_goods_received_in_the_hubs_words_bring_the_reception_among_the_first_ten(catalog_of, name, phrase):
    assert comparable(phrase) not in probe_phrases()
    assert_offered_with_room(catalog_of(Membership.Role.OWNER, "es"), name, phrase, room=TOP)
