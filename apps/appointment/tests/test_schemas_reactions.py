"""The payloads of other apps' events, read as those apps write them."""

import uuid

from apps.appointment.schemas.reactions import SaleFromAppointmentIn, SaleVoidedIn


def test_the_sales_payloads_are_read_as_sales_writes_them():
    sale, appointment = str(uuid.uuid7()), str(uuid.uuid7())
    payload = {
        "sale_id": sale,
        "appointment_id": appointment,
        "staff_id": None,
        "total": 2000,
    }
    assert SaleFromAppointmentIn.model_validate(payload).appointment_id == uuid.UUID(
        appointment
    )
    voided = {
        "sale_id": sale,
        "sale_number": "T-1",
        "reason": "x",
        "voided_by": "y",
        "total": 1,
        "lines": [],
    }
    assert SaleVoidedIn.model_validate(voided).sale_id == uuid.UUID(sale)
