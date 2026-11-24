"""Printers (PRINTING-F03, F04): their connection, their name and what each one prints; a printer that leaves
takes no queued job with it."""

import pytest
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied

from apps.printing.models import Printer, PrintJob, Settings
from apps.printing.tests.conftest import HUB_DB, ctx_for, enqueue, printer, run
from apps.printing.tests.test_services import events

pytestmark = HUB_DB


# ── PRINTING-F03 Add a printer by its address ───────────────────────────────────────────────────


def test_a_network_printer_takes_port_9100_80_mm_and_is_active():
    out = printer("Till")
    assert (out.kind, out.address, out.port, out.paper_width, out.usage, out.is_active) == (
        "network",
        "192.168.1.50",
        9100,
        80,
        "receipt",
        True,
    )
    assert out.target == "network:192.168.1.50:9100"
    assert out.state == "ready"
    assert Printer.objects.get(pk=out.id).created_by == "tester"
    assert events("printing.printer.created") == [{"id": str(out.id)}]


@pytest.mark.parametrize(
    ("values", "address", "port", "target"),
    [
        ({"kind": "bluetooth", "address": "aa-bb-cc-dd-ee-ff"}, "AA:BB:CC:DD:EE:FF", None, "bluetooth:AA:BB:CC:DD:EE:FF"),
        ({"kind": "usb", "address": "EPSON_TM-T20.II"}, "EPSON_TM-T20.II", None, "usb:EPSON_TM-T20.II"),
        ({"kind": "system", "address": ""}, "", None, "system"),
        ({"kind": "network", "address": "printer.local", "port": 9101}, "printer.local", 9101, "network:printer.local:9101"),
        ({"kind": "network", "address": "fe80::1"}, "fe80::1", 9100, "network:fe80::1:9100"),
    ],
)
def test_each_connection_keeps_the_address_the_app_understands(values, address, port, target):
    out = printer("P", **values)
    assert (out.address, out.port, out.target) == (address, port, target)


@pytest.mark.parametrize(
    ("values", "field", "message"),
    [
        ({"address": ""}, "address", "Type a valid IP or network name (for example 192.168.1.100)."),
        ({"address": "192.168.1.50/24"}, "address", "Type a valid IP or network name (for example 192.168.1.100)."),
        ({"port": 0}, "port", "The port goes from 1 to 65535."),
        ({"port": 70000}, "port", "The port goes from 1 to 65535."),
        ({"kind": "bluetooth", "address": "AA:BB:CC"}, "address", "Type the MAC as AA:BB:CC:DD:EE:FF."),
        ({"kind": "bluetooth", "address": "AA:BB:CC:DD:EE:FF", "port": 1}, "port", "Only a network printer has a port."),
        (
            {"kind": "usb", "address": "my printer"},
            "address",
            "Type the print queue's name as the system gives it (no spaces, slashes or #).",
        ),
        (
            {"kind": "system", "address": "10.0.0.1"},
            "address",
            "The system printer is the computer's own: it has no address.",
        ),
        (
            {"kind": "system", "address": "", "usage": "kitchen"},
            "usage",
            "The system printer prints A4 pages: give it the Receipt role.",
        ),
    ],
)
def test_an_address_that_no_printer_can_have_is_refused_at_its_field(values, field, message):
    with pytest.raises(InvalidPayload) as refused:
        printer("P", **values)
    assert refused.value.fields == {field: message}
    assert not Printer.objects.exists()


def test_two_printers_never_share_a_name_whatever_its_case():
    printer("Kitchen")
    with pytest.raises(Conflict) as refused:
        printer("kitchen", address="192.168.1.51")
    assert refused.value.code == "printing.printer_exists"
    assert refused.value.fields == {"name": "There is already a printer with that name."}


