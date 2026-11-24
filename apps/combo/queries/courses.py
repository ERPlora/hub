"""A course of a menu and one of its choices, each read alone: what names it on the assistant's card."""

from django.db.models import prefetch_related_objects
from live.context import OperationContext
from live.operations import INTERNAL, operation

from apps.combo.schemas.choices import OptionOut
from apps.combo.schemas.courses import GroupOut
from apps.combo.schemas.references import GroupRefIn, OptionRefIn

from .offers import takeaway_targets
from .reads import find_group, find_option
from .rows import _options, group_row, option_row


@operation(
    "combo.option.get",
    kind="query",
    permission="combo.view",
    input=OptionRefIn,
    output=OptionOut,
    ai=INTERNAL,
)
def get_option(ctx: OperationContext, data: OptionRefIn) -> dict:
    """One choice of a menu: what names a dish on the assistant's card; the model reads them with the menu."""
    option = find_option(
        data.id, combo_id=data.combo_id, combo=data.combo, group_id=data.group_id, group=data.group, product=data.product
    )
    return option_row(option, takeaway_targets())


@operation(
    "combo.group.get",
    kind="query",
    permission="combo.view",
    input=GroupRefIn,
    output=GroupOut,
    ai=INTERNAL,
)
def get_group(ctx: OperationContext, data: GroupRefIn) -> dict:
    """One course of a menu with its choices: what names a course on the assistant's card (``schemas.fields.A_COURSE``);
    the model reads the courses with their menu."""
    group = find_group(data.id, data.combo_id, data.combo, data.group)
    prefetch_related_objects([group], _options())
    return group_row(group, takeaway_targets())
