"""The assistant's card for a voucher granted (``service.grant.create``, SERVICE-F14): the voucher, whose it is and the
sale that charged it (then its line), first. A normal card's line shows only its first three data, in the form's order:
«Crear en Servicios: Bono 10 lavados · Lucía Fernández QA · 85,00 €» had no sale (hub#2347)."""

import dataclasses
import json

from live.operations import get

from apps.sale.models import SaleLine
from base import assistant
from base.tests.test_assistant_card_values_references import AN_ID

from .conftest import HUB_DB, ctx_for
from .test_grant_sales import haircut, lucia, sold_once

pytestmark = HUB_DB
__all__ = ["haircut", "lucia"]


def test_a_voucher_says_which_whose_and_the_sale_that_charged_it(lucia):
    _seller, sale = sold_once()
    line = SaleLine.objects.filter(sale_id=sale.id).get()
    arguments = {
        "package": "Bono 10 lavados",
        "customer_id": str(lucia.id),
        "amount": 8500,
        "net_amount": 7025,
        "tax_amount": 1475,
        "sale_id": str(sale.id),
        "sale_line_id": str(line.id),
    }
    spanish = dataclasses.replace(ctx_for(), language="es")
    fields = assistant.cards.card(get("service.grant.create"), arguments, "es", spanish)["fields"]
    shown = [field for field in fields if field["kind"] != "empty"][:3]
    assert [field["name"] for field in shown] == ["package", "customer_id", "sale_id"]
    assert shown[1]["value"] == "Lucía Pérez"
    assert fields[3]["name"] == "sale_line_id"
    assert not AN_ID.search(json.dumps([field["value"] for field in fields[:4]]))
