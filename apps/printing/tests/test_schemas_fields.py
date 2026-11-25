"""Schemas of the printing app: what an input refuses before any operation runs, and that every field says
what it is (they are the assistant's tools too). Here, what every schema shares: the closed input, the page and
the four functions; ``refused``, which the tests of every schema module read."""

import pydantic
import pytest
from ninja import Schema

from apps.printing.schemas.claims import HostJobOut, JobAckOut, JobClaimIn, JobClaimOut, JobCompleteIn, JobFailIn
from apps.printing.schemas.fields import EmptyIn
from apps.printing.schemas.jobs import (
    JobCancelIn,
    JobCreateIn,
    JobCreateOut,
    JobListIn,
    JobOut,
    JobRefIn,
    JobSummaryOut,
    UsageSummary,
)
from apps.printing.schemas.printers import (
    PrinterIn,
    PrinterListIn,
    PrinterOut,
    PrinterRefIn,
    PrinterStatusOut,
    PrinterUpdateIn,
)
from apps.printing.schemas.settings import SettingsOut, SettingsPatchIn

INPUTS = [
    EmptyIn,
    SettingsPatchIn,
    PrinterIn,
    PrinterUpdateIn,
    PrinterRefIn,
    PrinterListIn,
    JobCreateIn,
    JobListIn,
    JobRefIn,
    JobCancelIn,
    JobClaimIn,
    JobCompleteIn,
    JobFailIn,
]
OUTPUTS = [
    SettingsOut,
    PrinterOut,
    PrinterStatusOut,
    JobOut,
    JobCreateOut,
    HostJobOut,
    JobClaimOut,
    JobAckOut,
    UsageSummary,
    JobSummaryOut,
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


def test_a_role_is_one_of_the_four_never_a_free_word():
    # «Kitchen», «kitchn» or «cocina» would open a queue that no printer ever drains.
    for usage in ("Kitchen", "kitchn", "cocina", " kitchen", ""):
        refused(PrinterIn, {"name": "Till", "kind": "network", "usage": usage})
        refused(PrinterUpdateIn, {"printer": "Till", "usage": usage})
        refused(JobCreateIn, {"document_type": "receipt", "document": {}, "usage": usage})
        refused(SettingsPatchIn, {usage: "Till"})
    assert JobCreateIn.model_validate({"document_type": "receipt", "document": {}, "usage": "kitchen"}).usage == "kitchen"


@pytest.mark.parametrize("schema", [PrinterListIn, JobListIn])
def test_a_list_pages_up_to_100(schema):
    refused(schema, {"limit": 101})
    assert schema.model_validate({}).limit == 50
