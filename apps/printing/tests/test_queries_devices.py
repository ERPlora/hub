"""The devices that print (PRINTING-F18), as the devices screen lists them."""

import pytest
from django.utils import timezone
from live.errors import PermissionDenied

from apps.printing.queries.devices import list_devices
from apps.printing.schemas.devices import DeviceListIn
from apps.printing.tests.conftest import HUB_DB, ctx_for, printer, run

pytestmark = HUB_DB


def test_the_devices_by_name_with_the_printers_each_one_reaches():
    from apps.printing.models import PrintDevice

    till = printer("Till")
    kitchen = printer("Kitchen", usage="kitchen", address="10.0.0.2", is_active=False)
    counter = PrintDevice.objects.create(name="Counter", key=PrintDevice.key_of("counter"), registered_by="Ana")
    counter.printers.add(till.id, kitchen.id)
    PrintDevice.objects.create(name="bar tablet", key=PrintDevice.key_of("bar"))
    gone = PrintDevice.objects.create(name="Old till", key=PrintDevice.key_of("old"), retired_at=timezone.now())
    gone.printers.add(till.id)

    out = run("printing.device.list", ctx=ctx_for("hub_employee"))
    assert (out.total, [row.name for row in out.rows]) == (2, ["bar tablet", "Counter"])
    row = out.rows[1]
    assert [(p.name, p.usage, p.is_active) for p in row.printers] == [("Kitchen", "kitchen", False), ("Till", "receipt", True)]
    assert (row.registered_by, row.last_seen_at, row.this_device) == ("Ana", None, False)
    assert list_devices(ctx_for(), DeviceListIn(limit=1, offset=1)).rows[0].name == "Counter"
    with pytest.raises(PermissionDenied):
        run("printing.device.list", ctx=ctx_for("nobody"))
