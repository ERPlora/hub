"""Each WhatsApp record lives only in its business's own database (hub#1053), which keeps one channel row and one
live template per name and language whatever business column phase 1 left on its rows (hub#1132)."""

import uuid

import pytest
from django.db import IntegrityError, connections, transaction
from live.context import Scope
from live.errors import NotFound
from live.models import OutboxEvent

from apps.whatsapp_inbox import events
from apps.whatsapp_inbox.models import Channel, Conversation, Message, Template, TemplateSample
from apps.whatsapp_inbox.tests.conftest import ctx_for, receive, run, system, template
from base.tenancy.context import current_alias, use_hub
from base.tenancy.tests import hubs

pytestmark = [
    pytest.mark.django_db(databases=hubs.HUB_DATABASES),
    pytest.mark.usefixtures("no_test_fallback"),
]


def scope(hub) -> Scope:
    return Scope("host", hub.slug)


def test_two_businesses_keep_their_number_and_same_named_template_in_two_real_databases(hub_a, hub_b):
    for hub, phone, body in (
        (hub_a, "+34910000000", "Hola de A"),
        (hub_b, "+34910000001", "Hola de B"),
    ):
        with use_hub(hub):
            system(
                "whatsapp_inbox.channel.sync",
                {
                    "version": 1,
                    "status": "connected",
                    "phone_number": phone,
                    "monthly_limit": 150,
                    "templates": [template("recordatorio", body=body)],
                },
                scope(hub),
            )

    for hub, phone, body in (
        (hub_a, "+34910000000", "Hola de A"),
        (hub_b, "+34910000001", "Hola de B"),
    ):
        with use_hub(hub):
            assert Channel.objects.get().phone_number == phone
            assert Template.objects.get().body == body
            assert Channel.objects.count() == 1
            assert Template.objects.count() == 1


def test_rows_can_be_written_without_a_host_and_read_back_with_their_header_file(hub_a, hub_b):
    for hub in (hub_a, hub_b):
        with use_hub(hub):
            Channel.objects.create(phone_number=f"+3491000000{1 if hub is hub_a else 2}")
            sample = TemplateSample.objects.create(
                header_format=TemplateSample.Kind.IMAGE,
                key=f"hub-{hub.id.hex}/sample.jpg",
                sha256="a" * 64,
                content_type="image/jpeg",
                size=10,
                name="sample.jpg",
            )
            Template.objects.create(
                name="recordatorio",
                language="es",
                body="Hola",
                header_sample=sample,
            )
            listed = run("whatsapp_inbox.template.list", {}, ctx_for(scope=scope(hub)))
            assert listed.total == 1
            assert listed.rows[0].header_sample.id == sample.id
            detail = run(
                "whatsapp_inbox.template_sample.detail",
                {"id": str(sample.id)},
                ctx_for(scope=scope(hub)),
            )
            assert detail.name == "sample.jpg"


def test_the_business_columns_leave_the_models_and_each_database_holds_its_own_template_names(hub_a, hub_b):
    for model, field in (
        (Channel, "host"),
        (Conversation, "erase_host"),
        (Message, "host"),
        (Template, "host"),
        (TemplateSample, "host"),
    ):
        assert field not in {item.name for item in model._meta.get_fields()}

    for hub in (hub_a, hub_b):
        with use_hub(hub):
            Template.objects.create(name="shared-name", language="es", submit_key=uuid.uuid7())
    for hub in (hub_a, hub_b):
        with use_hub(hub):
            assert Template.objects.filter(name="shared-name", language="es").count() == 1


def test_a_header_file_of_another_business_is_never_found(hub_a, hub_b):
    with use_hub(hub_b):
        theirs = TemplateSample.objects.create(
            header_format=TemplateSample.Kind.IMAGE,
            key=f"hub-{hub_b.id.hex}/sample.jpg",
            sha256="b" * 64,
            content_type="image/jpeg",
            size=10,
            name="theirs.jpg",
        )
    with use_hub(hub_a), pytest.raises(NotFound) as gone:
        run("whatsapp_inbox.template_sample.detail", {"id": str(theirs.id)}, ctx_for(scope=scope(hub_a)))
    assert gone.value.code == "whatsapp_inbox.sample_not_found"


