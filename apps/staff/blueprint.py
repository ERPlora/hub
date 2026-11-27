"""What of Staff travels in an export of the business (BASE-F35): the roles it uses, by their name, read with Staff's
own list and written with its own create. The people, their schedules and their time off never travel, nor a retired
role. A role is retired, never deleted, so what a load brings stays like the rest of the business's settings."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext

from base.blueprint.calls import Dataset, Loaded, count_of, create_each, given, natural_key, pages, text_of

ROLE_FIELDS = ("name", "description", "color", "order")


def _role_rows(ctx: OperationContext) -> list[dict]:
    return [{name: getattr(row, name) for name in ROLE_FIELDS} for row in pages(ctx, "staff.role.list", is_active=True)]


def _role_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {natural_key(row.name) for row in pages(ctx, "staff.role.list")}
    create_each(ctx, rows, loaded, name="staff.role.create", key=lambda row: natural_key(text_of(row, "name")),
                existing=existing, build=lambda row: given(row, ROLE_FIELDS), label=lambda row: text_of(row, "name"))


DATASETS = [
    Dataset(
        key="staff.role",
        label=_("Roles"),
        rows=_role_rows,
        count=count_of("staff.role.list", is_active=True),
        load=_role_load,
        models=("Role",),
    ),
]
