"""Django admin of Online orders: the tables' codes, for the platform's staff to look at.

A code is changed by regenerating it (its operation, with its event): the admin shows it and changes nothing.
"""

from django.contrib import admin
from django.test import RequestFactory

from apps.online_order.admin import TableCodeAdmin
from apps.online_order.models import TableCode


def test_the_codes_are_registered_and_read_only():
    registered = admin.site._registry[TableCode]
    assert isinstance(registered, TableCodeAdmin)
    assert registered.list_display == ("table_id", "code", "issued_at")
    request = RequestFactory().get("/admin/")
    assert registered.has_add_permission(request) is False
    assert registered.has_change_permission(request) is False
