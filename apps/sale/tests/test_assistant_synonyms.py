"""What Sales' words mean to the Hub's assistant (``SaleConfig.assistant_synonyms``, gathered by
``base.assistant.relevance.synonyms``): a «cuenta», a check or a tab is a table's open check (``sale.order``), never the
person's account, and a «ticket», a «tique» or a receipt is a sale's."""

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
