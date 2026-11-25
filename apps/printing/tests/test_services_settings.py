"""The settings (PRINTING-F06): only what is sent is saved, and the printer of a function is one of its active ones."""

import pytest
from live.errors import InvalidPayload, PermissionDenied

from apps.printing.models import Settings
from apps.printing.tests.conftest import HUB_DB, ctx_for, printer, run
from apps.printing.tests.test_services import events

pytestmark = HUB_DB


# ── PRINTING-F06 Settings ───────────────────────────────────────────────────────────────────────


def test_the_settings_save_only_what_is_sent():
    out = run("printing.settings.update", {"open_drawer_on_sale": True, "receipt_copies": 2})
    assert (out.print_receipt_on_sale, out.open_drawer_on_sale, out.receipt_copies) == (True, True, 2)
    assert out.updated_at is not None
    assert events("printing.settings.updated") == [{"fields": ["open_drawer_on_sale", "receipt_copies"]}]
    assert Settings.objects.get().updated_by == "tester"


def test_the_printer_of_a_function_is_one_of_its_active_printers():
    kitchen = printer("Kitchen", usage="kitchen")
    printer("Till")
    printer("Old kitchen", usage="kitchen", address="10.0.0.2", is_active=False)
    out = run("printing.settings.update", {"kitchen_printer": "kitchen"})
    assert out.kitchen_printer_id == kitchen.id
    with pytest.raises(InvalidPayload) as refused:
        run("printing.settings.update", {"kitchen_printer": "Till"})
    assert refused.value.fields == {"kitchen_printer": "That printer does not have this role."}
    with pytest.raises(InvalidPayload) as refused:
        run("printing.settings.update", {"kitchen_printer": "Old kitchen"})
    assert refused.value.fields == {"kitchen_printer": "That printer is inactive."}
    with pytest.raises(InvalidPayload) as refused:
        run("printing.settings.update", {"label_printer": "Nowhere"})
    assert refused.value.fields == {"label_printer": "There is no printer with that name."}
    assert run("printing.settings.update", {"kitchen_printer": None}).kitchen_printer_id is None


def test_the_employee_reads_the_settings_and_does_not_change_them():
    with pytest.raises(PermissionDenied):
        run("printing.settings.update", {"receipt_copies": 2}, ctx_for("hub_employee"))
