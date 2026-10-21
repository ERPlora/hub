"""The «Call another system» step (WORKBOOK FLOW-F27; old hub HUB-F94, module flows-f16; hub#2659, hub#2675).

The other system is a real local HTTPS server (``local_https``). A step calls only an address whose origin
the owner granted (``http:https://host``); the request that parks the run answers at once, and the worker
makes the call (its relay hands it ``flow.run.parked``) after that COMMIT, outside any transaction, with an
``Idempotency-Key`` per run and step that every attempt repeats; the answer comes back in a
transaction of its own and the run goes on. Secrets go in the address, the headers or the body and come out
hidden everywhere. A call left half-way (the process died) is sent again, with the same key.
"""

import datetime as dt
import json
import uuid
from zoneinfo import ZoneInfo

import pydantic
import pytest
from cryptography.fernet import Fernet
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.context import system_context
from live.errors import InvalidPayload

from apps.flow import services, vault
from apps.flow.models import Flow, FlowRun, Question, Secret
from apps.task.models import Task
from base import relay

from .conftest import A, TASK_STEP, ctx_for, make_flow, run
from .local_https import Handler

pytestmark = pytest.mark.django_db

MADRID = ZoneInfo("Europe/Madrid")
NOON = dt.datetime(2026, 10, 15, 12, 0, tzinfo=MADRID)
SECRET = "sk_live_51HxYz"


@pytest.fixture(autouse=True)
def key(settings):
    settings.FLOW_SECRETS_KEY = Fernet.generate_key().decode()


def _call(origin: str, **more) -> dict:
    return {
        "id": "s1",
        "kind": "http",
        "method": "POST",
        "url": f"{origin}/orders?customer={{{{input.name}}}}",
        "headers": {"Authorization": "Bearer {{secret.STRIPE_KEY}}", "Content-Type": "application/json"},
        "body": '{"note": "{{input.note}}", "key": "{{run.idempotency_key}}"}',
        "timeout": 5,
    } | more


def _grant(origin: str) -> str:
    return f"http:{origin}"


def _manual(origin: str, steps, grants=None):
    Secret.objects.get_or_create(name="STRIPE_KEY", defaults={"ciphertext": vault.seal(SECRET)})
    return make_flow(
        trigger_kind=Flow.Trigger.MANUAL,
        steps=steps,
        grants=list(grants if grants is not None else [_grant(origin), "task.task.create"]),
    )


@pytest.fixture
def worker(monkeypatch, django_capture_on_commit_callbacks):
    """One pass of the outbox relay, as the worker runs it every tick (base.relay): what it hands over runs,
    and a call it schedules goes out after its COMMIT. Inside a test's transaction it keeps the connection."""
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)

    def tick():
        with django_capture_on_commit_callbacks(execute=True):
            return relay.run(timezone.now())

    def request(name, data, ctx=None):
        """Runs the operation ``name`` as a web request does, its COMMIT included: what it answers."""
        with django_capture_on_commit_callbacks(execute=True):
            return run(name, data, ctx)

    tick.request = request
    return tick


def test_run_now_answers_at_once_and_the_worker_makes_the_call(trusted, clock, worker):
    # «Run now» never waits for the other system (up to 30 s and a web thread): it parks the run and
    # answers; the worker makes the call on its next pass (Zapier, n8n, Power Automate).
    clock(NOON)
    flow = _manual(trusted, [_call(trusted), TASK_STEP | {"id": "s2"}])
    ran = worker.request("flow.flow.run", {"id": str(flow.id), "input": {"name": "Ana"}})
    assert ran.status == "calling"
    assert Handler.seen == []  # committed, and nothing went out from the request
    worker()
    assert len(Handler.seen) == 1
    assert FlowRun.objects.get(pk=ran.id).status == FlowRun.Status.SUCCEEDED
    assert Task.objects.count() == 1


