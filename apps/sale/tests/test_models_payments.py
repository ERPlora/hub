"""A sale's tenders: the change a tender gives back, and what another app adds on top of the sale."""

from apps.sale.models.payment_methods import PaymentMethod
from apps.sale.models.payments import SalePayment
from apps.sale.tests.conftest import HUB_DB, a_sale, refused

pytestmark = HUB_DB


def paid(sale, **more) -> SalePayment:
    cash = PaymentMethod.objects.get(is_system=True, type=PaymentMethod.Type.CASH)
    values = {
        "sale": sale,
        "position": 1,
        "method": cash,
        "method_name": "Cash",
        "method_type": cash.type,
        "amount": 100,
        "tendered": 150,
        "change": 50,
    }
    return SalePayment.objects.create(**(values | more))


def test_the_change_is_what_was_handed_over_beyond_the_amount_and_what_another_app_adds():
    sale = a_sale()
    payment = paid(sale)
    assert (payment.extra, payment.extra_label, str(payment)) == (0, "", "Cash 100")
    paid(sale, position=2, tendered=170, extra=20, extra_label="Tip")
    refused(lambda: paid(sale, position=3, change=40))
    refused(lambda: paid(sale, position=3, amount=0, tendered=50))
