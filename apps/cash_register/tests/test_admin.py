"""Django admin of the cash register app: every table with full CRUD for the platform's staff (round 12,
PLAN §17). Ids and dates are shown, never typed; the database still refuses what no door may save."""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.cash_register import admin as cash_admin
from apps.cash_register.models import (
    Count,
    Movement,
    Register,
    Session,
    SessionCounter,
    Settings,
)

MODELS = [Settings, Register, Session, SessionCounter, Movement, Count]
DATES = ("created_at", "updated_at", "opened_at", "closed_at", "counted_at")


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(
        username="root", password="pw", email="root@example.com"
    )


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


def test_a_session_shows_its_movements_and_counts():
    assert admin.site._registry[Session].inlines == [
        cash_admin.MovementInline,
        cash_admin.CountInline,
    ]
