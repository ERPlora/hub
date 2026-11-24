"""Inputs of the numbering series: a code is written in capitals, a format needs its year and its sequence, and what goes
in a number is printable ASCII. Each refusal names its field before anything runs."""

import pytest
from pydantic import ValidationError

from apps.invoice.schemas.series import SERIES_CODE_INVALID, SeriesCreateIn, SeriesUpdateIn
from apps.invoice.tests.conftest import fields


def test_a_series_code_is_written_in_capitals():
    data = SeriesCreateIn.model_validate(
        {"code": " shop-1 ", "invoice_type": "F1", "year": 2026}
    )
    assert data.code == "SHOP-1"
    with pytest.raises(ValidationError) as refused:
        SeriesCreateIn.model_validate(
            {"code": "shop 1", "invoice_type": "F1", "year": 2026}
        )
    assert fields(refused.value) == {"code"}


@pytest.mark.parametrize("wrong", ["E2E-?", "-A", "_A", "AÑO", "É1", "A B", "A.B", "A/B"])
def test_a_series_code_of_another_shape_is_refused_with_its_own_message(wrong):
    """hub#872: what a code takes, as the format of the number says its own (never pydantic's pattern)."""
    with pytest.raises(ValidationError) as refused:
        SeriesCreateIn.model_validate({"code": wrong, "invoice_type": "F1", "year": 2026})
    [error] = refused.value.errors()
    assert (error["loc"], error["type"], str(error["ctx"]["error"])) == (
        ("code",),
        "value_error",
        str(SERIES_CODE_INVALID),
    )


@pytest.mark.parametrize("right", ["A", "9", "FACT", "E2E_1-B", "a-1", "X" * 20])
def test_a_series_code_of_the_right_shape_is_taken(right):
    """Positive control: letters (in any case), digits, hyphens and underscores, from a letter or a digit."""
    data = SeriesCreateIn.model_validate({"code": right, "invoice_type": "F1", "year": 2026})
    assert data.code == right.upper()


def test_a_series_code_still_tells_its_shape_to_the_openapi_and_the_assistant():
    """The code's own check (hub#872) keeps the shape in the JSON Schema the OpenAPI and the assistant's tool read."""
    code = SeriesCreateIn.model_json_schema()["properties"]["code"]
    assert (code["pattern"], code["minLength"], code["maxLength"]) == (r"^[A-Z0-9][A-Z0-9_-]*$", 1, 20)


def test_a_series_format_needs_its_year_and_its_sequence():
    # Without the year, the series of the next year (born from this one) would repeat its numbers.
    for wrong in ("{prefix}-{year}", "{prefix}-{seq}"):
        with pytest.raises(ValidationError) as refused:
            SeriesCreateIn.model_validate(
                {"code": "A", "invoice_type": "F1", "year": 2026, "format": wrong}
            )
        assert fields(refused.value) == {"format"}
        with pytest.raises(ValidationError) as refused:
            SeriesUpdateIn.model_validate(
                {"series_id": "01999999-0000-7000-8000-000000000000", "format": wrong}
            )
        assert fields(refused.value) == {"format"}
    data = SeriesCreateIn.model_validate(
        {"code": "A", "invoice_type": "F1", "year": 2026, "format": " "}
    )
    assert data.format == ""


def test_the_next_number_starts_at_one_at_least():
    with pytest.raises(ValidationError) as refused:
        SeriesUpdateIn.model_validate(
            {"series_id": "01999999-0000-7000-8000-000000000000", "next_number": 0}
        )
    assert fields(refused.value) == {"next_number"}


def test_a_prefix_and_a_format_are_printable_ascii():
    # VeriFactu's NumSerieFactura: printable ASCII only («Fª» or «Nº» would be refused by the AEAT).
    base = {"code": "A", "invoice_type": "F1", "year": 2026}
    for field, wrong in (("prefix", "Fª"), ("format", "Nº{year}-{seq}"), ("prefix", "F\t1")):
        with pytest.raises(ValidationError) as refused:
            SeriesCreateIn.model_validate({**base, field: wrong})
        assert fields(refused.value) == {field}
    ok = SeriesCreateIn.model_validate(
        {**base, "prefix": "F/A", "format": "{prefix} {year}#{seq:04d}"}
    )
    assert (ok.prefix, ok.format) == ("F/A", "{prefix} {year}#{seq:04d}")
