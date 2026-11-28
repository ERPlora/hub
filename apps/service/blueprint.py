"""What of Services travels in an export of the business (BASE-F35) besides its categories and services, which the
platform carries: the vouchers of its catalogue, each with its terms and its services by name, read with Services' own
list and written with its own create. A voucher is named by its name. The vouchers sold, and the sessions spent of them,
never travel: they already happened."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext

from base.blueprint.calls import Dataset, by_name, count_of, ids_of, pages, remover

TERMS = (
    "name", "description", "discount_type", "discount_percent_bp", "discount_amount", "fixed_price", "validity_days",
    "max_uses", "is_active", "is_featured", "sort_order",
)  # fmt: skip
PACKAGE_FIELDS = (*TERMS, "items")


def _package_rows(ctx: OperationContext) -> list[dict]:
    return [
        {
            **{name: getattr(row, name) for name in TERMS},
            "items": [{"service": item.service_name, "sessions": item.sessions} for item in row.items],
        }
        for row in pages(ctx, "service.package.list")
    ]


DATASETS = [
    Dataset(
        key="service.package",
        label=_("Vouchers"),
        rows=_package_rows,
        ids=ids_of("service.package.list"),
        count=count_of("service.package.list"),
        load=by_name("service.package.list", "service.package.create", PACKAGE_FIELDS),
        remove=remover("service.package.delete"),
        models=("Package", "PackageItem"),
    ),
]
