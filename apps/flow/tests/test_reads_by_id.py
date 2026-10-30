"""FIX-HUB-FLOW-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS: one record of Automations by its id — a draft the assistant
proposed, a run of the History, a question waiting for an answer —, with the words its screen names it by. The
assistant's card names by them what a write of flow names by its id (an automation, by ``flow.flow.detail``), never by
the id; the API reads them too. Each is read with the permission of its list (a question, only by whom it was asked
of), and each is of the business that asks.
"""

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from live.errors import NotFound, PermissionDenied

from apps.flow.models import Draft, Flow, FlowRun, Question
from base.models import Membership
from base.tenancy import context
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

from .conftest import ctx_for, make_draft, make_flow, make_run, run

#: Thursday 15 October 2026 at 21:00 in Madrid, the business's clock in phase 1 (an instant: 19:00 UTC).
STARTED = dt.datetime(2026, 10, 15, 19, 0, tzinfo=dt.UTC)
#: …as each language writes a day and a time (the card's own CLDR words: a medium day and a short time).
WHEN = {"es": "15 oct 2026, 21:00", "en": "Oct 15, 2026, 9:00\u202fPM"}


def make_question(flow: Flow | None = None, *, role: str = "", status: str = Question.Status.PENDING, **fields):
    """A question an «Ask someone first» step asked (FLOW-F28), its run waiting for the answer."""
    flow = flow or make_flow("Refunds", trigger_kind=Flow.Trigger.MANUAL, steps=[{"id": "s1", "kind": "ask", "title": "x"}])
    asking = make_run(flow, status=FlowRun.Status.ASKING, started_at=STARTED)
    fields.setdefault("title", "Refund 15 € to Ana?")
    fields.setdefault("expires_at", STARTED + dt.timedelta(hours=72))
    return Question.objects.create(run=asking, flow=flow, step_id="s1", role=role, status=status, **fields)


# ── flow.draft.get ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_draft_is_read_by_its_id_with_its_name_whatever_was_decided_of_it():
    """As the drafts' tray names it; a draft already used or discarded is still read, with its status."""
    waiting = make_draft()
    dismissed = make_draft("Thank who paid", status=Draft.Status.DISMISSED)
    read = run("flow.draft.get", {"id": str(waiting.id)})
    assert (read.id, read.name, read.status) == (waiting.id, "Call who did not come", "pending")
    assert (run("flow.draft.get", {"id": str(dismissed.id)}).status) == "dismissed"


@pytest.mark.django_db
def test_a_missing_draft_is_not_found_as_discarding_it_says():
    with pytest.raises(NotFound) as caught:
        run("flow.draft.get", {"id": "0192f0b2-0000-7000-8000-000000000000"})
    assert caught.value.code == "not_found"


# ── flow.run.get ─────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_run_is_named_by_its_automation_and_when_it_started_as_the_history_says_it(language):
    """The History lists an automation's runs by when each started; out of it, the automation says whose."""
    ran = make_run(make_flow("Welcome"), status=FlowRun.Status.FAILED, started_at=STARTED)
    read = run("flow.run.get", {"id": str(ran.id)}, ctx_for(language=language))
    assert (read.id, read.status, read.label) == (ran.id, "failed", f"Welcome · {WHEN[language]}")


@pytest.mark.django_db
def test_a_missing_run_is_not_found_as_resuming_it_says():
    with pytest.raises(NotFound) as caught:
        run("flow.run.get", {"id": "0192f0b2-0000-7000-8000-000000000000"})
    assert caught.value.code == "not_found"


# ── flow.question.get ────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_question_waiting_for_an_answer_is_read_by_its_id_as_the_inbox_shows_it():
    asked = make_question(role="employee")
    read = run("flow.question.get", {"id": str(asked.id)}, ctx_for(permissions={"flow.answer"}))
    assert (read.id, read.title, read.flow_name, read.run_id) == (asked.id, "Refund 15 € to Ana?", "Refunds", asked.run_id)


@pytest.mark.django_db
def test_a_question_is_read_only_by_whom_it_was_asked_of_or_whoever_runs_the_business():
    """As «Waiting for your answer» shows it: an employee reads an employee's question, never a manager's; who manages
    reads them all."""
    of_a_manager = make_question(role="manager")
    with pytest.raises(PermissionDenied) as caught:
        run("flow.question.get", {"id": str(of_a_manager.id)}, ctx_for("hub_employee"))
    assert caught.value.code == "flow.question_not_yours"
    assert run("flow.question.get", {"id": str(of_a_manager.id)}, ctx_for("hub_manager")).id == of_a_manager.id
    assert run("flow.question.get", {"id": str(of_a_manager.id)}, ctx_for("hub_owner")).id == of_a_manager.id


