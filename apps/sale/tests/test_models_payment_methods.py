"""The payment methods: the factory ones' names in the reader's language, and which of them give change."""

from django.utils import translation

from apps.sale.models.payment_methods import PaymentMethod
from apps.sale.tests.conftest import HUB_DB

pytestmark = HUB_DB


def test_factory_payment_methods_read_in_the_active_language_until_renamed():
    cash = PaymentMethod.objects.get(is_system=True, type=PaymentMethod.Type.CASH)
    with translation.override("es"):
        assert cash.display_name == "Efectivo"
        cash.name = "Caja chica"
        assert cash.display_name == "Caja chica"
    own = PaymentMethod(name="Bizum", type=PaymentMethod.Type.OTHER)
    assert own.display_name == "Bizum"


def test_cash_takes_change_and_the_other_types_do_not():
    assert PaymentMethod(type=PaymentMethod.Type.CASH).requires_change is True
    for kind in (
        PaymentMethod.Type.CARD,
        PaymentMethod.Type.TRANSFER,
        PaymentMethod.Type.OTHER,
    ):
        assert PaymentMethod(type=kind).requires_change is False
