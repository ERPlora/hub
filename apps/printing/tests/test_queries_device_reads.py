"""A device set up to print (PRINTING-F18), found by its registration id and read as the screens read it."""

import pytest
from django.utils import timezone
from live.errors import NotFound, PermissionDenied

from apps.printing.queries.device_reads import find_device
from apps.printing.tests.conftest import HUB_DB, ctx_for, printer, run

pytestmark = HUB_DB


def test_a_device_by_its_registration_id_with_the_printers_it_reaches():
    """«printing.device.detail»: one device set up to print, as the devices screen shows it — what the assistant's card
    names a device by. Never its own id; a retired one is no device there."""
    from apps.printing.models import PrintDevice

    till = printer("Till")
    counter = PrintDevice.objects.create(name="Counter", key=PrintDevice.key_of("counter"), registered_by="Ana")
    counter.printers.add(till.id)
    out = run("printing.device.detail", {"device_id": str(counter.id)}, ctx_for("hub_employee"))
    assert (out.id, out.name, [p.name for p in out.printers], out.registered_by, out.this_device) == (
        counter.id,
        "Counter",
        ["Till"],
        "Ana",
        False,
    )
    assert "key" not in out.model_dump()
    assert find_device(counter.id) == counter
    with pytest.raises(PermissionDenied):
        run("printing.device.detail", {"device_id": str(counter.id)}, ctx_for("nobody"))
    PrintDevice.objects.filter(pk=counter.id).update(retired_at=timezone.now())
    with pytest.raises(NotFound) as retired:
        run("printing.device.detail", {"device_id": str(counter.id)})
    assert retired.value.code == "printing.device_not_found"
