"""What of Cash register travels in an export of the business (BASE-F35): its active drawers, by name, read with its
own list and written with its own create. The sessions, their movements and counts never travel. A drawer is retired,
never deleted, so what a load brings stays like the rest of the business's settings."""

from django.utils.translation import gettext_lazy as _

from base.blueprint.calls import Dataset, by_name, count_of, rows_of

DATASETS = [
    Dataset(
        key="cash_register.register",
        label=_("Drawers"),
        rows=rows_of("cash_register.register.list", ("name",), is_active=True),
        count=count_of("cash_register.register.list", is_active=True),
        load=by_name("cash_register.register.list", "cash_register.register.create", ("name",)),
        models=("Register",),
    ),
]
