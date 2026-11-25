"""Who and what an appointment is for: the customer is said when someone acts for her."""

from apps.appointment.schemas.changes import CancelIn
from apps.appointment.schemas.references import ForCustomer

from .schema_checks import ID, errors


def test_acting_for_the_customer_names_her():
    assert "customer" in errors(ForCustomer, on_behalf_of_customer=True)
    assert not errors(CancelIn, id=ID, reason="Ill")
    assert "customer" in errors(CancelIn, id=ID, on_behalf_of_customer=True)
    assert not errors(
        CancelIn, id=ID, on_behalf_of_customer=True, customer="+34600111222"
    )
    assert "reason" in errors(CancelIn, id=ID, reason="x" * 501)
