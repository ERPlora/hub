"""What of Sales travels in an export of the business (BASE-F35): the till's own setup, read with Sales' own lists and
written with its own creates — the payment methods, by name, the departments of the open price with the tax category
each charges at, and the quick notes of a line. The checks, the sales, the refunds and the day's numbers never travel.
A payment method has no delete: like the business's settings, one a load brought stays."""

from django.utils.translation import gettext_lazy as _

from base.blueprint.calls import Dataset, by_name, count_of, ids_of, remover, rows_of

METHOD_FIELDS = ("name", "type", "sort_order")
DEPARTMENT_FIELDS = ("name", "tax_category_key", "sort_order")
NOTE_FIELDS = ("text", "sort_order")


DATASETS = [
    Dataset(
        key="sale.payment_method",
        label=_("Payment methods"),
        rows=rows_of("sale.payment_method.list", METHOD_FIELDS),
        count=count_of("sale.payment_method.list"),
        load=by_name("sale.payment_method.list", "sale.payment_method.create", METHOD_FIELDS),
        models=("PaymentMethod",),
    ),
    Dataset(
        key="sale.department",
        label=_("Open price departments"),
        rows=rows_of("sale.department.list", DEPARTMENT_FIELDS),
        ids=ids_of("sale.department.list"),
        count=count_of("sale.department.list"),
        load=by_name("sale.department.list", "sale.department.create", DEPARTMENT_FIELDS),
        remove=remover("sale.department.delete"),
        models=("Department",),
    ),
    Dataset(
        key="sale.quick_note",
        label=_("Quick notes"),
        rows=rows_of("sale.quick_note.list", NOTE_FIELDS),
        ids=ids_of("sale.quick_note.list"),
        count=count_of("sale.quick_note.list"),
        load=by_name("sale.quick_note.list", "sale.quick_note.create", NOTE_FIELDS, named="text"),
        remove=remover("sale.quick_note.delete"),
        models=("QuickNote",),
    ),
]
