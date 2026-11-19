from django.utils.translation import gettext_noop
from ninja import Field

from apps.sale.schemas import OrderLineRefIn
from base.allergens import CODES, Allergens

CUSTOMERS_ALLERGY = gettext_noop("Customer's allergy")


class OrderSetLineAllergyIn(OrderLineRefIn):
    allergy: Allergens = Field(
        max_length=len(CODES),
        title=CUSTOMERS_ALLERGY,
        description="All the allergens the person it is for must not eat, by their codes, of the fourteen that must "
        "be declared: they replace the ones marked; an empty list takes the allergy off.",
    )
