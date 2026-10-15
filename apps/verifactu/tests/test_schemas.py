"""The inputs of the verifactu app's operations: what each one accepts and the 422 of what it does not (the same
schema the route, the live subscription and the assistant validate with)."""

import datetime as dt
import uuid

import pydantic
import pytest

from apps.verifactu import schemas


def refused(schema, data: dict) -> dict:
    with pytest.raises(pydantic.ValidationError) as error:
        schema.model_validate(data)
    return {
        ".".join(map(str, item["loc"])) or "__root__": item["msg"]
        for item in error.value.errors()
    }


def test_a_record_is_named_by_its_id_or_by_its_invoices_number():
    assert (
        schemas.RecordRefIn.model_validate(
            {"invoice_number": " TICKET-2026-000001 "}
        ).invoice_number
        == "TICKET-2026-000001"
    )
    record_id = uuid.uuid7()
    assert (
        schemas.RecordRefIn.model_validate({"record_id": str(record_id)}).record_id
        == record_id
    )
    assert "Say which record" in next(
        iter(refused(schemas.RecordRefIn, {"invoice_number": "  "}).values())
    )


def test_a_record_is_created_from_an_invoice_by_its_id_or_its_number():
    assert (
        schemas.RecordCreateIn.model_validate({"number": "FACT-2026-000001"}).number
        == "FACT-2026-000001"
    )
    assert refused(schemas.RecordCreateIn, {})


def test_the_create_input_takes_the_invoices_notice_as_it_comes():
    # invoice.invoice.issued carries more keys than an invoice's id: the reaction ignores them.
    data = schemas.RecordCreateIn.model_validate(
        {"invoice_id": str(uuid.uuid7()), "number": "T-1", "total": 100}
    )
    assert data.invoice_id is not None


def test_a_cancellation_says_why():
    errors = refused(schemas.RecordCancelIn, {"invoice_number": "T-1", "reason": ""})
    assert "reason" in errors
    assert (
        schemas.RecordCancelIn.model_validate(
            {"invoice_number": "T-1", "reason": "Duplicate"}
        ).reason
        == "Duplicate"
    )


def test_lists_page_at_most_a_hundred():
    assert schemas.RecordListIn.model_validate({}).limit == 50
    assert "limit" in refused(schemas.RecordListIn, {"limit": 101})
    assert "limit" in refused(schemas.EventListIn, {"limit": 0})


def test_the_record_list_filters_and_sorts_by_what_it_shows():
    data = schemas.RecordListIn.model_validate(
        {
            "status": "rejected",
            "environment": "production",
            "record_type": "anulacion",
            "invoice_type": "R5",
            "sort": "sequence",
            "dir": "asc",
        }
    )
    assert (data.status, data.environment, data.sort) == (
        "rejected",
        "production",
        "sequence",
    )
    assert "status" in refused(schemas.RecordListIn, {"status": "error"})
    assert "sort" in refused(schemas.RecordListIn, {"sort": "xml"})


def test_a_manual_anchor_is_a_64_hexadecimal_fingerprint_with_its_invoice():
    data = schemas.RecoverManualIn.model_validate(
        {
            "fingerprint": " " + "ab" * 32 + " ",
            "invoice_number": "OLD-1",
            "issue_date": "2026-10-01",
        }
    )
    assert data.fingerprint == "AB" * 32
    assert data.issue_date == dt.date(2026, 10, 1)
    errors = refused(
        schemas.RecoverManualIn,
        {"fingerprint": "XYZ", "invoice_number": "OLD-1", "issue_date": "2026-10-01"},
    )
    assert errors["fingerprint"].endswith(
        "The fingerprint must be 64 hexadecimal characters."
    )
    errors = refused(schemas.RecoverManualIn, {"fingerprint": "A" * 64})
    assert set(errors) == {"invoice_number", "issue_date"}


def test_the_route_is_erplora_or_own():
    assert schemas.ConfigUpdateIn.model_validate({"route": "own"}).route == "own"
    assert "route" in refused(schemas.ConfigUpdateIn, {"route": "gateway"})


def test_the_photo_no_longer_carries_the_certificate():
    """The certificate is uploaded in the Hub (Ioan, 2026-10-15): an older photo that still names it is read
    without it."""
    assert "own_certificate" not in schemas.ConfigSyncIn.model_fields
    data = schemas.ConfigSyncIn.model_validate(
        {"version": 1, "own_certificate": {"loaded": True, "holder": "ANA"}}
    )
    assert "own_certificate" not in data.model_dump()


def test_the_photo_no_longer_carries_the_multiple_taxpayers_indicator():
    """IndicadorMultiplesOT is always «S» (ERPlora serves many taxpayers, T2b): an older photo that still names
    it is read without it."""
    assert "multiple_taxpayers" not in schemas.ConfigSyncIn.model_fields
    data = schemas.ConfigSyncIn.model_validate({"version": 1, "multiple_taxpayers": "N"})
    assert "multiple_taxpayers" not in data.model_dump()


def test_the_accounts_photo():
    data = schemas.ConfigSyncIn.model_validate(
        {
            "version": 7,
            "representation": {
                "status": "approved",
                "updated_at": "2026-10-02T10:00:00Z",
                "reason": "",
            },
        }
    )
    assert data.version == 7
    assert data.representation.status == "approved"
    assert "live_paid" in refused(
        schemas.ConfigSyncIn, {"version": 1, "live_paid": "maybe"}
    )
    assert "version" in refused(schemas.ConfigSyncIn, {})


def test_an_aeat_query_month_is_one_to_twelve():
    assert "month" in refused(schemas.AeatQueryIn, {"month": 13})
    assert schemas.AeatQueryIn.model_validate({"year": 2026, "month": 8}).month == 8
