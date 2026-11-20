"""What Sales' words mean to the Hub's assistant (``SaleConfig.assistant_synonyms``, gathered by
``base.assistant.relevance.synonyms``): a «cuenta», a check or a tab is a table's open check (``sale.order``), never the
person's account, a «ticket», a «tique» or a receipt is a sale's, and a text set up «para marcarlo rápido» is a quick
note of the till."""

from django.apps import apps
from live import assistant as shared

from base.tests.test_assistant_asks import assert_its_words_name


def test_the_hub_reads_a_cuenta_as_an_order_and_a_tique_as_a_sale():
    """Sales says these words itself: the platform's own words do not, and without any of the Hub's groups neither
    does live (positive control)."""
    order, sale = shared.stem("order"), shared.stem("sale")
    assert_its_words_name(
        "sale",
        [("divide la cuenta entre tres", order), ("what's on the tab?", order), ("reimprime el último tique", sale)],
    )


#: «Rápido», «marcar» and «aviso» said of anything but a quick note of the till: a message to a customer, an alert of
#: the stock, charging or adding fast, marking an invoice as paid or a ticket as served.
OTHER_QUICK_THINGS = [
    "manda un aviso rápido a Ana por WhatsApp",
    "avísame rápido si se acaba la harina",
    "cóbrame rápido la mesa 4",
    "añade rápido un café a la mesa 4",
    "la factura de Luis, quiero marcarla rápido como pagada",
    "hay que marcarlo rápido como servido, la comanda de la 12",
    "la tarea de limpiar, márcala rápido como hecha",
]


def test_the_hub_reads_para_marcarlo_rapido_as_a_quick_note_and_no_other_quick_thing():
    """Sale's own words (its ``assistant_synonyms``): «para marcarlo rápido» or «para marcarla rápido» is a quick note
    of the till (``sale.quick_note``), and without the Hub's groups neither is (positive control); «rápido», «marcar»
    and «aviso» said otherwise name no quick note."""
    quick = shared.stem("quick")
    assert_its_words_name(
        "sale",
        [
            ("deja preparado el aviso «Sin cilantro QA» para marcarlo rápido al apuntar platos", quick),
            ("prepara un aviso «sin gluten» para marcarlo rápido", quick),
            ("prepara «para llevar» para marcarla rápido", quick),
        ],
    )
    own = apps.get_app_config("sale").assistant_synonyms
    named = [said for said in OTHER_QUICK_THINGS if any(quick in one for one in shared.asked([said], own).concepts)]
    assert named == []