def test_resuming_a_call_answers_at_once_and_the_worker_makes_it(trusted, clock, worker):
    clock(NOON)
    flow = _manual(trusted, [_call(trusted)])
    sealed = Secret.objects.get().ciphertext
    Secret.objects.all().delete()
    ran = worker.request("flow.flow.run", {"id": str(flow.id), "input": {}})
    worker()
    assert FlowRun.objects.get(pk=ran.id).error_code == "flow.secret_not_found"
    Secret.objects.create(name="STRIPE_KEY", ciphertext=sealed)
    resumed = worker.request("flow.run.retry", {"id": str(ran.id)})
    assert resumed.status == "calling"
    assert Handler.seen == []
    worker()
    assert len(Handler.seen) == 1
    assert FlowRun.objects.get(pk=ran.id).status == FlowRun.Status.SUCCEEDED


def test_a_yes_that_leads_to_a_call_answers_at_once_and_the_worker_makes_it(trusted, clock, worker):
    clock(NOON)
    ask = {"id": "s0", "kind": "ask", "title": "Send it?", "hours": 1}
    flow = _manual(trusted, [ask, _call(trusted)])
    ran = worker.request("flow.flow.run", {"id": str(flow.id), "input": {}})
    question = Question.objects.get(run_id=ran.id)
    answered = worker.request("flow.question.answer", {"id": str(question.id), "approve": True})
    assert answered.status == "calling"
    assert Handler.seen == []
    worker()
    assert len(Handler.seen) == 1
    assert FlowRun.objects.get(pk=ran.id).status == FlowRun.Status.SUCCEEDED


def test_the_worker_calls_only_for_a_run_parked_on_a_call(trusted, clock, worker):
    # `flow.run.parked` also parks a wait: its reaction has nothing to call there.
    clock(NOON)
    waiting = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[{"id": "s1", "kind": "delay", "seconds": 60}])
    parked = worker.request("flow.flow.run", {"id": str(waiting.id), "input": {}})
    system = ctx_for(permissions={"flow.system"})
    assert worker.request("flow.run.call", {"id": str(parked.id)}, system).count == 0
    calling = worker.request("flow.flow.run", {"id": str(_manual(trusted, [_call(trusted)]).id), "input": {}})
    assert worker.request("flow.run.call", {"id": str(calling.id)}, system).count == 1
    assert len(Handler.seen) == 1


def _run_now(flow, data, worker):
    """«Run now» (its COMMIT included), then the worker's pass that makes a call it parked."""
    ran = worker.request("flow.flow.run", {"id": str(flow.id), "input": data})
    worker()
    return ran, FlowRun.objects.get(pk=ran.id)


def test_a_granted_call_goes_out_after_the_commit_and_the_run_goes_on(trusted, clock, worker):
    clock(NOON)
    flow = _manual(trusted, [_call(trusted), TASK_STEP | {"id": "s2", "params": {"title": "Created {{steps.s1.body.ok}}"}}])
    ran, done = _run_now(flow, {"name": "Ana López", "note": 'He said "hi"'}, worker)
    assert ran.status == "calling"  # the step parked; the call left after the COMMIT
    assert done.status == FlowRun.Status.SUCCEEDED
    seen = Handler.seen[-1]
    assert (seen["method"], seen["path"]) == ("POST", "/orders?customer=Ana%20L%C3%B3pez")
    assert seen["headers"]["Authorization"] == f"Bearer {SECRET}"
    key = str(uuid.uuid5(services.IDEMPOTENCY_NAMESPACE, f"{done.id}:s1"))
    assert seen["headers"]["Idempotency-Key"] == key
    assert json.loads(seen["body"]) == {"note": 'He said "hi"', "key": key}  # JSON-escaped inside JSON
    assert Task.objects.get().title == "Created true"
    assert [entry["outcome"] for entry in done.log] == ["calling", "called", "done"]
    assert done.log[1]["status"] == 201 and done.log[1]["host"] == "localhost"
    assert SECRET not in json.dumps(done.log) and done.outputs == {}


def test_what_comes_back_hides_the_secrets(trusted, clock, worker):
    clock(NOON)
    flow = _manual(
        trusted,
        [_call(trusted, body="{{secret.STRIPE_KEY}}", headers={}), {"id": "s2", "kind": "delay", "seconds": 60}],
    )
    _, waiting = _run_now(flow, {}, worker)
    assert waiting.status == FlowRun.Status.WAITING
    assert waiting.outputs["s1"]["body"]["body"] == vault.MASK  # the server echoed it: hidden
    assert SECRET not in json.dumps(waiting.outputs)


