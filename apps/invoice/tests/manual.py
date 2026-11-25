"""An invoice issued by hand, for the tests that only need one."""

from apps.invoice.tests.conftest import run

RECIPIENT = {
    "customer_name": "Talleres Pérez SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Luna 3",
}
LINE = {"description": "Course", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}


def manual(ctx=None, **more):
    """An invoice of 12.10 € in FACT, unless ``more`` says another thing."""
    return run("invoice.invoice.create", {"lines": [LINE], **RECIPIENT, **more}, ctx)
