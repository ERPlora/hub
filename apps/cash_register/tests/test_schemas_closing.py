"""What the closing preview takes and gives: the open session by default and a counted cash never negative; and the
figures the assistant's card shows the close with, as money and with the difference signed."""

from apps.cash_register.schemas.closing import ClosingSummaryIn, ClosingSummaryOut
from apps.cash_register.schemas.fields import DRAWER
from apps.cash_register.tests.schema_checks import refused


def test_the_closing_preview_is_of_the_open_session_with_a_counted_cash_never_negative():
    preview = ClosingSummaryIn.model_validate({})
    assert (preview.session_id, preview.session, preview.closing_balance) == (None, None, None)
    named = ClosingSummaryIn.model_validate({"session": " S-261014-0001 ", "closing_balance": 0})
    assert (named.session, named.closing_balance) == ("S-261014-0001", 0)
    assert refused(ClosingSummaryIn, closing_balance=-1) == ["closing_balance"]
    assert refused(ClosingSummaryIn, closing_notes="late") == ["closing_notes"]


def test_the_closing_preview_shows_its_amounts_as_money_and_signs_the_difference():
    fields = ClosingSummaryOut.model_json_schema()["properties"]
    amounts = ("opening_balance", "closing_balance", "expected_balance", "difference")
    assert all(fields[name]["money"] for name in amounts)
    assert [name for name, field in fields.items() if field.get("signed")] == ["difference"]
    assert fields["register_name"]["title"] == DRAWER
    assert all(fields[name].get("title") for name in ("number", "expected_balance"))
    assert set(ClosingSummaryOut.model_fields["pending"].annotation.model_fields) == {
        "open_checks", "open_check_labels", "unserved", "unserved_labels", "prints", "print_usages", "incomplete",
    }
