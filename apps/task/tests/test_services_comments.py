"""Writes of a task's comments (TASK-F10): a comment is signed by whoever writes it."""

import pytest
from live.errors import NotFound

from apps.task.models import Comment
from base.models import HubUser, Membership

from .conftest import HUB_DB, A, ctx_for, make_task
from .test_services import as_employee, events, run

pytestmark = HUB_DB


def test_a_comment_is_signed_by_the_caller(team):
    task = make_task(assigned_to=team["worker_member"])
    comment = run("task.comment.add", {"task_id": str(task.id), "text": " On it "}, ctx=as_employee(team))
    assert (comment.text, comment.author_id, comment.author_name) == ("On it", team["worker"].person.pk, "Bea Ruiz")
    # What is kept, not only what the command answers: the thread is a record signed in the database.
    assert Comment.objects.get(pk=comment.id).author_id == team["worker"].person.pk
    assert events() == [("task.comment.added", {"id": str(comment.id), "task_id": str(task.id)})]


def test_a_comment_or_a_task_of_someone_the_business_s_database_does_not_know_yet_makes_their_person(
    team, django_user_model
):
    # A session opened before the business's database knew them: their first write signs with a person of its
    # own, and they own what they created.
    late = django_user_model.objects.create_user(username="saas:late", first_name="Eva")
    Membership.objects.create(user=late, host=A.key, role="hub_employee")
    ctx = ctx_for("hub_employee", actor=late)

    task = run("task.task.create", {"title": "Restock"}, ctx=ctx)
    comment = run("task.comment.add", {"task_id": str(task.id), "text": "Done"}, ctx=ctx)

    person = HubUser.objects.get(username="saas:late")
    assert (task.created_by_id, task.created_by_name, task.can_change) == (person.pk, "Eva", True)
    assert (comment.author_id, comment.author_name) == (person.pk, "Eva")


def test_an_employee_does_not_comment_someone_elses_task(team):
    task = make_task(assigned_to=team["ana"])
    with pytest.raises(NotFound):
        run("task.comment.add", {"task_id": str(task.id), "text": "x"}, ctx=as_employee(team))
