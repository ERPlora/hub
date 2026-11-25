"""Schemas of the print jobs: what a job asked for carries, how one is named, and the A4 page."""

import pytest

from apps.printing.schemas.jobs import MAX_HTML_BYTES, JobCancelIn, JobCreateIn, JobRefIn

from .test_schemas_fields import refused


def test_a_job_names_a_document_the_printer_knows():
    refused(JobCreateIn, {"document_type": "kitchn", "document": {}})
    job = JobCreateIn.model_validate({"document_type": "receipt", "document": {"total": 1}})
    assert (job.format, job.automatic, job.usage, job.printer, job.copies, job.job_key) == (
        "receipt",
        False,
        None,
        None,
        None,
        None,
    )


def test_an_a4_job_carries_its_page_and_only_an_a4_one():
    errors = refused(JobCreateIn, {"document_type": "invoice", "format": "a4"})
    assert "A4 page" in errors[0]["msg"]
    errors = refused(JobCreateIn, {"document_type": "receipt", "html": "<p>x</p>"})
    assert "A4" in errors[0]["msg"]
    page = JobCreateIn.model_validate({"document_type": "invoice", "format": "a4", "html": "<p>Invoice</p>"})
    assert page.html == "<p>Invoice</p>"


def test_an_a4_page_runs_no_script_and_has_a_size_limit():
    errors = refused(JobCreateIn, {"document_type": "invoice", "format": "a4", "html": "<script>x()</script>"})
    assert "script" in errors[0]["msg"]
    big = "<p>" + "x" * MAX_HTML_BYTES + "</p>"
    refused(JobCreateIn, {"document_type": "invoice", "format": "a4", "html": big})


@pytest.mark.parametrize(("field", "value"), [("copies", 0), ("copies", 6), ("job_key", ""), ("job_key", "k" * 129)])
def test_a_job_has_one_to_five_copies_and_a_key_up_to_128(field, value):
    refused(JobCreateIn, {"document_type": "receipt", field: value})


def test_a_job_is_named_by_its_id_or_its_document_reference():
    refused(JobRefIn, {})
    assert JobRefIn.model_validate({"reference": "T-000123"}).reference == "T-000123"
    assert JobCancelIn.model_validate({"reference": "T-1"}).reason == ""


def test_a_document_holds_json_values_only():
    from decimal import Decimal

    errors = refused(JobCreateIn, {"document_type": "receipt", "document": {"total": Decimal("1.50")}})
    assert errors[0]["loc"][:2] == ("document", "total")


def test_an_a4_page_prints_once():
    errors = refused(JobCreateIn, {"document_type": "invoice", "format": "a4", "html": "<p>F</p>", "copies": 2})
    assert "prints once" in errors[0]["msg"]


def test_the_currency_is_an_iso_code():
    refused(JobCreateIn, {"document_type": "receipt", "currency": "euro"})
    assert JobCreateIn.model_validate({"document_type": "receipt", "currency": "JPY"}).currency == "JPY"