def test_a_card_recovered_in_one_business_claims_only_its_own_conversation(hub_a, hub_b):
    """hub#1324: the same number writes to two businesses and both delete her card; the card recovered from the
    separate copy of A (CUSTOMER-F33) takes back A's conversation, and B's stays without a card."""
    cards = {}
    for hub in (hub_a, hub_b):
        with use_hub(hub):
            receive("wamid.1", "34600111222", scope(hub))
            ana = run("customer.customer.create", {"name": "Ana López", "phone": "600111222"}, ctx_for(scope=scope(hub)))
            run("customer.customer.delete", {"id": str(ana.id)}, ctx_for(scope=scope(hub)))
            events.react(scope(hub), events.CUSTOMER_DELETED, {"id": str(ana.id)})
            cards[hub.slug] = ana.id
    with use_hub(hub_a):
        system("customer.customer.restore", {"id": str(cards[hub_a.slug])}, scope(hub_a))
        [restored] = OutboxEvent.objects.filter(name=events.CUSTOMER_RESTORED)
        assert events.react(scope(hub_a), restored.name, restored.payload).count == 1
        assert Conversation.objects.get().customer_id == cards[hub_a.slug]
    with use_hub(hub_b):
        assert not OutboxEvent.objects.filter(name=events.CUSTOMER_RESTORED).exists()
        assert Conversation.objects.get().customer_id is None


def keep_business(row, host: str) -> None:
    """Writes ``host`` on ``row`` in the database of the hub in use, as phase 1 left its rows: the business column
    the models no longer name (hub#1053) but each database still keeps until hub#1132 drops it."""
    with connections[current_alias()].cursor() as cursor:
        cursor.execute(f'UPDATE "{row._meta.db_table}" SET host = %s WHERE id = %s', [host, row.pk])


def refused_by(guard: str, create) -> bool:
    """Whether ``create`` is refused by the database guard called ``guard``, in the database of the hub in use."""
    with pytest.raises(IntegrityError) as refused, transaction.atomic(using=current_alias()):
        create()
    return guard in str(refused.value)


@pytest.mark.parametrize("host", ["a", ""], ids=["first-kept-its-business", "first-has-none"])
def test_a_second_channel_row_is_refused_whatever_business_the_first_kept(hub_a, host):
    with use_hub(hub_a):
        keep_business(Channel.objects.create(phone_number="+34910000000"), host)

        assert refused_by(
            "whatsapp_inbox_channel_one_row", lambda: Channel.objects.create(phone_number="+34910000000")
        )
        assert Channel.objects.count() == 1


@pytest.mark.parametrize("host", ["a", ""], ids=["first-kept-its-business", "first-has-none"])
def test_a_second_live_template_of_a_name_and_language_is_refused_whatever_business_the_first_kept(hub_a, host):
    with use_hub(hub_a):
        keep_business(Template.objects.create(name="recordatorio", language="es"), host)
        Template.objects.create(name="recordatorio", language="en")

        assert refused_by(
            "whatsapp_inbox_template_live_name_language_unique",
            lambda: Template.objects.create(name="recordatorio", language="es"),
        )
        assert Template.objects.filter(name="recordatorio", language="es").count() == 1


def test_the_number_and_the_template_of_another_business_never_clash(hub_a, hub_b):
    for hub in (hub_a, hub_b):
        with use_hub(hub):
            Channel.objects.create(phone_number="+34910000000")
            Template.objects.create(name="recordatorio", language="es")

    for hub in (hub_a, hub_b):
        with use_hub(hub):
            assert list(Channel.objects.values_list("phone_number", flat=True)) == ["+34910000000"]
            assert Template.objects.filter(name="recordatorio", language="es").count() == 1
