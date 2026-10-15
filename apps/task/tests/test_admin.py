"""Django admin of the task app: full CRUD on every model, for the platform's staff.

Round 12 (PLAN §17, CLAUDE.md «Frontend y admin») gives the Hub admin full CRUD over all of a hub's
tables. A raw admin write records no event.
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.task.admin import CommentAdmin, CommentInline, ProjectAdmin, TaskAdmin, TaskCounterAdmin
from apps.task.models import Comment, Project, Task, TaskCounter

from .conftest import make_comment, make_member, make_project, make_task

MODELS = {
    Project: ProjectAdmin,
    Task: TaskAdmin,
    Comment: CommentAdmin,
    TaskCounter: TaskCounterAdmin,
}


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
    assert TaskAdmin.inlines == [CommentInline]


def test_full_crud_for_the_platform_staff(superuser):
    request = request_by(superuser)
    for model in MODELS:
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model
        assert model_admin.has_add_permission(request), model
        assert model_admin.has_change_permission(request), model
        assert model_admin.has_delete_permission(request), model


@pytest.mark.django_db
def test_a_project_is_added_and_changed_from_the_admin(client, superuser):
    client.force_login(superuser)
    added = client.post(
        "/admin/task/project/add/",
        {"code": "opening", "name": "Opening", "color": "", "is_active": "on"},
        HTTP_HOST="hubs.localhost",
    )
    assert added.status_code == 302, added.content[:500]
    project = Project.objects.get()
    changed = client.post(
        f"/admin/task/project/{project.pk}/change/",
        {"code": "opening", "name": "Grand opening", "color": "#AA3300"},
        HTTP_HOST="hubs.localhost",
    )
    assert changed.status_code == 302
    project.refresh_from_db()
    assert (project.name, project.color, project.is_active) == ("Grand opening", "#AA3300", False)


@pytest.mark.django_db
def test_the_pages_render_on_the_platform_host(client, superuser):
    project = make_project()
    task = make_task("Buy towels", project=project, assigned_to=make_member(), description="Private note")
    comment = make_comment(task, "Ordered")
    TaskCounter.objects.create(day="2026-10-14", last_number=3)
    client.force_login(superuser)
    for url, text in (
        ("/admin/task/task/add/", b"title"),
        ("/admin/task/task/", b"Buy towels"),
        (f"/admin/task/task/{task.pk}/change/", b"Private note"),
        ("/admin/task/project/", b"Opening"),
        (f"/admin/task/comment/{comment.pk}/change/", b"Ordered"),
        ("/admin/task/taskcounter/", b"20261014"),
    ):
        response = client.get(url, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200, url
        assert text in response.content, url
