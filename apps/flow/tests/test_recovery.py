"""Automations and what a recovery brings back from a separate copy of the business (hub#1307; FLOW-F21, BASE-F114).

A card the business lost and the staff brings back from one of its separate copies is no new customer: the
automations that wait for «customer created» (a welcome, a task) start nothing for it, nor those that wait for
«customer restored» for the one that comes back the same. A card the business makes afterwards still starts them.

Real databases, as the recovery runs (``base.tenancy.tests.test_recovery``): the business's own and its copy; the
worker's relay (``base.relay``) hands every event over, as it does in each business every tick.
"""

import pytest
from django.utils import timezone

from apps.flow.models import Flow, FlowRun
from apps.flow.tests.conftest import make_flow
from base import relay
from base.tenancy.context import use_hub
from base.tenancy.tests.test_recovery import ANA, LUIS, MARTA, Recoveries, gone, run, run_in

pytestmark = pytest.mark.usefixtures("no_test_fallback")


@pytest.fixture
def recoveries(django_db_blocker, hub_databases):
    with django_db_blocker.unblock():
        made = Recoveries(hub_databases.template)
        yield made
        made.clean()


def relayed(hub) -> None:
    """One pass of the worker's relay in ``hub``: every event it holds handed to the apps that listen to it."""
    with use_hub(hub):
        relay.run(timezone.now())


def runs(hub) -> list[tuple[str, str]]:
    """The runs the automations of ``hub`` started: each one's automation and what started it."""
    with use_hub(hub):
        return sorted(FlowRun.objects.values_list("flow__name", "event_name"))


class TestWhatARecoveryBringsBack:
    def a_business_that_welcomes(self, recoveries, every_app_on):
        """A business with Ana and Luis, made before its two automations of a new and a restored card were on, and a
        copy of it; since the copy, Ana deleted from her card and Luis gone altogether."""
        hub, (ana, luis) = recoveries.business(every_app_on, ANA, LUIS)
        relayed(hub)
        with use_hub(hub):
            make_flow("Welcome")
            make_flow("Welcome back", trigger_event="customer.customer.restored")
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        gone(hub, luis)
        relayed(hub)
        return hub, copy

    def test_the_cards_it_brings_back_start_no_automation_of_a_new_or_a_restored_card(self, recoveries, every_app_on):
        hub, copy = self.a_business_that_welcomes(recoveries, every_app_on)
        recoveries.ask(copy)

        assert run() == 1
        relayed(hub)

        # Ana came back the same and Luis was made again, each with its event, and neither is welcomed.
        with use_hub(hub):
            from apps.customer.models import Customer

            assert Customer.objects.live().count() == 2
            assert Flow.objects.filter(enabled=True).count() == 2
        assert runs(hub) == []

    def test_what_hangs_from_a_card_it_makes_again_starts_no_automation_of_its_own(self, recoveries, every_app_on):
        """Luis, gone, comes back with a group, a tag and a custom field the business deleted since, made again by
        their own operations: none of their events starts the automations that wait for them. The same event done by
        the business afterwards still does."""
        waited = (
            "customer.group.created",
            "customer.tag.created",
            "customer.field.created",
            "customer.customer.groups_changed",
            "customer.customer.tags_changed",
        )
        hub, (_ana, luis) = recoveries.business(every_app_on, ANA, LUIS)
        vip = run_in(hub, "customer.group.create", name="VIP").id
        regular = run_in(hub, "customer.tag.create", name="Regular").id
        pet = run_in(hub, "customer.field.create", name="Pet").id
        run_in(hub, "customer.customer.set_groups", id=luis, group_ids=[vip])
        run_in(hub, "customer.customer.set_tags", id=luis, tag_ids=[regular])
        run_in(hub, "customer.customer.update", id=luis, field_values=[{"field_id": pet, "value": "Luna"}])
        relayed(hub)
        with use_hub(hub):
            for event in waited:
                make_flow(f"On {event}", trigger_event=event)
        copy = recoveries.copy_of(hub)
        gone(hub, luis)
        for operation, deleted in (
            ("customer.group.delete", vip),
            ("customer.tag.delete", regular),
            ("customer.field.delete", pet),
        ):
            run_in(hub, operation, id=deleted)
        relayed(hub)
        recoveries.ask(copy)

        assert run() == 1
        relayed(hub)

        with use_hub(hub):
            from apps.customer.models import Customer

            again = Customer.objects.live().get(name=LUIS["name"])
            assert (again.groups.count(), again.tags.count(), again.field_values.count()) == (1, 1, 1)
        assert runs(hub) == []
        run_in(hub, "customer.customer.set_groups", id=again.pk, group_ids=[])
        relayed(hub)
        assert runs(hub) == [("On customer.customer.groups_changed", "customer.customer.groups_changed")]

    def test_a_card_the_business_makes_afterwards_still_starts_them(self, recoveries, every_app_on):
        hub, copy = self.a_business_that_welcomes(recoveries, every_app_on)
        recoveries.ask(copy)
        assert run() == 1
        relayed(hub)

        run_in(hub, "customer.customer.create", **MARTA)
        relayed(hub)

        assert runs(hub) == [("Welcome", "customer.customer.created")]
