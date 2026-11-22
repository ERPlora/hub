"""The line a check or a counter sale takes: a product of the catalog, a menu with its dishes, an open price or a
service."""

from decimal import Decimal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field
from pydantic import model_validator

from apps.sale.schemas.fields import (
    A_DEPARTMENT,
    A_DISH,
    A_MEMBER,
    A_MENU,
    A_PRODUCT,
    A_SERVICE,
    MAX_OPTIONS,
    SAY_WHICH_DEPARTMENT,
    SAY_WHICH_DISH,
    SAY_WHICH_MENU,
    SAY_WHICH_PRODUCT,
    SAY_WHICH_SERVICE,
    Cents,
    Closed,
    ModifierId,
    Note,
    Quantity,
    Said,
    _text,
)


class LineFields(Closed):
    quantity: Quantity = Field(
        Decimal("1"),
        description="Quantity, in the product's unit (0.532 kg); 1 by default.",
    )
    notes: Note = Field(
        "", description="A note for the kitchen and the ticket, e.g. no salt."
    )
    staff_id: UUID | None = Field(
        None,
        description="Who serves this line (a member of Staff); empty = the check's.",
        json_schema_extra=A_MEMBER,
    )
    is_gift: bool = Field(False, description="True: a comp, charged at 0.")
    gift_reason: _text(200) = Field("", description="Why it is a comp.")


class ProductLineIn(LineFields):
    """A line of Inventory's catalog: its price, unit and tax category come from the catalog."""

    product_id: UUID | None = Field(None, description="The product's id.", json_schema_extra=A_PRODUCT)
    product: Said | None = Field(
        None, title=gettext_noop("Product"), description="The product's SKU or name, when its id is not known."
    )
    option_ids: list[ModifierId] = Field(
        default_factory=list,
        max_length=MAX_OPTIONS,
        title=gettext_noop("Modifiers"),
        description="The options of Modifiers chosen for the product (modifier.group.for_target), in the order "
        "they were chosen; one chosen twice is named twice. Modifiers checks and values them: their price comes "
        "from it and stays frozen on the line.",
    )

    @model_validator(mode="after")
    def _named(self):
        if self.product_id is None and self.product is None:
            raise ValueError(str(SAY_WHICH_PRODUCT))
        return self


class ComboChoiceIn(Closed):
    """A dish picked in a menu of Menus: by the choice's id, or by its product (and course)."""

    option_id: UUID | None = Field(None, description="The choice's id (combo.combo.for_sale).", json_schema_extra=A_DISH)
    product: Said | None = Field(
        None, description="The SKU or name of the product picked, when the choice's id is not known."
    )
    group: Said | None = Field(
        None, description="The course it is picked in, when the product is in several."
    )
    quantity: int = Field(
        1, ge=1, le=MAX_OPTIONS, description="How many times it is picked in one menu (two coffees: 2)."
    )
    option_ids: list[ModifierId] = Field(
        default_factory=list,
        max_length=MAX_OPTIONS,
        title=gettext_noop("Modifiers"),
        description="The options of Modifiers chosen for the dish (modifier.group.for_target of its product), in the "
        "order they were chosen: the same the dish asks sold on its own. Each pick of the dish carries them all. "
        "Modifiers checks and values them, and their price adds to the menu's, frozen on the line.",
    )

    @model_validator(mode="after")
    def _named(self):
        if self.option_id is None and self.product is None:
            raise ValueError(str(SAY_WHICH_DISH))
        return self


class ComboLineFields(LineFields):
    """A menu of Menus with the dishes picked: Menus checks it and prices it, and the line keeps its answer."""

    combo_id: UUID | None = Field(None, description="The menu's id (combo.combo.for_sale).", json_schema_extra=A_MENU)
    combo: Said | None = Field(None, description="The menu's name, when its id is not known.")
    choices: list[ComboChoiceIn] = Field(
        default_factory=list,
        max_length=MAX_OPTIONS,
        title=gettext_noop("Dishes"),
        description="The dishes picked, course by course. Menus checks each course (its minimum, maximum and "
        "repeats) and prices the menu: its closed price plus the supplements, frozen on the line.",
    )

    @model_validator(mode="after")
    def _named(self):
        if self.combo_id is None and self.combo is None:
            raise ValueError(str(SAY_WHICH_MENU))
        return self


class ComboLineIn(ComboLineFields):
    pass


class OpenLineFields(LineFields):
    """A line at an open price: typed amount, charged at a department's (or a tax category's) VAT."""

    unit_price: Cents = Field(description="The amount typed, in cents, per unit.")
    department_id: UUID | None = Field(
        None, title=gettext_noop("Section"), description="The department it is charged at.", json_schema_extra=A_DEPARTMENT
    )
    department: _text(60, 1) | None = Field(
        None, title=gettext_noop("Section"), description="The department's name, when its id is not known."
    )
    tax_category_key: _text(80, 1) | None = Field(
        None,
        description="Without departments: the tax category (key, name or alias) it is charged at.",
    )
    name: _text(200) = Field(
        "", description="The line's name; the department's by default."
    )

    @model_validator(mode="after")
    def _charged_somewhere(self):
        if (
            self.department_id is None
            and self.department is None
            and self.tax_category_key is None
        ):
            raise ValueError(str(SAY_WHICH_DEPARTMENT))
        return self


class OpenLineIn(OpenLineFields):
    pass


class ServiceLineFields(LineFields):
    """A line of a service of the Services app: its name, price and tax category come from it."""

    service_id: UUID | None = Field(
        None, title=gettext_noop("Service"), description="The service's id (Services).", json_schema_extra=A_SERVICE
    )
    service: Said | None = Field(
        None, description="The service's name, when its id is not known."
    )
    unit_price: Cents | None = Field(
        None,
        description="Only for a service without a fixed price (from, hourly, variable, free): the amount charged "
        "per unit, in cents, within its minimum and maximum.",
    )
    booked_price: Cents | None = Field(
        None,
        title=gettext_noop("Booked price"),
        description="The price the appointment of the check booked for this service, in cents, frozen on the "
        "line whatever the catalog says today. Checked against the appointment (its service at that price; "
        "lower only with the open-price right); without an appointment it is an open price.",
    )

    @model_validator(mode="after")
    def _named(self):
        if self.service_id is None and self.service is None:
            raise ValueError(str(SAY_WHICH_SERVICE))
        return self


class ServiceLineIn(ServiceLineFields):
    pass
