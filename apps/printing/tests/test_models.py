"""Models of the printing app: what the database itself refuses, and the helpers the models carry."""

import hashlib

import pytest
from django.db import IntegrityError, transaction

from apps.printing.models import PrintDevice, Printer, PrintJob, Settings

pytestmark = pytest.mark.django_db


def refused(make):
    with pytest.raises(IntegrityError), transaction.atomic():
        make()


def a_printer(**more) -> Printer:
    values = {"name": "Till", "kind": "network", "address": "192.168.1.50", "port": 9100, "usage": "receipt"}
    return Printer.objects.create(**(values | more))


def a_job(**more) -> PrintJob:
    values = {
        "job_key": "sale-1-receipt",
        "kind": "document",
        "document_type": "receipt",
        "document": {"receipt_id": "T-1"},
        "usage": "receipt",
    }
    return PrintJob.objects.create(**(values | more))


@pytest.mark.parametrize(
    ("values", "target"),
    [
        ({"kind": "network", "address": "192.168.1.50", "port": 9100}, "network:192.168.1.50:9100"),
        ({"kind": "network", "address": "printer.local", "port": 9101}, "network:printer.local:9101"),
        ({"kind": "bluetooth", "address": "AA:BB:CC:DD:EE:FF", "port": None}, "bluetooth:AA:BB:CC:DD:EE:FF"),
        ({"kind": "usb", "address": "EPSON_TM_T20", "port": None}, "usb:EPSON_TM_T20"),
        ({"kind": "system", "address": "", "port": None}, "system"),
    ],
)
def test_the_target_is_the_printer_id_the_apps_commands_take(values, target):
    # discovery::parse_print_target of ERPlora/app: `network:<ip>:<port>`, `bluetooth:<mac>`, `usb:<queue>`.
    assert a_printer(**values).target == target


def test_the_system_printer_prints_a4_and_the_thermal_ones_receipt_paper():
    assert a_printer(kind="system", address="", port=None).format == "a4"
    assert a_printer(name="Kitchen").format == "receipt"


def test_a_printer_name_is_unique_whatever_its_case_and_never_empty():
    a_printer()
    refused(lambda: a_printer(name="till"))
    refused(lambda: a_printer(name=""))


def test_the_paper_is_58_or_80_mm():
    refused(lambda: a_printer(paper_width=76))
    assert a_printer(paper_width=58).paper_width == 58


def test_a_network_printer_has_an_address_and_a_port_in_range():
    refused(lambda: a_printer(port=None))
    refused(lambda: a_printer(port=0))
    refused(lambda: a_printer(port=65536))
    refused(lambda: a_printer(address=""))


def test_usb_and_bluetooth_printers_have_an_address_and_no_port():
    refused(lambda: a_printer(kind="usb", address="", port=None))
    refused(lambda: a_printer(kind="bluetooth", address="AA:BB:CC:DD:EE:FF", port=9100))


def test_the_system_printer_has_no_address_and_prints_receipts_and_documents():
    refused(lambda: a_printer(kind="system", address="x", port=None))
    refused(lambda: a_printer(kind="system", address="", port=None, usage="kitchen"))


def test_the_settings_are_one_row_with_one_to_three_copies():
    Settings.objects.create()
    refused(lambda: Settings.objects.create())
    refused(lambda: Settings.objects.update(receipt_copies=4))


def test_the_factory_settings():
    settings = Settings()
    assert settings.print_receipt_on_sale is True
    assert settings.open_drawer_on_sale is False
    assert settings.receipt_copies == 1
    assert settings.receipt_printer is None


def test_a_job_key_is_unique():
    a_job()
    refused(lambda: a_job())


def test_a_job_has_one_to_five_copies():
    refused(lambda: a_job(copies=0))
    refused(lambda: a_job(copies=6))


def test_a_document_job_names_a_document_the_renderer_knows():
    refused(lambda: a_job(document_type=""))
    refused(lambda: a_job(document_type="kitchn"))
    assert a_job(job_key="t", kind="test_page", document_type="").kind == "test_page"


def test_an_a4_job_carries_its_page_until_it_is_printed_or_cancelled():
    refused(lambda: a_job(format="a4", html=""))
    assert a_job(format="a4", html="<p>Invoice</p>").format == "a4"
    # RGPD: a printed or cancelled job lets its page go.
    assert a_job(job_key="done", format="a4", html="", status="done").html == ""
    assert a_job(job_key="cancelled", format="a4", html="", status="cancelled").html == ""


def test_the_factory_job_is_pending_with_one_copy():
    job = a_job()
    assert (job.status, job.attempts, job.copies, job.open_drawer, job.format) == ("pending", 0, 1, False, "receipt")


def test_a_printer_with_jobs_is_never_deleted():
    till = a_printer()
    a_job(printer=till)
    with pytest.raises(Exception), transaction.atomic():
        till.delete()


def a_device(**more) -> PrintDevice:
    return PrintDevice.objects.create(**({"name": "Till", "key": PrintDevice.key_of("till-1")} | more))


def test_a_device_is_known_by_the_digest_of_its_own_id_never_by_the_id():
    # hub#2551: the id a device sends is its credential; the database keeps its SHA-256, which proves nothing.
    assert PrintDevice.key_of("till-1") == hashlib.sha256(b"till-1").hexdigest()
    assert PrintDevice.key_of("  till-1 ") == PrintDevice.key_of("till-1")
    a_device()
    refused(lambda: a_device(name="Other"))
    refused(lambda: a_device(key=PrintDevice.key_of("till-2"), name=""))


def test_a_device_reaches_printers_and_one_with_jobs_is_never_deleted():
    till = a_device()
    till.printers.add(a_printer())
    assert [p.name for p in till.printers.all()] == ["Till"]
    a_job(print_device=till, device="Till")
    with pytest.raises(Exception), transaction.atomic():
        till.delete()


def test_names():
    assert str(a_device(name="Counter till")) == "Counter till"
    assert str(a_printer()) == "Till"
    assert str(Settings()) == "printing settings"
    assert str(a_job(reference="T-000123")) == "receipt T-000123"


def test_a_job_names_each_document_the_renderer_paints_and_no_other():
    """The labels of a job's document (the queue's and the assistant's card's words for it) are those of the eight the
    renderer paints, in its order: a new one comes with its label or nowhere."""
    from typing import get_args

    from apps.printing.documents import DOCUMENT_TYPES
    from apps.printing.schemas import DocumentType

    assert PrintJob.DocumentType.values == list(DOCUMENT_TYPES) == list(get_args(DocumentType))
    assert PrintJob._meta.get_field("document_type").choices == PrintJob.DocumentType.choices
