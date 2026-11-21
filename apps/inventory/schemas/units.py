"""Schemas of the units of measure."""

from decimal import Decimal

from ninja import Field, Schema

from apps.inventory.schemas.fields import Page, PageIn, UnitCode


class UnitListIn(PageIn):
    search: str | None = Field(
        None, max_length=50, description="Part of the code or the name of the unit."
    )


class UnitOut(Schema):
    code: UnitCode = Field(description="Code.")
    name: str = Field(description="Name, in the request's language.")
    category: str = Field(description="count, mass, volume or time.")
    factor_num: int = Field(
        description="Numerator of the exact factor towards the reference unit of its category."
    )
    factor_den: int = Field(description="Denominator of that factor (1 min = 1/60 h).")
    increment: Decimal = Field(
        description="The step every quantity in this unit is a multiple of."
    )
    is_reference: bool = Field(
        description="Whether it is the reference unit of its category."
    )


UnitPage = Page[UnitOut]