def test_only_who_manages_the_settings_adds_a_printer():
    with pytest.raises(PermissionDenied):
        run("printing.printer.create", {"name": "Till", "kind": "system", "usage": "receipt"}, ctx_for("hub_employee"))
    assert run(
        "printing.printer.create", {"name": "Till", "kind": "system", "usage": "receipt"}, ctx_for("hub_manager")
    ).name == "Till"


# ── PRINTING-F04 What each printer prints ───────────────────────────────────────────────────────


def test_a_printer_is_changed_by_its_name():
    till = printer("Till")
    out = run("printing.printer.update", {"printer": "till", "name": "Front till", "paper_width": 58})
    assert (out.id, out.name, out.paper_width) == (till.id, "Front till", 58)
    assert events("printing.printer.updated") == [{"id": str(till.id), "fields": ["name", "paper_width"]}]


def test_nothing_changed_is_no_event():
    printer("Till")
    run("printing.printer.update", {"printer": "Till", "name": "Till"})
    assert events("printing.printer.updated") == []


def test_a_printer_is_deactivated_and_activated_never_deleted():
    till = printer("Till")
    assert run("printing.printer.update", {"printer_id": str(till.id), "is_active": False}).state == "inactive"
    assert run("printing.printer.update", {"printer_id": str(till.id), "is_active": True}).state == "ready"


def test_changing_the_connection_asks_for_an_address_it_can_have():
    printer("Till", kind="bluetooth", address="AA:BB:CC:DD:EE:FF")
    with pytest.raises(InvalidPayload) as refused:
        run("printing.printer.update", {"printer": "Till", "kind": "network"})
    assert set(refused.value.fields) == {"address"}
    out = run("printing.printer.update", {"printer": "Till", "kind": "network", "address": "10.0.0.7"})
    assert out.target == "network:10.0.0.7:9100"
    out = run("printing.printer.update", {"printer": "Till", "kind": "system", "address": ""})
    assert (out.address, out.port, out.target) == ("", None, "system")


def test_an_unknown_printer_is_not_found():
    with pytest.raises(NotFound) as refused:
        run("printing.printer.update", {"printer": "Nowhere", "is_active": False})
    assert refused.value.message == "There is no printer with that name."


def test_a_printer_that_changes_function_stops_being_the_one_of_its_old_function():
    kitchen = printer("Kitchen", usage="kitchen")
    run("printing.settings.update", {"kitchen_printer": "Kitchen"})
    run("printing.printer.update", {"printer": "Kitchen", "usage": "bar"})
    assert Settings.objects.get().kitchen_printer_id is None
    assert Printer.objects.get(pk=kitchen.id).usage == "bar"


# ── PRINTING-F04 A printer that leaves takes no queued job with it ───────────────────────────────


def test_deactivating_a_printer_moves_its_queued_jobs_to_the_printer_of_its_function_now():
    printer("Till")
    printer("Till 2", address="10.0.0.2")
    queued = enqueue(printer="Till").job
    before = len(events("printing.job.queued"))
    run("printing.printer.update", {"printer": "Till", "is_active": False})
    moved = PrintJob.objects.get(pk=queued.id)
    assert moved.printer.name == "Till 2"
    assert len(events("printing.job.queued")) == before + 1


def test_a_printer_that_changes_role_or_connection_lets_go_of_what_it_no_longer_prints():
    printer("Till")
    queued = enqueue(printer="Till").job
    run("printing.printer.update", {"printer": "Till", "usage": "kitchen"})
    assert PrintJob.objects.get(pk=queued.id).printer_id is None
    printer("Till 2", address="10.0.0.2")
    other = enqueue(printer="Till 2").job
    run("printing.printer.update", {"printer": "Till 2", "kind": "system", "address": ""})
    assert PrintJob.objects.get(pk=other.id).printer_id is None


def test_a_rename_keeps_the_queue_where_it_is():
    till = printer("Till")
    queued = enqueue(printer="Till").job
    run("printing.printer.update", {"printer": "Till", "name": "Front till"})
    assert PrintJob.objects.get(pk=queued.id).printer_id == till.id