def test_a_call_to_an_address_not_granted_never_goes_out(trusted, clock, worker):
    clock(NOON)
    flow = _manual(trusted, [_call(trusted)], grants=["task.task.create"])
    ran, failed = _run_now(flow, {}, worker)
    assert ran.status == "failed"  # refused before it even parks: «Run now» says so at once
    assert (failed.status, failed.error_code) == (FlowRun.Status.FAILED, "flow.not_allowed")
    assert Handler.seen == []


def test_an_answer_that_is_not_2xx_stops_the_run_or_carries_on(trusted, clock, worker):
    clock(NOON)
    flow = _manual(trusted, [_call(trusted, url=f"{trusted}/status/503")])
    _, failed = _run_now(flow, {}, worker)
    assert (failed.status, failed.error_code) == (FlowRun.Status.FAILED, "flow.http_status")
    assert "503" in failed.error_message
    carrying = _manual(
        trusted,
        [
            _call(trusted, url=f"{trusted}/status/503", on_error="continue"),
            TASK_STEP | {"id": "s2", "params": {"title": "It answered {{steps.s1.status}}"}},
        ],
    )
    _, done = _run_now(carrying, {}, worker)
    assert done.status == FlowRun.Status.SUCCEEDED
    assert Task.objects.get().title == "It answered 503"


def test_the_business_own_network_is_never_called(settings, server, clock, worker):
    clock(NOON)
    settings.FLOW_HTTP_CA_BUNDLE = server["ca"]
    settings.FLOW_HTTP_TRUSTED_ADDRESSES = []
    Handler.seen.clear()
    origin = f"https://localhost:{server['port']}"
    flow = _manual(origin, [_call(origin)])
    _, failed = _run_now(flow, {}, worker)
    assert (failed.status, failed.error_code) == (FlowRun.Status.FAILED, "flow.http_blocked")
    assert Handler.seen == []
    # FLOW-F24: resuming runs the same steps, so the same address would be blocked again: it is not offered.
    from apps.flow.queries import resume_problem

    assert resume_problem(failed, NOON)[0] == "flow.run_not_resumable"


def test_a_secret_deleted_fails_the_step_before_any_call(trusted, clock, worker):
    clock(NOON)
    flow = _manual(trusted, [_call(trusted)])
    Secret.objects.all().delete()
    _, failed = _run_now(flow, {}, worker)
    assert (failed.status, failed.error_code) == (FlowRun.Status.FAILED, "flow.secret_not_found")
    assert "STRIPE_KEY" in failed.error_message
    assert Handler.seen == []
    # Saving the secret again fixes it: that run can be resumed (FLOW-F24).
    from apps.flow.queries import resume_problem

    assert resume_problem(failed, NOON) is None


def test_without_the_servers_key_a_call_with_a_secret_fails_visibly(trusted, settings, clock, worker):
    clock(NOON)
    flow = _manual(trusted, [_call(trusted)])
    settings.FLOW_SECRETS_KEY = ""
    _, failed = _run_now(flow, {}, worker)
    assert (failed.status, failed.error_code) == (FlowRun.Status.FAILED, "flow.secrets_key_missing")
    assert Handler.seen == []


