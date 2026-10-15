"""Django admin of the printing app: every table with full CRUD for the platform's staff (round 12, PLAN
§17). Ids and dates are shown, never typed; the database still refuses what no door may save."""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.printing.models import Printer, PrintJob, Settings

MODELS = [Settings, Printer, PrintJob]
DATES = (
    "created_at",
    "updated_at",
    "last_printed_at",
    "last_failed_at",
    "sent_at",
    "printed_at",
    "failed_at",
    "retried_at",
    "cancelled_at",
)


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(username="root", password="pw", email="root@example.com")


def request_by(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_every_model_is_registered():
    for model in MODELS:
        assert model in admin.site._registry, model.__name__


def test_full_crud_for_the_staff(superuser):
    request = request_by(superuser)
    for model in MODELS:
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model.__name__
        assert model_admin.has_add_permission(request), model.__name__
        assert model_admin.has_change_permission(request), model.__name__
        assert model_admin.has_delete_permission(request), model.__name__


def test_ids_and_dates_are_read_only():
    for model in MODELS:
        readonly = set(admin.site._registry[model].readonly_fields)
        assert "id" in readonly, model.__name__
        for field in DATES:
            if any(f.name == field for f in model._meta.get_fields()):
                assert field in readonly, (model.__name__, field)


def test_the_queue_is_searched_by_document_and_filtered_by_state():
    job_admin = admin.site._registry[PrintJob]
    assert "reference" in job_admin.search_fields
    assert {"status", "usage", "kind"} <= set(job_admin.list_filter)


@pytest.mark.django_db
def test_the_admin_pages_open(client, superuser):
    client.force_login(superuser)
    for model in MODELS:
        url = f"/admin/printing/{model._meta.model_name}/"
        response = client.get(url, HTTP_HOST="hubs.localhost")
        assert response.status_code in (200, 302), (url, response.status_code)
