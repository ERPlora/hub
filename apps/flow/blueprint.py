"""What of Automations travels in an export of the business (BASE-F35): every automation, by its name, with when it
starts and its steps, read with Automations' own list and written with its own create. A new automation is born paused
and with no permission given, so one a file brings waits for the owner to review it and give it what it may do, as a
copied automation does elsewhere. Its runs, its questions, the assistant's drafts and the secrets never travel."""

from django.utils.translation import gettext_lazy as _

from base.blueprint.calls import Dataset, by_name, count_of, ids_of, remover, rows_of

FLOW_FIELDS = ("name", "trigger", "steps")


DATASETS = [
    Dataset(
        key="flow.flow",
        label=_("Automations"),
        rows=rows_of("flow.flow.list", FLOW_FIELDS, sort="name"),
        ids=ids_of("flow.flow.list"),
        count=count_of("flow.flow.list"),
        load=by_name("flow.flow.list", "flow.flow.create", FLOW_FIELDS),
        remove=remover("flow.flow.delete"),
        models=("Flow",),
    ),
]