@pytest.mark.django_db
@pytest.mark.parametrize("status", [Question.Status.APPROVED, Question.Status.EXPIRED, Question.Status.CANCELLED])
def test_a_question_no_longer_waiting_is_closed_and_a_missing_one_not_found(status):
    closed = make_question(status=status)
    with pytest.raises(NotFound) as caught:
        run("flow.question.get", {"id": str(closed.id)})
    assert caught.value.code == "flow.question_closed"
    with pytest.raises(NotFound) as caught:
        run("flow.question.get", {"id": "0192f0b2-0000-7000-8000-000000000000"})
    assert caught.value.code == "flow.question_not_found"


@pytest.mark.django_db
def test_a_question_whose_run_no_longer_waits_is_closed():
    """A run paused or cancelled while it waited leaves its question pending but nobody can answer it any more."""
    asked = make_question()
    FlowRun.objects.filter(pk=asked.run_id).update(status=FlowRun.Status.CANCELLED)
    with pytest.raises(NotFound) as caught:
        run("flow.question.get", {"id": str(asked.id)})
    assert caught.value.code == "flow.question_closed"


# ── Who reads them ───────────────────────────────────────────────────────────────────────────────

#: Each read by id, a record of it, and the permission of the list it comes from (the same screen shows it).
READS = [
    pytest.param("flow.draft.get", lambda: make_draft(), "flow.view", id="draft"),
    pytest.param("flow.run.get", lambda: make_run(make_flow()), "flow.view", id="run"),
    pytest.param("flow.question.get", lambda: make_question(role="employee"), "flow.answer", id="question"),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("name", "made", "permission"), READS)
def test_each_is_read_with_the_permission_of_its_list_and_only_with_it(name, made, permission):
    record = made()
    assert run(name, {"id": str(record.id)}, ctx_for(permissions={permission})).id == record.id
    other = {"flow.answer"} if permission == "flow.view" else {"flow.view"}
    with pytest.raises(PermissionDenied):
        run(name, {"id": str(record.id)}, ctx_for(permissions=other))


# ── Over HTTP, each of the business that asks ────────────────────────────────────────────────────

#: Each read's route, how a record of it is made and the datum that names it.
ROUTES = [
    pytest.param("/flow/flows/detail", lambda: make_flow(), "name", id="flow"),
    pytest.param("/flow/drafts/detail", lambda: make_draft(), "name", id="draft"),
    pytest.param("/flow/runs/detail", lambda: make_run(make_flow()), "label", id="run"),
    pytest.param("/flow/questions/detail", lambda: make_question(), "title", id="question"),
]


@pytest.fixture
def as_in_production(monkeypatch):
    """Every request opens its own database context, as in production (``base/tenancy/tests/conftest.py``)."""
    monkeypatch.setattr(context, "_test_fallback", None)
    cache.clear()
    yield
    cache.clear()


def signed_in(client, hub):
    user, _ = get_user_model().objects.get_or_create(username="saas:1", defaults={"first_name": "Olga"})
    Membership.objects.get_or_create(user=user, host=hub.slug, defaults={"role": "hub_admin"})
    client.force_login(user)
    return client


def read(client, hub, path: str, record_id) -> tuple[int, dict]:
    answer = client.get(f"/api{path}", {"id": str(record_id)}, HTTP_HOST=f"{hub.slug}.localhost:8000")
    return answer.status_code, answer.json()


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize(("path", "made", "named"), ROUTES)
def test_the_api_reads_one_of_this_business_by_its_id_with_what_names_it(client, hub_a, as_in_production, path, made, named):
    signed_in(client, hub_a)
    with use_hub(hub_a):
        record = made()
    status, body = read(client, hub_a, path, record.id)
    assert status == 200, body
    assert body["id"] == str(record.id) and body[named]


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize(("path", "made", "named"), ROUTES)
def test_another_businesss_record_is_not_there(client, hub_a, hub_b, as_in_production, path, made, named):
    with use_hub(hub_b):
        theirs = made()
    signed_in(client, hub_a)
    status, body = read(client, hub_a, path, theirs.id)
    # The code its writes answer too: «not_found» (an automation, a draft, a run), «flow.question_not_found».
    assert status == 404 and body["error"]["code"].endswith("not_found"), body
