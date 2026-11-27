"""The kitchen's sheet (KITCHEN-F08): a dish sold by measure goes to paper with its unit, so the printer writes
«0.35 kg Prawns» and never a bare «0.35x»; a dish sold by units goes as before, and the printer writes «2x»."""

from apps.printing.models import PrintJob

from .conftest import HUB_DB, add_line, open_check, run

pytestmark = HUB_DB


def test_a_dish_sold_by_measure_goes_to_paper_with_its_unit_and_one_by_units_without(product, printers):
    order = open_check("Table 4")
    add_line(order.id, product("Prawns", "PRW", 2400, unit="kg"), "0.350")
    add_line(order.id, product("Burger"), "2")

    run("kitchen.ticket.send", {"order_id": str(order.id)})

    (sheet,) = PrintJob.objects.filter(document_type="kitchen_order")
    assert sheet.document["items"] == [
        {"name": "Prawns", "quantity": 0.35, "unit": "kg"},
        {"name": "Burger", "quantity": 2.0},
    ]
