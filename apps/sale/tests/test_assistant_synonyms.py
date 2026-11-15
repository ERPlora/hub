"""What Sales' words mean to the Hub's assistant (``SaleConfig.assistant_synonyms``, gathered by
``base.assistant.synonyms``): a «cuenta», a check or a tab is a table's open check (``sale.order``), never the
person's account, and a «ticket», a «tique» or a receipt is a sale's."""

from django.apps import apps
from live import assistant as shared

from base import assistant


def test_the_hub_reads_a_cuenta_as_an_order_and_a_tique_as_a_sale():
    """Sales says these words itself: the platform's own words do not, and without any of the Hub's groups neither
    does live (positive control)."""
    order, sale = shared.stem("order"), shared.stem("sale")
    said = apps.get_app_config("sale").assistant_synonyms
    for phrase, wanted in (
        ("divide la cuenta entre tres", order),
        ("what's on the tab?", order),
        ("reimprime el último tique", sale),
    ):
        assert any(wanted in concept for concept in shared.asked([phrase], said).concepts), phrase
        assert not any(wanted in concept for concept in shared.asked([phrase], assistant.SYNONYMS).concepts), phrase
        assert not any(wanted in concept for concept in shared.asked([phrase]).concepts), phrase
