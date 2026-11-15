"""Django admin of the flow app: full CRUD on every model, for the platform's staff.

The Hub admin has full CRUD over all of a hub's tables. A raw admin write records no event.
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.flow.admin import DraftAdmin, FlowAdmin, FlowRunAdmin, FlowRunInline, QuestionAdmin
from apps.flow.models import Draft, Flow, FlowRun, Question
from base.tenancy.tests.concurrency import PLATFORM_HOST

from .conftest import HUB_DB, make_draft, make_flow, make_run

MODELS = {Flow: FlowAdmin, FlowRun: FlowRunAdmin, Draft: DraftAdmin, Question: QuestionAdmin}


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


@HUB_DB
def test_full_crud_for_the_platform_staff(superuser):
    request = request_by(superuser)
    for model in MODELS:
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model
        assert model_admin.has_add_permission(request), model
        assert model_admin.has_change_permission(request), model
        assert model_admin.has_delete_permission(request), model


@HUB_DB
def test_the_lists_and_change_pages_open(hub_staff):
    flow = make_flow("Welcome")
    run_ = make_run(flow)
    draft = make_draft()
    for path in (
        "/admin/flow/flow/",
        f"/admin/flow/flow/{flow.pk}/change/",
        "/admin/flow/flowrun/",
        f"/admin/flow/flowrun/{run_.pk}/change/",
        "/admin/flow/draft/",
        f"/admin/flow/draft/{draft.pk}/change/",
    ):
        response = hub_staff.get(path, HTTP_HOST=PLATFORM_HOST)
        assert response.status_code == 200, (path, response.status_code)


@HUB_DB
def test_an_automation_is_renamed_from_the_admin(hub_staff):
    flow = make_flow("Welcome")
    page = hub_staff.get(f"/admin/flow/flow/{flow.pk}/change/", HTTP_HOST=PLATFORM_HOST)
    form = page.context["adminform"].form
    data = {name: form[name].value() for name in form.fields}
    data = {key: ("" if value is None else value) for key, value in data.items()}
    data.update({"name": "Hello", "enabled": "on"})
    for key in ("trigger_filter", "schedule", "steps", "grants"):
        data[key] = form[key].value()
    for prefix in ("runs",):
        data.update({f"{prefix}-TOTAL_FORMS": "0", f"{prefix}-INITIAL_FORMS": "0"})
    changed = hub_staff.post(f"/admin/flow/flow/{flow.pk}/change/", data, HTTP_HOST=PLATFORM_HOST)
    assert changed.status_code == 302, changed.content[:1000]
    assert Flow.objects.get(pk=flow.pk).name == "Hello"


@HUB_DB
def test_the_recipe_an_automation_comes_from_is_seen_in_the_admin(hub_staff):
    # FLOW-F33: staff can tell an app's ready-made automation from the owner's own, and from which version.
    flow = make_flow("Gap", recipe="appointment/customer_cancelled", recipe_digest="a" * 64)
    form = hub_staff.get(f"/admin/flow/flow/{flow.pk}/change/", HTTP_HOST=PLATFORM_HOST).context["adminform"].form
    assert (form["recipe"].value(), form["recipe_digest"].value()) == ("appointment/customer_cancelled", "a" * 64)


# FLOW-F26: a secret is sealed with the server's key; the admin sees its name and may delete it, never its
# value, and cannot write one (it would not be sealed).
@HUB_DB
def test_a_secret_shows_only_its_name_and_can_only_be_deleted(hub_staff):
    from apps.flow.admin import SecretAdmin
    from apps.flow.models import Secret

    secret = Secret.objects.create(name="STRIPE_KEY", ciphertext="gAAAA-sealed")
    model_admin = admin.site._registry[Secret]
    assert isinstance(model_admin, SecretAdmin)
    request = request_by(get_user_model().objects.get())  # the platform staff, the only person
    assert model_admin.has_view_permission(request) and model_admin.has_delete_permission(request)
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    page = hub_staff.get(f"/admin/flow/secret/{secret.pk}/change/", HTTP_HOST=PLATFORM_HOST)
    assert page.status_code == 200
    assert b"STRIPE_KEY" in page.content and b"gAAAA-sealed" not in page.content


# FLOW-F28: a question is a row of the business like any other; the staff sees and fixes it from the admin.


@HUB_DB
def test_a_question_opens_in_the_admin(hub_staff):
    flow = make_flow("Refunds")
    run_ = make_run(flow, status="asking")
    question = Question.objects.create(run=run_, flow=flow, step_id="s1", title="Refund?", expires_at=run_.started_at)
    for path in ("/admin/flow/question/", f"/admin/flow/question/{question.pk}/change/"):
        assert hub_staff.get(path, HTTP_HOST=PLATFORM_HOST).status_code == 200, path
