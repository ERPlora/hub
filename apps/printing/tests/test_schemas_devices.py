"""Schemas of the devices that print: setting one up, changing it and asking who covers a function."""

import uuid

import pytest

from apps.printing.schemas.devices import CoverageIn, DeviceRegisterIn, DeviceUpdateIn

from .test_schemas_fields import refused


def test_a_device_change_says_what_changes():
    some = str(uuid.uuid4())
    errors = refused(DeviceUpdateIn, {"device_id": some})
    assert errors[0]["type"] == "value_error"
    renamed = DeviceUpdateIn.model_validate({"device_id": some, "name": " Bar till "})
    assert (renamed.name, renamed.printers) == ("Bar till", None)
    assert DeviceUpdateIn.model_validate({"device_id": some, "printers": []}).printers == []


def test_a_device_reaches_at_most_twenty_printers():
    printers = [str(uuid.uuid4()) for _ in range(21)]
    refused(DeviceRegisterIn, {"name": "Till", "printers": printers})
    refused(DeviceUpdateIn, {"device_id": str(uuid.uuid4()), "printers": printers})
    assert len(DeviceRegisterIn.model_validate({"name": "Till", "printers": printers[:20]}).printers) == 20


@pytest.mark.parametrize("usage", ["receipt", "kitchen", "bar", "label"])
def test_the_coverage_asks_for_one_of_the_four_functions(usage):
    assert CoverageIn.model_validate({"usage": usage}).usage == usage
    refused(CoverageIn, {"usage": usage.title()})