def test_without_the_servers_key_a_call_without_secrets_is_saved_tried_and_goes_out(
    trusted, settings, clock, worker
):
    # FLOW-F27 does not depend on FLOW-F26: a server without FLOW_SECRETS_KEY (prod until it is set) still
    # saves, tries and makes a call that names no secret; only a secret is refused.
    clock(NOON)
    settings.FLOW_SECRETS_KEY = ""
    plain = _call(trusted, headers={"Content-Type": "application/json"})
    assert run("flow.flow.create", {"steps": [plain]}).required_grants == [_grant(trusted)]
    flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=[plain, TASK_STEP | {"id": "s2"}], grants=[_grant(trusted), "task.task.create"])
    tried = run("flow.flow.test", {"id": str(flow.id), "document": json.dumps({"trigger": {"kind": "manual"}, "steps": flow.steps})})
    assert tried.steps[0].outcome == "would_call"
    _, done = _run_now(flow, {"name": "Ana", "note": "hi"}, worker)
    assert (done.status, done.error_code) == (FlowRun.Status.SUCCEEDED, "")
    seen = Handler.seen[-1]
    assert (seen["method"], seen["path"]) == ("POST", "/orders?customer=Ana")
    assert "Authorization" not in seen["headers"]
    assert seen["headers"]["Idempotency-Key"] == str(uuid.uuid5(services.IDEMPOTENCY_NAMESPACE, f"{done.id}:s1"))
    assert Task.objects.count() == 1
    assert run("flow.secret.list", {}).available is False


def test_a_call_left_half_way_is_sent_again_with_the_same_key(trusted, clock, django_capture_on_commit_callbacks):
    clock(NOON)
    flow = _manual(trusted, [_call(trusted)])
    with django_capture_on_commit_callbacks(execute=False):  # the process dies before the call
        ran = run("flow.flow.run", {"id": str(flow.id), "input": {}})
    system = ctx_for(permissions={"flow.system"})
    claimed = run("flow.run.claim_call", {"id": str(ran.id)}, system)
    assert claimed.claimed is True  # …and dies again during the call
    assert run("flow.run.claim_call", {"id": str(ran.id)}, system).claimed is False  # someone else holds it
    clock(NOON + dt.timedelta(minutes=services.CALL_LEASE_MINUTES, seconds=1))
    with django_capture_on_commit_callbacks(execute=True):
        run("flow.run.resume_due", {}, system)
    done = FlowRun.objects.get(pk=ran.id)
    assert done.status == FlowRun.Status.SUCCEEDED
    keys = [seen["headers"]["Idempotency-Key"] for seen in Handler.seen]
    assert keys == [str(uuid.uuid5(services.IDEMPOTENCY_NAMESPACE, f"{done.id}:s1"))]


def test_an_answer_that_comes_late_changes_nothing(trusted, clock, django_capture_on_commit_callbacks):
    clock(NOON)
    flow = _manual(trusted, [_call(trusted)])
    with django_capture_on_commit_callbacks(execute=False):
        ran = run("flow.flow.run", {"id": str(flow.id), "input": {}})
    run("flow.flow.delete", {"id": str(flow.id)})
    cancelled = FlowRun.objects.get(pk=ran.id)
    assert (cancelled.status, cancelled.error_code) == (FlowRun.Status.CANCELLED, "flow.deleted")
    system = ctx_for(permissions={"flow.system"})
    assert run("flow.run.claim_call", {"id": str(ran.id)}, system).claimed is False
    run("flow.run.record_call", {"id": str(ran.id), "kind": "ok", "status": 200, "body": {}}, system)
    assert FlowRun.objects.get(pk=ran.id).status == FlowRun.Status.CANCELLED


def test_its_own_idempotency_key_wins(trusted, clock, worker):
    clock(NOON)
    flow = _manual(trusted, [_call(trusted, headers={"Idempotency-Key": "mine-{{input.n}}"})])
    _run_now(flow, {"n": 7}, worker)
    assert Handler.seen[-1]["headers"]["Idempotency-Key"] == "mine-7"


# What is saved


def test_saving_asks_for_a_plain_https_address_written_by_hand():
    for url in (
        "http://api.example.com/x",
        "https://{{input.host}}/x",
        "https://api.example.com{{input.path}}",
        "https://user:pw@api.example.com/x",
        "ftp://api.example.com",
    ):
        with pytest.raises(pydantic.ValidationError):
            run("flow.flow.create", {"steps": [{"id": "s1", "kind": "http", "method": "GET", "url": url}]})
    created = run(
        "flow.flow.create",
        {"steps": [{"id": "s1", "kind": "http", "method": "GET", "url": "https://api.example.com/v1/{{input.id}}?q=1"}]},
    )
    assert created.required_grants == ["http:https://api.example.com"]


