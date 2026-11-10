"""Each WhatsApp record lives only in its business's own database (hub#1053)."""

import uuid

import pytest
from live.context import Scope

from apps.whatsapp_inbox.models import Channel, Conversation, Message, Template, TemplateSample
from apps.whatsapp_inbox.tests.conftest import ctx_for, run, system, template
from base.tenancy.context import use_hub
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
            row = Template.objects.create(
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


def test_business_columns_leave_the_models_but_their_data_is_not_queried_between_hubs(hub_a, hub_b):
    for model, field in (
        (Channel, "host"),
        (Conversation, "erase_host"),
        (Message, "host"),
        (Template, "host"),
        (TemplateSample, "host"),
    ):
        assert field not in {item.name for item in model._meta.get_fields()}

    with use_hub(hub_a):
        Template.objects.create(name="shared-name", language="es", submit_key=uuid.uuid7())
    with use_hub(hub_b):
        Template.objects.create(name="shared-name", language="es", submit_key=uuid.uuid7())
