"""The task app's models: defaults, the constraints the database keeps, and what a deletion takes
with it (WORKBOOK «Para quien lo mantiene»)."""

import datetime as dt
import uuid

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.task.models import Comment, Project, Task, TaskCounter

from .conftest import make_comment, make_member, make_project, make_task

pytestmark = pytest.mark.django_db


def test_keys_are_uuid7():
    task = make_task()
    assert isinstance(task.pk, uuid.UUID) and task.pk.version == 7


def test_a_task_is_born_to_do_with_medium_priority_and_no_completion():
    task = make_task()
    assert (task.status, task.priority, task.completed_at, task.tags) == ("todo", "medium", None, [])
    assert task.description == ""
    assert str(task) == f"{task.number} — Clean the store room"


def test_the_five_statuses_and_four_priorities_of_the_old_module():
    assert Task.Status.values == ["todo", "in_progress", "blocked", "done", "cancelled"]
    assert Task.Priority.values == ["low", "medium", "high", "urgent"]


def test_a_number_is_unique():
    make_task(number="TSK-20261014-0001")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_task(number="TSK-20261014-0001")


def test_done_and_a_completion_date_go_together():
    now = timezone.now()
    make_task(status="done", completed_at=now)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_task(status="done", completed_at=None)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_task(status="cancelled", completed_at=now)


def test_a_task_is_not_its_own_parent():
    task = make_task()
    task.parent = task
    with pytest.raises(IntegrityError), transaction.atomic():
        task.save()


def test_deleting_a_parent_takes_its_subtasks_and_their_comments():
    parent = make_task("Opening prep")
    child = make_task("Buy towels", parent=parent)
    grandchild = make_task("Pick the colour", parent=child)
    make_comment(grandchild)
    parent.delete()
    assert not Task.objects.filter(pk__in=[child.pk, grandchild.pk]).exists()
    assert not Comment.objects.exists()


def test_deleting_a_project_keeps_its_tasks():
    project = make_project()
    task = make_task(project=project)
    project.delete()
    task.refresh_from_db()
    assert task.project is None


def test_an_assignee_record_deleted_from_the_admin_leaves_the_task_unassigned():
    member = make_member()
    task = make_task(assigned_to=member)
    member.delete()
    task.refresh_from_db()
    assert task.assigned_to is None


def test_a_project_code_is_unique_whatever_the_case():
    make_project(code="Q3-Audit")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_project(code="q3-audit", name="Other")


def test_a_project_is_born_active_without_colour():
    project = make_project()
    assert (project.is_active, project.color, project.owner) == (True, "", None)
    assert str(project) == "Opening"


def test_one_counter_per_day():
    TaskCounter.objects.create(day=dt.date(2026, 10, 14))
    with pytest.raises(IntegrityError), transaction.atomic():
        TaskCounter.objects.create(day=dt.date(2026, 10, 14))


def test_a_comment_belongs_to_its_task():
    comment = make_comment(make_task(), "Done tomorrow")
    assert str(comment) == "Done tomorrow"
    assert Project._meta.verbose_name == "project"
