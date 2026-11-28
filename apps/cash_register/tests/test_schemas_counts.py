"""A count of the drawer: notes and coins or a total, and the counts of one named session."""

from apps.cash_register.schemas.counts import CountAddIn, CountListIn
from apps.cash_register.tests.schema_checks import refused


def test_a_count_takes_notes_and_coins_or_a_total():
    count = CountAddIn.model_validate(
        {"denominations": {"bills": {"50": 2}, "coins": {"0.50": 3}}}
    )
    assert count.type == "closing"
    assert CountAddIn.model_validate({"total": 0}).total == 0
    assert refused(CountAddIn) == [""]
    assert refused(CountAddIn, denominations={"bills": {"fifty": 2}}) == [
        "denominations.bills.fifty.[key]"
    ]
    assert refused(CountAddIn, denominations={"coins": {"0.50": -1}}) == [
        "denominations.coins.0.50"
    ]
    assert refused(CountAddIn, total=-1) == ["total"]


def test_a_count_list_names_its_session():
    assert refused(CountListIn) == [""]
    CountListIn.model_validate({"session_id": "0199e4f0-0000-7000-8000-000000000000"})
