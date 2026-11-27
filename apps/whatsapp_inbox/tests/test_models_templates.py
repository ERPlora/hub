"""The model of a WhatsApp template: its key, its defaults, one live template per name and language, one save per
key, and which templates the Hub can write and fill."""

import uuid

import pytest

from apps.whatsapp_inbox.models.templates import Template
from apps.whatsapp_inbox.tests.conftest import HUB_DB, NOW, violates

pytestmark = HUB_DB


def test_keys_are_uuid7():
    tpl = Template.objects.create(name="recordatorio", language="es")
    assert tpl.pk.version == 7


def test_defaults():
    tpl = Template.objects.create(name="recordatorio", language="es")
    assert (tpl.category, tpl.status, tpl.variables) == ("UTILITY", "APPROVED", 0)


def test_one_template_per_name_and_language():
    Template.objects.create(name="recordatorio", language="es")
    Template.objects.create(name="recordatorio", language="en")
    assert violates(
        "whatsapp_inbox_template_live_host_name_language_unique",
        lambda: Template.objects.create(name="recordatorio", language="es"),
    )


def test_a_template_deleted_here_frees_its_name_and_language():
    Template.objects.create(name="recordatorio", language="es", deleted_at=NOW, delete_state="done")
    Template.objects.create(name="recordatorio", language="es")
    assert Template.objects.filter(name="recordatorio", language="es").count() == 2


def test_one_save_of_a_template_per_key():
    key = uuid.uuid7()
    Template.objects.create(name="uno", language="es", submit_key=key)
    assert violates(
        "whatsapp_inbox_template_submit_key_unique",
        lambda: Template.objects.create(name="dos", language="es", submit_key=key),
    )


@pytest.mark.parametrize(
    ("fields", "handled"),
    [
        ({}, True),
        ({"header_format": "TEXT", "header": "Tu cita"}, True),
        ({"header_format": "TEXT", "header": "Hola {{1}}"}, False),
        ({"header_format": "IMAGE"}, True),  # sent with the file chosen (F33)
        ({"header_format": "LOCATION"}, False),
        ({"category": "AUTHENTICATION"}, False),
        ({"buttons": [{"type": "QUICK_REPLY", "text": "Sí"}, {"type": "URL", "text": "Web", "url": "https://p.test"}]}, True),
        ({"buttons": [{"type": "URL", "text": "Web", "url": "https://p.test/{{1}}"}]}, False),
        ({"buttons": [{"type": "COPY_CODE", "text": "Copiar"}]}, False),
    ],
)
def test_the_hub_handles_templates_it_can_write_and_fill(fields, handled):
    row = Template.objects.create(name="t", language="es", **fields)
    assert row.supported is handled
    assert Template.objects.get(pk=row.pk).supported is handled


def test_str():
    assert str(Template(name="recordatorio", language="es")) == "recordatorio (es)"
