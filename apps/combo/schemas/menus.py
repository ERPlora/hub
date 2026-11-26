"""Menus: their list, what one is made or changed with, and how one reads back."""

import datetime as dt
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.combo.schemas.courses import GroupOut
from apps.combo.schemas.fields import (
    D_PRICE,
    D_SUPPLY,
    D_TAX,
    VAT_CATEGORY,
    Cents,
    Direction,
    In,
    KitchenName,
    Name,
    Order,
    Page,
    PageIn,
    Search,
    SupplyKind,
    TaxKey,
)
from apps.combo.schemas.references import ComboRefIn
from apps.tax.schemas.references import A_TAX_CATEGORY
from base.recovery import ImageInCopyIn


class ComboListIn(PageIn):
    search: Search | None = Field(
        None, description="Text to look for in the name or the kitchen name."
    )
    name: Search | None = Field(
        None, description="Keep the menus whose name contains this."
    )
    supply_kind: SupplyKind | None = Field(
        None, description="Keep the menus sold this way: service (eaten in) or goods."
    )
    is_active: bool | None = Field(
        None,
        description="true: only the menus on sale; false: only the withdrawn ones.",
    )
    sort: Literal["sort_order", "name", "price", "supply_kind", "is_active", "id"] = (
        Field(
            "sort_order",
            description="Column to sort by; the name and the id break ties.",
        )
    )
    dir: Direction = Field("asc", description="asc or desc.")


class ComboIn(In):
    name: Name = Field(description="The menu's name on the till («Menu of the day»).")
    kitchen_name: KitchenName = Field(
        "", description="Name on the kitchen ticket; empty uses the name."
    )
    price: Cents = Field(description=D_PRICE)
    supply_kind: SupplyKind = Field("service", description=D_SUPPLY)
    tax_category_key: TaxKey | None = Field(
        None, title=VAT_CATEGORY, description=D_TAX, json_schema_extra=A_TAX_CATEGORY
    )
    sort_order: Order = Field(
        0, description="Position on the list of menus and on the till."
    )
    is_active: bool = Field(
        True, description="On sale: false keeps it on the list but off the till."
    )


class ComboRecoverIn(ComboIn, ImageInCopyIn):
    """A menu of a separate copy the business no longer has: what ``combo.combo.create`` takes and the image it showed
    there."""

    stands_for: UUID = Field(description="The menu of the copy it is made again for, by its id there.")


class ComboPatchIn(ComboRefIn):
    """Only the fields sent change."""

    name: Name | None = Field(None, description="New name.")
    kitchen_name: KitchenName | None = Field(
        None, description="New kitchen name; empty uses the name."
    )
    price: Cents | None = Field(None, description="New closed price, in cents.")
    supply_kind: SupplyKind | None = Field(None, description=D_SUPPLY)
    tax_category_key: TaxKey | None = Field(
        None, title=VAT_CATEGORY, json_schema_extra=A_TAX_CATEGORY,
        description=D_TAX + " Empty clears it (only to take away).",
    )
    sort_order: Order | None = Field(None, description="New position on the list.")
    is_active: bool | None = Field(
        None, description="Put on sale (true) or withdraw from the till (false)."
    )


class ComboOut(Schema):
    id: UUID
    name: str
    kitchen_name: str
    price: int = Field(json_schema_extra={"money": True})
    supply_kind: SupplyKind
    tax_category_key: str | None
    tax_category_name: str | None
    sort_order: int
    is_active: bool
    group_count: int
    image: str = Field(
        description="Its image: catalog:<folder>/<name> of the shared library, file:<name> of a photo of its own, "
        "or empty."
    )
    image_url: str = Field(description="Where the Hub serves its image; empty: it has none (show its initials).")
    created_at: dt.datetime
    updated_at: dt.datetime


ComboPage = Page[ComboOut]


class BlockerOut(Schema):
    code: str = Field(
        description="combo.not_on_sale, combo.tax_category_inactive, combo.no_choices, combo.group_short or "
        "combo.no_catalog_price."
    )
    message: str
    group_id: UUID | None


class ComboDetailOut(ComboOut):
    groups: list[GroupOut]
    sellable: bool = Field(description="Whether the till offers it now.")
    blockers: list[BlockerOut] = Field(description="Why the till does not offer it.")