def test_a_secret_or_the_key_only_go_in_a_call_and_a_secret_must_exist():
    with pytest.raises(pydantic.ValidationError):
        run("flow.flow.create", {"steps": [TASK_STEP | {"params": {"title": "{{secret.STRIPE_KEY}}"}}]})
    with pytest.raises(pydantic.ValidationError):
        run("flow.flow.create", {"steps": [TASK_STEP | {"params": {"title": "{{run.idempotency_key}}"}}]})
    with pytest.raises(pydantic.ValidationError):
        run("flow.flow.create", {"steps": [_call("https://api.example.com", headers={"Authorization": "{{secret.lower}}"})]})
    with pytest.raises(InvalidPayload) as missing:
        run("flow.flow.create", {"steps": [_call("https://api.example.com")]})
    assert missing.value.fields == {"steps.0.headers": "There is no secret called «STRIPE_KEY»."}
    with pytest.raises(pydantic.ValidationError):  # its own Host is never sent
        run("flow.flow.create", {"steps": [_call("https://api.example.com", headers={"Host": "evil.example.com"})]})
    with pytest.raises(pydantic.ValidationError):
        run("flow.flow.create", {"steps": [_call("https://api.example.com", timeout=31)]})


def test_granting_a_call_names_its_origin():
    flow = make_flow(steps=[], grants=[])
    granted = run("flow.flow.grant", {"id": str(flow.id), "operations": ["http:https://api.example.com"]})
    assert granted.grants == ["http:https://api.example.com"]
    for bad in ("http:http://api.example.com", "http:https://api.example.com/path", "http:https://u@api.example.com"):
        with pytest.raises(InvalidPayload):
            run("flow.flow.grant", {"id": str(flow.id), "operations": [bad]})


def test_try_it_never_calls_and_never_shows_a_secret(trusted):
    flow = _manual(trusted, [_call(trusted)])
    tried = run(
        "flow.flow.test",
        {"id": str(flow.id), "document": json.dumps({"trigger": {"kind": "manual"}, "steps": flow.steps})},
    )
    step = tried.steps[0]
    assert step.outcome == "would_call"
    assert step.params["headers"]["Authorization"] == f"Bearer {vault.MASK}"
    assert SECRET not in tried.model_dump_json()
    assert Handler.seen == []
    ungranted = run(
        "flow.flow.test",
        {"document": json.dumps({"trigger": {"kind": "manual"}, "steps": flow.steps})},
    )
    assert ungranted.steps[0].outcome == "not_allowed"


def test_a_call_from_a_scheduled_run_goes_out_too(trusted, clock, worker, django_capture_on_commit_callbacks):
    clock(NOON)
    flow = _manual(trusted, [_call(trusted)])
    flow.trigger_kind = Flow.Trigger.AT
    flow.run_at = NOON
    flow.next_fire_at = NOON
    flow.save()
    with django_capture_on_commit_callbacks(execute=True):
        run("flow.schedule.fire_due", {}, system_context(A))
    assert Handler.seen == []  # the task parks it; the relay, in the same tick of the worker, makes it
    worker()
    assert FlowRun.objects.get().status == FlowRun.Status.SUCCEEDED
    assert len(Handler.seen) == 1


def test_a_header_with_a_datum_the_wire_cannot_carry_stops_the_run_visibly(trusted, clock, worker):
    # A customer's name with an accent in a header: the call cannot be sent. The run stops by an error that
    # says so (and can be resumed once the step is fixed); it never stays «calling» with its lease, to be
    # sent again every five minutes and crash the same way each time.
    clock(NOON)
    flow = _manual(trusted, [_call(trusted, headers={"X-Customer": "{{input.name}}"})])
    _, failed = _run_now(flow, {"name": "Ana López", "note": ""}, worker)
    assert (failed.status, failed.error_code) == (FlowRun.Status.FAILED, "flow.http_failed")
    assert "X-Customer" in failed.log[-1]["error"]["technical"]  # the technical text names the header
    assert Handler.seen == []
