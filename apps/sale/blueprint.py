"""What of Sales travels in an export of the business (BASE-F35): the till's own setup, read with Sales' own lists and
written with its own creates — the payment methods, by name, the departments of the open price with the tax category
each charges at, and the quick notes of a line. The checks, the sales, the refunds and the day's numbers never travel.
A payment method has no delete: like the business's settings, one a load brought stays."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext

from base.blueprint.calls import Dataset, Loaded, count_of, create_each, given, ids_of, natural_key, pages, remover
from base.blueprint.calls import text_of

METHOD_FIELDS = ("name", "type", "sort_order")
DEPARTMENT_FIELDS = ("name", "tax_category_key", "sort_order")
NOTE_FIELDS = ("text", "sort_order")


def _rows(operation: str, fields: tuple[str, ...]):
    return lambda ctx: [{name: getattr(row, name) for name in fields} for row in pages(ctx, operation)]


def _loader(list_operation: str, create: str, fields: tuple[str, ...], named: str):
    """Each row the business does not have, by its ``named`` field, made with ``create``."""

    def load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
        existing = {natural_key(getattr(row, named)) for row in pages(ctx, list_operation)}
        create_each(ctx, rows, loaded, name=create, key=lambda row: natural_key(text_of(row, named)),
                    existing=existing, build=lambda row: given(row, fields), label=lambda row: text_of(row, named))

    return load


DATASETS = [
    Dataset(
        key="sale.payment_method",
        label=_("Payment methods"),
        rows=_rows("sale.payment_method.list", METHOD_FIELDS),
        count=count_of("sale.payment_method.list"),
        load=_loader("sale.payment_method.list", "sale.payment_method.create", METHOD_FIELDS, "name"),
        models=("PaymentMethod",),
    ),
    Dataset(
        key="sale.department",
        label=_("Open price departments"),
        rows=_rows("sale.department.list", DEPARTMENT_FIELDS),
        ids=ids_of("sale.department.list"),
        count=count_of("sale.department.list"),
        load=_loader("sale.department.list", "sale.department.create", DEPARTMENT_FIELDS, "name"),
        remove=remover("sale.department.delete"),
        models=("Department",),
    ),
    Dataset(
        key="sale.quick_note",
        label=_("Quick notes"),
        rows=_rows("sale.quick_note.list", NOTE_FIELDS),
        ids=ids_of("sale.quick_note.list"),
        count=count_of("sale.quick_note.list"),
        load=_loader("sale.quick_note.list", "sale.quick_note.create", NOTE_FIELDS, "text"),
        remove=remover("sale.quick_note.delete"),
        models=("QuickNote",),
    ),
]
