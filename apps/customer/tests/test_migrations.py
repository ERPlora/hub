"""Migration 0004 of the customer app: every card that exists gets its search text without the email and the phone.

The function of the ``RunPython`` is called the way the migration runs it, with the app registry and a schema editor
whose connection is business A's own database, inside the test's transaction.
"""

from importlib import import_module

from django.apps import apps as global_apps
from django.db import connections

from apps.customer.models import Customer
from base.tenancy.context import current_alias

from .conftest import HUB_DB

pytestmark = HUB_DB

MIGRATION = import_module("apps.customer.migrations.0004_search_text_without_contact")


class _SchemaEditor:
    @property
    def connection(self):
        return connections[current_alias()]


def test_the_cards_that_exist_get_their_search_text_without_contact():
    ana = Customer.objects.create(name="Ana García", email="ana@example.com", phone="+34600111222", tax_id="12345678Z")
    bea = Customer.objects.create(name="Bea Núñez", company_name="Peluquería Sol", deleted_at="2026-11-01T10:00Z")
    Customer.objects.update(search_text_without_contact="")
    MIGRATION.forwards(global_apps, _SchemaEditor())
    assert {card.name: card.search_text_without_contact for card in Customer.objects.filter(pk__in=[ana.pk, bea.pk])} == {
        "Ana García": "ana garcia 12345678z",
        "Bea Núñez": "bea nunez peluqueria sol",
    }


def test_it_touches_only_that_text():
    ana = Customer.objects.create(name="Ana García", email="ana@example.com", phone="+34600111222")
    Customer.objects.update(search_text_without_contact="")
    MIGRATION.forwards(global_apps, _SchemaEditor())
    ana.refresh_from_db()
    assert (ana.name, ana.email, ana.phone, ana.search_text) == (
        "Ana García", "ana@example.com", "+34600111222", "ana garcia ana@example.com +34600111222"
    )
