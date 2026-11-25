"""The printing settings as they are read: the factory ones until the business saves its own."""

import pytest
from live.errors import PermissionDenied

from apps.printing.queries.settings import get_settings
from apps.printing.schemas.fields import EmptyIn
from apps.printing.tests.conftest import HUB_DB, ctx_for, printer, run

pytestmark = HUB_DB


def test_a_business_that_never_saved_has_the_factory_settings():
    # The read answers the defaults and never writes a row.
    out = run("printing.settings.get")
    assert (out.print_receipt_on_sale, out.open_drawer_on_sale, out.receipt_copies, out.updated_at) == (True, False, 1, None)
    assert (out.receipt_printer_id, out.kitchen_printer_id, out.bar_printer_id, out.label_printer_id) == (None,) * 4
    from apps.printing.models import Settings

    assert not Settings.objects.exists()


def test_the_settings_read_what_was_saved():
    kitchen = printer("Kitchen", usage="kitchen")
    run("printing.settings.update", {"print_receipt_on_sale": False, "kitchen_printer": "Kitchen"})
    out = get_settings(ctx_for("hub_employee"), EmptyIn())
    assert (out.print_receipt_on_sale, out.kitchen_printer_id) == (False, kitchen.id)


def test_a_role_without_printing_reads_nothing():
    with pytest.raises(PermissionDenied):
        run("printing.settings.get", ctx=ctx_for("nobody"))
