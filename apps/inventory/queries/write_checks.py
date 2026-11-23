"""What a write of Inventory names, read before the assistant's card of the write (BASE-F97): the product of a count, a
write-off or a category link, the category of that link, and every product of a reception, each as the write finds it.
A product or a category the business does not have, or a name several fit, is refused at once and the person never sees
a card for it: the model hears which one, and looks it up or asks."""

from uuid import UUID

from live.context import OperationContext
from live.errors import InvalidPayload, NotFound
from live.operations import INTERNAL, get, operation

from apps.inventory.queries.reads import PRODUCT_NOT_FOUND, find_category, find_product
from apps.inventory.schemas.fields import _ProductLineRef
from apps.inventory.schemas.product_categories import ProductCategoryIn
from apps.inventory.schemas.products import ProductOut, ProductsOut
from apps.inventory.schemas.stock import ReceiveIn, ReceiveLineIn


def line_product_unknown(field: str) -> InvalidPayload:
    """A line of a reception whose product the business does not have: a 422 on that line's field."""
    message = str(PRODUCT_NOT_FOUND)
    return InvalidPayload(message, code="invalid_field", fields={field: message})


def line_products(items: list[ReceiveLineIn]) -> list[tuple[int, str, UUID, ReceiveLineIn]]:
    """Each line of a reception with the field that names its product and that product's id, all of them or none."""
    named = []
    for index, line in enumerate(items):
        field = f"items.{index}.product_id" if line.product_id is not None else f"items.{index}.product"
        try:
            named.append((index, field, find_product(line.product_id, line.product).id, line))
        except NotFound as exc:
            raise line_product_unknown(field) from exc
    return named


def _product(ctx: OperationContext, product_id: UUID | None, said: str | None) -> dict:
    read = get("inventory.product.get")
    return read(ctx, read.input.model_validate({"id": product_id, "product": said}))


@operation(
    "inventory.product.check",
    kind="query",
    permission="inventory.view_product",
    input=_ProductLineRef,
    output=ProductOut,
    ai=INTERNAL,
)
def check_product(ctx: OperationContext, data: _ProductLineRef) -> dict:
    """The product a count or a write-off of stock names."""
    return _product(ctx, data.product_id, data.product)


@operation(
    "inventory.product.bulk_check",
    kind="query",
    permission="inventory.view_product",
    input=ReceiveIn,
    output=ProductsOut,
    ai=INTERNAL,
)
def check_products(ctx: OperationContext, data: ReceiveIn) -> dict:
    """The products a reception names, once every line names one the business has."""
    named = dict.fromkeys(product_id for _, _, product_id, _ in line_products(data.items))
    return {"rows": [_product(ctx, product_id, None) for product_id in named]}


@operation(
    "inventory.product_category.check",
    kind="query",
    permission="inventory.view_product",
    input=ProductCategoryIn,
    output=ProductOut,
    ai=INTERNAL,
)
def check_product_category(ctx: OperationContext, data: ProductCategoryIn) -> dict:
    """The product a write puts in a category or takes out of it, once that category is there too."""
    product = _product(ctx, data.product_id, data.product)
    find_category(data.category_id, data.category)
    return product
