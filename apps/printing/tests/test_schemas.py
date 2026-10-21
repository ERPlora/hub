"""Schemas of the printing app: what an input refuses before any operation runs, and that every field says
what it is (they are the assistant's tools too)."""

import uuid

import pydantic
import pytest
from ninja import Schema

from apps.printing import schemas

INPUTS = [
    schemas.EmptyIn,
    schemas.SettingsPatchIn,
    schemas.PrinterIn,
    schemas.PrinterUpdateIn,
    schemas.PrinterRefIn,
    schemas.PrinterListIn,
    schemas.JobCreateIn,
    schemas.JobListIn,
    schemas.JobRefIn,
    schemas.JobCancelIn,
    schemas.JobClaimIn,
    schemas.JobCompleteIn,
    schemas.JobFailIn,
]
OUTPUTS = [
    schemas.SettingsOut,
    schemas.PrinterOut,
    schemas.PrinterStatusOut,
    schemas.JobOut,
    schemas.JobCreateOut,
    schemas.HostJobOut,
    schemas.JobClaimOut,
    schemas.JobAckOut,
    schemas.UsageSummary,
    schemas.JobSummaryOut,
]


def refused(schema: type[Schema], data: dict) -> list[dict]:
    with pytest.raises(pydantic.ValidationError) as caught:
        schema.model_validate(data)
    return caught.value.errors()


@pytest.mark.parametrize("schema", INPUTS + OUTPUTS)
def test_every_field_says_what_it_is(schema):
    for name, field in schema.model_fields.items():
        assert field.description, f"{schema.__name__}.{name}"


@pytest.mark.parametrize("schema", INPUTS)
def test_an_input_refuses_what_it_does_not_know(schema):
    errors = refused(schema, {"no_such_field": 1})
    assert any(error["type"] == "extra_forbidden" for error in errors)


def test_a_job_names_a_document_the_printer_knows():
    refused(schemas.JobCreateIn, {"document_type": "kitchn", "document": {}})
    job = schemas.JobCreateIn.model_validate({"document_type": "receipt", "document": {"total": 1}})
    assert (job.format, job.automatic, job.usage, job.printer, job.copies, job.job_key) == (
        "receipt",
        False,
        None,
        None,
        None,
        None,
    )


def test_an_a4_job_carries_its_page_and_only_an_a4_one():
    errors = refused(schemas.JobCreateIn, {"document_type": "invoice", "format": "a4"})
    assert "A4 page" in errors[0]["msg"]
    errors = refused(schemas.JobCreateIn, {"document_type": "receipt", "html": "<p>x</p>"})
    assert "A4" in errors[0]["msg"]
    page = schemas.JobCreateIn.model_validate({"document_type": "invoice", "format": "a4", "html": "<p>Invoice</p>"})
    assert page.html == "<p>Invoice</p>"


def test_an_a4_page_runs_no_script_and_has_a_size_limit():
    errors = refused(schemas.JobCreateIn, {"document_type": "invoice", "format": "a4", "html": "<script>x()</script>"})
    assert "script" in errors[0]["msg"]
    big = "<p>" + "x" * schemas.MAX_HTML_BYTES + "</p>"
    refused(schemas.JobCreateIn, {"document_type": "invoice", "format": "a4", "html": big})


@pytest.mark.parametrize(("field", "value"), [("copies", 0), ("copies", 6), ("job_key", ""), ("job_key", "k" * 129)])
def test_a_job_has_one_to_five_copies_and_a_key_up_to_128(field, value):
    refused(schemas.JobCreateIn, {"document_type": "receipt", field: value})


def test_a_printer_is_named_by_its_id_or_its_name():
    refused(schemas.PrinterRefIn, {})
    assert schemas.PrinterRefIn.model_validate({"printer": " Kitchen "}).printer == "Kitchen"
    some = uuid.uuid4()
    assert schemas.PrinterRefIn.model_validate({"printer_id": str(some)}).printer_id == some


def test_a_printer_change_says_which_one_and_what_changes():
    refused(schemas.PrinterUpdateIn, {"name": "Bar"})
    refused(schemas.PrinterUpdateIn, {"printer": "Till"})
    assert schemas.PrinterUpdateIn.model_validate({"printer": "Till", "is_active": False}).is_active is False


