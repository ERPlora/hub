"""A service's price on the public booking page, with how it is priced so «From €65.00» never reads as a fixed €65.00.

A business that hides its prices hides both: not even «Free» is shown.
"""

from ninja import Field, Schema

from apps.service.models.catalog import Service
from apps.service.schemas.catalog import PricingType


class ServicePriceOut(Schema):
    price: int | None = Field(
        description="In cents; empty when the business does not show prices.", json_schema_extra={"money": True}
    )
    pricing_type: PricingType | None = Field(
        description="How it is priced: fixed, hourly, from (a minimum), variable or free; empty when the business "
        "does not show prices."
    )


def shown_price(service: Service, show_prices: bool) -> dict:
    if not show_prices:
        return {"price": None, "pricing_type": None}
    return {"price": service.price, "pricing_type": service.pricing_type}
