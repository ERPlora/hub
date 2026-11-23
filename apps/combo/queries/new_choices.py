"""What a new choice names, read before the assistant's card of the write that adds it (COMBO-F06): the course, and each
product as the write finds it in Inventory. A product the business does not have is refused at once, on its field, and
the person never sees a card for it: the model hears which one is missing, and looks it up or asks."""

from uuid import UUID

from live.context import OperationContext
from live.errors import InvalidPayload, NotFound
from live.operations import INTERNAL, get, operation

from apps.combo.schemas import GroupOut, OptionBulkIn, OptionIn
from apps.inventory.models import Product
from apps.inventory.queries.reads import find_product


def field_refusal(error: NotFound, field: str) -> InvalidPayload:
    """A reference of a write that does not exist is a 422 on its field, not a 404 of the write."""
    return InvalidPayload(error.message, code="invalid_field", fields={field: error.message})


def product_said(product_id: UUID | None, said: str | None, field: str) -> Product:
    """The live product a new choice names, by its id or as the person says it; one that is not there is a 422 on
    ``field``, never a 404 of the write."""
    try:
        return find_product(product_id, said)
    except NotFound as error:
        raise field_refusal(error, field) from None


def _course(ctx: OperationContext, data: OptionIn | OptionBulkIn) -> GroupOut:
    read = get("combo.group.get")
    named = {"id": data.group_id, "combo_id": data.combo_id, "combo": data.combo, "group": data.group}
    return read(ctx, read.input.model_validate(named))


@operation(
    "combo.option.check",
    kind="query",
    permission="combo.view",
    input=OptionIn,
    output=GroupOut,
    ai=INTERNAL,
)
def check_option(ctx: OperationContext, data: OptionIn) -> GroupOut:
    """The course ``combo.option.create`` adds its choice to, once the product it offers is there."""
    course = _course(ctx, data)
    product_said(data.product_id, data.product, "product_id" if data.product_id else "product")
    return course


@operation(
    "combo.option.bulk_check",
    kind="query",
    permission="combo.view",
    input=OptionBulkIn,
    output=GroupOut,
    ai=INTERNAL,
)
def check_options(ctx: OperationContext, data: OptionBulkIn) -> GroupOut:
    """The course ``combo.option.bulk_create`` adds its choices to, once every product it offers is there."""
    course = _course(ctx, data)
    for product_id in data.product_ids:
        product_said(product_id, None, "product_ids")
    return course