def test_a_new_printer():
    refused(schemas.PrinterIn, {"name": "", "kind": "network", "usage": "receipt"})
    refused(schemas.PrinterIn, {"name": "Till", "kind": "wifi", "usage": "receipt"})
    refused(schemas.PrinterIn, {"name": "Till", "kind": "network", "usage": "receipt", "paper_width": 76})
    printer = schemas.PrinterIn.model_validate({"name": " Till ", "kind": "network", "address": " 10.0.0.9 ", "usage": "receipt"})
    assert (printer.name, printer.address, printer.port, printer.paper_width, printer.is_active) == ("Till", "10.0.0.9", None, 80, True)


def test_a_role_is_one_of_the_four_never_a_free_word():
    # hub#457: «Kitchen», «kitchn» or «cocina» would open a queue that no printer ever drains.
    for usage in ("Kitchen", "kitchn", "cocina", " kitchen", ""):
        refused(schemas.PrinterIn, {"name": "Till", "kind": "network", "usage": usage})
        refused(schemas.PrinterUpdateIn, {"printer": "Till", "usage": usage})
        refused(schemas.JobCreateIn, {"document_type": "receipt", "document": {}, "usage": usage})
        refused(schemas.SettingsPatchIn, {usage: "Till"})
    assert schemas.JobCreateIn.model_validate({"document_type": "receipt", "document": {}, "usage": "kitchen"}).usage == "kitchen"


def test_a_job_is_named_by_its_id_or_its_document_reference():
    refused(schemas.JobRefIn, {})
    assert schemas.JobRefIn.model_validate({"reference": "T-000123"}).reference == "T-000123"
    assert schemas.JobCancelIn.model_validate({"reference": "T-1"}).reason == ""


def test_a_claim_names_the_printers_the_device_reaches_and_the_device():
    refused(schemas.JobClaimIn, {"printers": [], "device": "Till 1"})
    refused(schemas.JobClaimIn, {"printers": [str(uuid.uuid4()) for _ in range(21)], "device": "Till 1"})
    refused(schemas.JobClaimIn, {"printers": [str(uuid.uuid4())], "device": ""})


def test_a_failure_says_why():
    refused(schemas.JobFailIn, {"job_id": str(uuid.uuid4()), "error": "", "device": "A", "attempt": 1})
    long = schemas.JobFailIn.model_validate({"job_id": str(uuid.uuid4()), "error": "e" * 900, "device": "A", "attempt": 1})
    assert len(long.error) == 500


@pytest.mark.parametrize("schema", [schemas.PrinterListIn, schemas.JobListIn])
def test_a_list_pages_up_to_100(schema):
    refused(schema, {"limit": 101})
    assert schema.model_validate({}).limit == 50


def test_the_settings_patch_takes_copies_up_to_3():
    refused(schemas.SettingsPatchIn, {"receipt_copies": 4})
    patch = schemas.SettingsPatchIn.model_validate({"kitchen_printer": None})
    assert patch.model_dump(exclude_unset=True) == {"kitchen_printer": None}


def test_a_document_holds_json_values_only():
    from decimal import Decimal

    errors = refused(schemas.JobCreateIn, {"document_type": "receipt", "document": {"total": Decimal("1.50")}})
    assert errors[0]["loc"][:2] == ("document", "total")


def test_an_a4_page_prints_once():
    errors = refused(schemas.JobCreateIn, {"document_type": "invoice", "format": "a4", "html": "<p>F</p>", "copies": 2})
    assert "prints once" in errors[0]["msg"]


def test_the_currency_is_an_iso_code():
    refused(schemas.JobCreateIn, {"document_type": "receipt", "currency": "euro"})
    assert schemas.JobCreateIn.model_validate({"document_type": "receipt", "currency": "JPY"}).currency == "JPY"


def test_the_device_says_who_it_is_and_which_hand_out_it_answers():
    some = str(uuid.uuid4())
    refused(schemas.JobCompleteIn, {"job_id": some})
    refused(schemas.JobFailIn, {"job_id": some, "error": "x", "device": "A", "attempt": 0})
    assert schemas.JobCompleteIn.model_validate({"job_id": some, "device": "A", "attempt": 1}).attempt == 1
