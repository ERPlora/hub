"""What of Customers travels in an export of the business (BASE-F35) besides the customers themselves: its active
groups, tags and custom fields, by their name, read with Customers' own lists and written with its own creates."""

from django.utils.translation import gettext_lazy as _

from base.blueprint.calls import Dataset, by_name, count_of, ids_of, remover, rows_of

GROUP_FIELDS = ("name", "description", "color", "sort_order")
TAG_FIELDS = ("name", "color")
FIELD_FIELDS = ("name", "field_type", "options", "is_required", "sort_order")
ACTIVE = {"is_active": True}


def _catalogue(entity: str, label, fields: tuple[str, ...], model: str) -> Dataset:
    listed = f"customer.{entity}.list"
    return Dataset(
        key=f"customer.{entity}",
        label=label,
        rows=rows_of(listed, fields, **ACTIVE),
        ids=ids_of(listed, **ACTIVE),
        count=count_of(listed, **ACTIVE),
        load=by_name(listed, f"customer.{entity}.create", fields),
        remove=remover(f"customer.{entity}.delete"),
        models=(model,),
    )


DATASETS = [
    _catalogue("group", _("Customer groups"), GROUP_FIELDS, "CustomerGroup"),
    _catalogue("tag", _("Customer tags"), TAG_FIELDS, "CustomerTag"),
    _catalogue("field", _("Custom fields"), FIELD_FIELDS, "CustomField"),
]
