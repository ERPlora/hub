"""What of Automations travels in an export of the business (BASE-F35): every automation with when it starts and its
steps, read with Automations' own list and written with its own create. It arrives paused and with no permission given,
as a copied automation does: the owner reviews it and gives it what it may do. Its runs, its questions, the
assistant's drafts and the secrets its steps send never travel.

Every test runs against the real apps, in business A's own database, as production does.
"""

from apps.flow.tests.conftest import HUB_DB, TASK_STEP, in_business_a
from base.tests.blueprint_round_trip import app_report, call, ctx, data_of, exported, loaded_back

__all__ = ["ctx", "in_business_a"]
pytestmark = HUB_DB

WELCOME = {"name": "Welcome", "trigger": {"kind": "event", "event": "customer.customer.created"}, "steps": [TASK_STEP]}
MONDAYS = {"name": "Mondays", "trigger": {"kind": "manual"}, "steps": []}


def the_automations(ctx) -> list[tuple]:
    return sorted(
        (row.name, row.trigger, row.steps, row.enabled, row.grants)
        for row in call(ctx, "flow.flow.list", limit=100).rows
    )


def test_a_backup_brings_the_automations_back_paused_and_without_permissions(ctx):
    welcome = call(ctx, "flow.flow.create", **WELCOME)
    call(ctx, "flow.flow.grant", id=welcome.id, operations=["task.task.create"])
    call(ctx, "flow.flow.set_enabled", id=welcome.id, enabled=True)
    call(ctx, "flow.flow.create", **MONDAYS)
    before = [(name, trigger, steps) for name, trigger, steps, _, _ in the_automations(ctx)]
    file = exported(ctx, ["flow"])
    for row in call(ctx, "flow.flow.list", limit=100).rows:
        call(ctx, "flow.flow.delete", id=row.id)

    report = loaded_back(ctx, file)

    assert the_automations(ctx) == [(name, trigger, steps, False, []) for name, trigger, steps in before]
    assert [(part["created"], part["already"]) for part in app_report(report, "flow")["datasets"]] == [(2, 0)]


def test_loading_the_file_again_duplicates_nothing(ctx):
    call(ctx, "flow.flow.create", **WELCOME)

    report = loaded_back(ctx, exported(ctx, ["flow"]))

    assert [(part["created"], part["already"]) for part in app_report(report, "flow")["datasets"]] == [(0, 1)]


def test_only_the_automations_travel_never_their_permissions(ctx):
    welcome = call(ctx, "flow.flow.create", **WELCOME)
    call(ctx, "flow.flow.grant", id=welcome.id, operations=["task.task.create"])

    data = data_of(ctx, ["flow"])

    assert set(data) == {"flow.flow"}
    assert data["flow.flow"] == [{"name": "Welcome", "trigger": welcome.trigger, "steps": welcome.steps}]
