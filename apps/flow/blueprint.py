"""What of Automations travels in an export of the business (BASE-F35): every automation, by its name, with when it
starts and its steps, read with Automations' own list and written with its own create. A new automation is born paused
and with no permission given, so one a file brings waits for the owner to review it and give it what it may do, as a
copied automation does elsewhere. Its runs, its questions, the assistant's drafts and the secrets never travel."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext

from base.blueprint.calls import Dataset, Loaded, count_of, create_each, given, ids_of, natural_key, pages, remover
from base.blueprint.calls import text_of

FLOW_FIELDS = ("name", "trigger", "steps")


def _flow_rows(ctx: OperationContext) -> list[dict]:
    return [{name: getattr(row, name) for name in FLOW_FIELDS} for row in pages(ctx, "flow.flow.list", sort="name")]


def _flow_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {natural_key(row.name) for row in pages(ctx, "flow.flow.list")}
    create_each(ctx, rows, loaded, name="flow.flow.create", key=lambda row: natural_key(text_of(row, "name")),
                existing=existing, build=lambda row: given(row, FLOW_FIELDS), label=lambda row: text_of(row, "name"))


DATASETS = [
    Dataset(
        key="flow.flow",
        label=_("Automations"),
        rows=_flow_rows,
        ids=ids_of("flow.flow.list"),
        count=count_of("flow.flow.list"),
        load=_flow_load,
        remove=remover("flow.flow.delete"),
        models=("Flow",),
    ),
]
