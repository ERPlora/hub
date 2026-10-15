"""Django admin of the flow app: full CRUD on every model, for the platform's staff.

Round 12 (PLAN §17, CLAUDE.md «Frontend y admin») gives the Hub admin full CRUD over all of a hub's
tables. A raw admin write records no event.
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.flow.admin import DraftAdmin, FlowAdmin, FlowRunAdmin, FlowRunInline
from apps.flow.models import Draft, Flow, FlowRun

from .conftest import make_draft, make_flow, make_run

MODELS = {Flow: FlowAdmin, FlowRun: FlowRunAdmin, Draft: DraftAdmin}


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(username="root", password="pw", email="root@example.com")


def request_by(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_every_model_is_registered():
    for model, model_admin in MODELS.items():
        assert isinstance(admin.site._registry[model], model_admin), model
    assert FlowAdmin.inlines == [FlowRunInline]


def test_full_crud_for_the_platform_staff(superuser):
    request = request_by(superuser)
    for model in MODELS:
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model
        assert model_admin.has_add_permission(request), model
        assert model_admin.has_change_permission(request), model
        assert model_admin.has_delete_permission(request), model


@pytest.mark.django_db
def test_the_lists_and_change_pages_open(client, superuser):
    flow = make_flow("Welcome")
    run_ = make_run(flow)
    draft = make_draft()
    client.force_login(superuser)
    for path in (
        "/admin/flow/flow/",
        f"/admin/flow/flow/{flow.pk}/change/",
        "/admin/flow/flowrun/",
        f"/admin/flow/flowrun/{run_.pk}/change/",
        "/admin/flow/draft/",
        f"/admin/flow/draft/{draft.pk}/change/",
    ):
        response = client.get(path, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200, (path, response.status_code)


@pytest.mark.django_db
def test_an_automation_is_renamed_from_the_admin(client, superuser):
    flow = make_flow("Welcome")
    client.force_login(superuser)
    page = client.get(f"/admin/flow/flow/{flow.pk}/change/", HTTP_HOST="hubs.localhost")
    form = page.context["adminform"].form
    data = {name: form[name].value() for name in form.fields}
    data = {key: ("" if value is None else value) for key, value in data.items()}
    data.update({"name": "Hello", "enabled": "on"})
    for key in ("trigger_filter", "schedule", "steps", "grants"):
        data[key] = form[key].value()
    for prefix in ("runs",):
        data.update({f"{prefix}-TOTAL_FORMS": "0", f"{prefix}-INITIAL_FORMS": "0"})
    changed = client.post(f"/admin/flow/flow/{flow.pk}/change/", data, HTTP_HOST="hubs.localhost")
    assert changed.status_code == 302, changed.content[:1000]
    assert Flow.objects.get(pk=flow.pk).name == "Hello"
