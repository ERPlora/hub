"""The reaction to Staff (TASK-F15): a person who leaves the team leaves their open tasks without an assignee."""

import pytest
from django.utils import timezone
from live.errors import PermissionDenied

from apps.task.models import Task

from .conftest import HUB_DB, ctx_for, make_task
from .test_services import events, run

pytestmark = HUB_DB


def test_releasing_a_member_unassigns_their_open_tasks_only(team):
    from live.context import system_context

    from .conftest import A

    ana = team["ana"]
    open_one = make_task("Open", assigned_to=ana)
    blocked = make_task("Blocked", assigned_to=ana, status="blocked")
    done = make_task("Done", assigned_to=ana, status="done", completed_at=timezone.now())
    result = run("task.task.release_member", {"id": str(ana.id)}, ctx=system_context(A))
    assert result.released == 2
    assert Task.objects.get(pk=open_one.pk).assigned_to is None
    assert Task.objects.get(pk=blocked.pk).assigned_to is None
    assert Task.objects.get(pk=done.pk).assigned_to_id == ana.id
    assert sorted(payload["id"] for _, payload in events("task.task.assigned")) == sorted(
        [str(open_one.id), str(blocked.id)]
    )


def test_no_person_reaches_the_reaction(team):
    with pytest.raises(PermissionDenied):
        run("task.task.release_member", {"id": str(team["ana"].id)}, ctx=ctx_for("hub_owner"))
