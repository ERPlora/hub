"""What Customers brings back from a separate copy: the cards the business lost, the deleted ones the same and the
gone ones created anew, and why one does not come back. The databases are ``conftest.py``'s, the rest of what it
runs on ``test_recovery``'s."""

import uuid

from django.apps import apps as django_apps
from live.models import OutboxEvent
from live.operations import get as get_operation

from base import recovery as base_recovery
from base.tenancy.context import use_hub
from base.tenancy.tests.test_recovery import (
    ANA,
    AT,
    CUSTOMERS,
    LUIS,
    MARTA,
    fresh,
    gone,
    in_the_copy,
    live_cards,
    run,
    run_in,
)
from control.models import CopyRecovery, Hub


def created_events(hub: Hub) -> int:
    with use_hub(hub):
        return OutboxEvent.objects.filter(name="customer.customer.created").count()


def restored_events(hub: Hub) -> int:
    with use_hub(hub):
        return OutboxEvent.objects.filter(name="customer.customer.restored").count()


class TestCustomersComeBack:
    def test_the_cards_the_business_lost_come_back_the_deleted_the_same_and_the_gone_created_anew(
        self, recoveries, every_app_on
    ):
        hub, (ana, luis, _marta) = recoveries.business(every_app_on, ANA, LUIS, MARTA)
        copy = recoveries.copy_of(hub)
        # Lost since the copy: Ana deleted from her card, Luis's row gone altogether.
        run_in(hub, "customer.customer.delete", id=ana)
        gone(hub, luis)
        asked = recoveries.ask(copy)
        before = (created_events(hub), restored_events(hub))

        assert run() == 1

        assert live_cards(hub) == [
            ("Ana López", "+34600111222", "ana@example.com", "Madrid"),
            ("Luis Pérez", "+34600333444", "luis@example.com", ""),
            ("Marta Ruiz", "+34600555666", "marta@example.com", ""),
        ]
        # Ana, still in the business, is the same card back by Customers' restore; Luis, gone, a new one by its create:
        # never a copied row, each with its event.
        with use_hub(hub):
            from apps.customer.models import Customer

            assert Customer.objects.live().get(name="Ana López").pk == ana
            again = Customer.objects.live().get(name="Luis Pérez")
            assert (again.pk != luis, again.notes) == (True, "Prefers mornings")
            assert Customer.objects.count() == 3
        assert (created_events(hub), restored_events(hub)) == (before[0] + 1, before[1] + 1)
        done = fresh(asked)
        assert (done.status, done.done_at, done.last_error, done.lease_owner) == ("done", AT, "", "")
        assert done.results == [CUSTOMERS | {"restored": 1, "created": 1}]

    def test_a_card_the_business_deleted_comes_back_with_its_purchases_consents_notes_and_activity(
        self, recoveries, every_app_on
    ):
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        run_in(hub, "customer.note.add", customer_id=ana, content="Prefers mornings")
        run_in(
            hub,
            "customer.consent.grant",
            customer_id=ana,
            channel="email",
            notice_text="I want offers.",
            notice_version="v1",
        )
        run_in(hub, "customer.purchase.record", customer_id=ana, sale_id=uuid.uuid7(), total=2500, currency="EUR")
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        recoveries.ask(copy)

        run()

        detail = run_in(hub, "customer.customer.detail", id=ana)
        assert (detail.id, detail.total_purchases, detail.total_spent) == (ana, 1, 2500)
        with use_hub(hub):
            from apps.customer.models import Customer

            back = Customer.objects.live().get()
            assert back.pk == ana
            assert (back.purchases.count(), back.consents.count()) == (1, 1)
            assert back.activity.filter(kind="note_added", text="Prefers mornings").exists()

    def test_every_event_of_what_comes_back_says_the_recovery_did_it_and_one_of_the_business_does_not(
        self, recoveries, every_app_on
    ):
        """hub#1307: the apps' operations run as the recovery (``base.recovery.actor_of``), so each event they record
        keeps it as its actor in the outbox, and what reacts to it tells what came back from what the business does
        (an automation of «customer created» starts nothing for a card brought back, FLOW-F21)."""
        hub, (ana, luis) = recoveries.business(every_app_on, ANA, LUIS)
        # Luis in a group the business keeps and in a deactivated one, with a tag and a custom field's value: the
        # deactivated group, the tag and the field are deleted after the copy, so his card makes them again.
        vip = run_in(hub, "customer.group.create", name="VIP").id
        old = run_in(hub, "customer.group.create", name="Old").id
        regular = run_in(hub, "customer.tag.create", name="Regular").id
        pet = run_in(hub, "customer.field.create", name="Pet").id
        run_in(hub, "customer.customer.set_groups", id=luis, group_ids=[vip, old])
        run_in(hub, "customer.customer.set_tags", id=luis, tag_ids=[regular])
        run_in(hub, "customer.customer.update", id=luis, field_values=[{"field_id": pet, "value": "Luna"}])
        run_in(hub, "customer.group.update", id=old, is_active=False)
        # And a product in its own category: both deleted after the copy, so the category comes back with it inside.
        with use_hub(hub):
            from apps.tax.models import TaxCategory

            tax = TaxCategory.objects.filter(is_active=True).order_by("key").values_list("key", flat=True).first()
        desserts = run_in(hub, "inventory.category.create", name="Desserts").id
        cake = run_in(
            hub, "inventory.product.create", name="Cake", sku="CAK-1", price=400, tax_category_key=tax,
            category_ids=[desserts],
        ).id
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        gone(hub, luis)
        for operation, deleted in (("customer.group.delete", old), ("customer.tag.delete", regular)):
            run_in(hub, operation, id=deleted)
        run_in(hub, "customer.field.delete", id=pet)
        run_in(hub, "inventory.product.delete", id=cake)
        run_in(hub, "inventory.category.delete", id=desserts)
        asked = recoveries.ask(copy, "customer", "inventory")
        with use_hub(hub):
            before = list(OutboxEvent.objects.values_list("pk", flat=True))

        assert run() == 1
        run_in(hub, "customer.customer.create", **MARTA)

        with use_hub(hub):
            recorded = OutboxEvent.objects.exclude(pk__in=before).order_by("created_at", "id")
            said = [(event.name, event.actor) for event in recorded]
        mark = base_recovery.actor_of(asked.pk)
        assert said == [
            ("customer.customer.restored", mark),
            ("customer.customer.created", mark),
            ("customer.group.created", mark),
            ("customer.group.updated", mark),
            ("customer.customer.groups_changed", mark),
            ("customer.tag.created", mark),
            ("customer.customer.tags_changed", mark),
            ("customer.field.created", mark),
            ("inventory.category.created", mark),
            ("inventory.product.categorized", mark),
            ("inventory.product.restored", mark),
            ("customer.customer.created", "system"),
        ]
        assert [base_recovery.brought_back(actor) for _name, actor in said] == [True] * 11 + [False]

    def test_asked_again_nothing_is_made_twice(self, recoveries, every_app_on):
        hub, (ana, _luis) = recoveries.business(every_app_on, ANA, LUIS)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        recoveries.ask(copy)
        run()
        again = recoveries.ask(copy)

        assert run() == 1

        assert [card[0] for card in live_cards(hub)] == ["Ana López", "Luis Pérez"]
        assert fresh(again).results == [CUSTOMERS]

    def test_a_card_whose_personal_data_was_erased_or_merged_into_another_never_comes_back(
        self, recoveries, every_app_on
    ):
        hub, (ana, luis, marta) = recoveries.business(every_app_on, ANA, LUIS, MARTA)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.erase", id=ana, reason="Asked under GDPR")
        run_in(hub, "customer.customer.merge", id=marta, absorbed_id=luis)
        asked = recoveries.ask(copy)

        assert run() == 1

        assert [card[0] for card in live_cards(hub)] == ["Marta Ruiz"]
        # Neither restored nor refused: not even asked of Customers.
        assert (restored_events(hub), fresh(asked).results) == (0, [CUSTOMERS])

    def test_a_card_the_business_made_again_by_hand_is_not_made_once_more(self, recoveries, every_app_on):
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        run_in(hub, "customer.customer.create", **ANA)
        asked = recoveries.ask(copy)

        run()

        assert [card[0] for card in live_cards(hub)] == ["Ana López"]
        assert fresh(asked).results == [CUSTOMERS]

    def test_a_card_its_operation_refuses_is_counted_with_why_and_the_others_come_back(self, recoveries, every_app_on):
        hub, (ana, luis) = recoveries.business(every_app_on, ANA, LUIS)
        copy = recoveries.copy_of(hub)
        gone(hub, ana, luis)
        # In the copy, a phone today's rules do not take.
        in_the_copy(copy, "UPDATE customer_customer SET phone = %s WHERE id = %s", ["12", luis])
        asked = recoveries.ask(copy)

        run()

        assert [card[0] for card in live_cards(hub)] == ["Ana López"]
        [customers] = fresh(asked).results
        assert (customers["created"], customers["not_created"], customers["refused"]) == (1, 1, "")
        [why] = customers["reasons"]
        assert why["id"] == str(luis)
        assert why["reason"].startswith("customer.phone_invalid: ")

    def test_what_was_deleted_comes_back_before_anything_is_created_so_the_person_is_not_made_twice(
        self, recoveries, every_app_on
    ):
        # The copy holds Ana twice (the same name, phone and email): the business deleted one and lost the other.
        hub, (deleted, lost) = recoveries.business(every_app_on, ANA, ANA)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=deleted)
        gone(hub, lost)
        asked = recoveries.ask(copy)

        run()

        with use_hub(hub):
            from apps.customer.models import Customer

            assert list(Customer.objects.live().values_list("pk", flat=True)) == [deleted]
        assert fresh(asked).results == [CUSTOMERS | {"restored": 1}]

    def test_a_card_its_restore_refuses_is_counted_with_why_and_the_others_come_back(
        self, recoveries, every_app_on, monkeypatch
    ):
        hub, (ana, luis, marta) = recoveries.business(every_app_on, ANA, LUIS, MARTA)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        run_in(hub, "customer.customer.merge", id=marta, absorbed_id=luis)
        # Luis held deleted when the business was read, and merged into Marta before his turn came.
        customers = django_apps.get_app_config("customer")
        [declared] = customers.recoverable_from_copy()
        held = type(declared)(**(vars(declared) | {"deleted": lambda cards: [c for c in cards if c["id"] in {ana, luis}]}))
        monkeypatch.setattr(type(customers), "recoverable_from_copy", lambda self: [held])
        asked = recoveries.ask(copy)

        run()

        assert [card[0] for card in live_cards(hub)] == ["Ana López", "Marta Ruiz"]
        [customers_back] = fresh(asked).results
        assert (customers_back["restored"], customers_back["not_created"], customers_back["refused"]) == (1, 1, "")
        [why] = customers_back["reasons"]
        assert why["id"] == str(luis)
        assert why["reason"].startswith("customer.customer_unavailable: ")

    def test_the_reasons_are_said_in_the_language_of_the_staff_who_asked(self, recoveries, every_app_on):
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        gone(hub, ana)
        in_the_copy(copy, "UPDATE customer_customer SET phone = %s WHERE id = %s", ["12", ana])
        asked = recoveries.ask(copy, language="es")

        run()

        [customers] = fresh(asked).results
        [why] = customers["reasons"]
        from django.utils import translation

        from apps.customer.services import PHONE_INVALID

        with translation.override("es"):
            assert why["reason"] == f"customer.phone_invalid: {PHONE_INVALID}"
        assert str(PHONE_INVALID) not in why["reason"]

    def test_only_the_first_reasons_are_kept_and_every_card_not_created_is_counted(
        self, recoveries, every_app_on, monkeypatch
    ):
        hub, ids = recoveries.business(every_app_on, ANA, LUIS)
        copy = recoveries.copy_of(hub)
        gone(hub, *ids)
        in_the_copy(copy, "UPDATE customer_customer SET phone = '12'")
        monkeypatch.setattr(CopyRecovery, "REASONS_KEPT", 1)
        asked = recoveries.ask(copy)

        run()

        [customers] = fresh(asked).results
        assert (customers["created"], customers["not_created"], len(customers["reasons"])) == (0, 2, 1)

    def test_an_app_the_business_turned_off_is_refused_with_why_and_nothing_is_made(self, recoveries, every_app_on):
        hub, asked = recoveries.deleted_with_customers_off(every_app_on)

        run()

        assert live_cards(hub) == []
        [customers] = fresh(asked).results
        assert customers["created"] == 0
        assert customers["refused"].startswith("app_inactive: ")
        assert fresh(asked).status == "done"

    def test_a_business_that_is_not_ready_fails_with_why_and_nothing_is_made(self, recoveries, every_app_on):
        hub, (ana,) = recoveries.business(every_app_on, ANA)
        copy = recoveries.copy_of(hub)
        run_in(hub, "customer.customer.delete", id=ana)
        Hub.objects.filter(pk=hub.pk).update(status=Hub.Status.CANCELLED)
        asked = recoveries.ask(copy)

        assert run() == 1

        failed = fresh(asked)
        assert (failed.status, failed.results, failed.lease_owner) == ("failed", [], "")
        assert failed.last_error.startswith("recover_business_unavailable: ")
        assert live_cards(hub) == []

    def test_a_failure_halfway_keeps_what_had_come_back_until_then(self, recoveries, every_app_on, monkeypatch):
        hub, asked = recoveries.all_lost(every_app_on, ANA, LUIS)
        op = get_operation("customer.customer.create")
        real, made = op.fn, []

        def breaks_at_the_second(ctx, data):
            if made:
                raise RuntimeError("the business's database went away")
            made.append(real(ctx, data))
            return made[0]

        monkeypatch.setattr(op, "fn", breaks_at_the_second)

        assert run() == 1

        failed = fresh(asked)
        assert failed.status == "failed"
        assert failed.last_error == "recover_unexpected: RuntimeError: the business's database went away"
        # The staff reads what did come back before it broke, not an empty result.
        assert failed.results == [CUSTOMERS | {"created": 1}]
        assert len(live_cards(hub)) == 1
