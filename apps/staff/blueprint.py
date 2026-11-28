"""What of Staff travels in an export of the business (BASE-F35): the roles it uses, by their name, read with Staff's
own list and written with its own create. The people, their schedules and their time off never travel, nor a retired
role. A role is retired, never deleted, so what a load brings stays like the rest of the business's settings."""

from django.utils.translation import gettext_lazy as _

from base.blueprint.calls import Dataset, by_name, count_of, rows_of

ROLE_FIELDS = ("name", "description", "color", "order")


DATASETS = [
    Dataset(
        key="staff.role",
        label=_("Roles"),
        rows=rows_of("staff.role.list", ROLE_FIELDS, is_active=True),
        count=count_of("staff.role.list", is_active=True),
        load=by_name("staff.role.list", "staff.role.create", ROLE_FIELDS),
        models=("Role",),
    ),
]
