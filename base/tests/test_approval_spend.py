"""rv-hub-244 (BASE-F84, G136): the pass is spent in the same transaction as the command it lets through
(``base.approval_spend``, from ``LIVE["operation_database"]``), with its row locked: a command that fails for a reason of
the business leaves it unspent and the same request goes through with it after; one that went through cannot be
repeated; of two at once with the same pass, only one runs.
"""

import pytest

from base.models import Approval, Membership
from base.tests.test_approvals import (  # noqa: F401 — the fixtures of the approvals' tests
    APPROVABLE,
    CHANGE,
    SETTINGS,
    adam,
    approvable,
    code,
    eva,
    granted,
    post,
    with_pass,
)
from base.tests.test_people import with_pin

pytestmark = pytest.mark.django_db


def failing_once(monkeypatch, *, wait: float = 0.0) -> dict:
    """The approvable command fails once with a business refusal (a rollback) and then works; ``runs`` counts its calls.
    With ``wait``, each call holds its transaction open that long (two at once overlap)."""
    import threading
    import time

    from live.errors import Conflict
    from live.operations import get as get_operation

    op = get_operation(APPROVABLE)
    original = op.fn
    state = {"runs": 0, "fail": True, "entered": threading.Event()}

    def fn(ctx, data):
        state["runs"] += 1
        state["entered"].set()
        if wait:
            time.sleep(wait)
        if state["fail"]:
            state["fail"] = False
            raise Conflict("Not now.", code="base.test_not_now")
        return original(ctx, data)

    monkeypatch.setattr(op, "fn", fn)
    return state


class TestTheSpendIsTheCommands:
    """rv-hub-244: the pass is spent in the same transaction as the command it lets through, with its row locked: a
    command that fails for a reason of the business leaves it unspent; one that went through cannot be repeated."""

    def test_an_approved_command_that_fails_is_repeated_with_the_same_pass_and_goes_through(self, client, adam, eva, monkeypatch):
        token = granted(client)
        state = failing_once(monkeypatch)
        failed = post(client, SETTINGS, CHANGE, **with_pass(token))
        assert failed.status_code == 409, failed.content
        assert code(failed) == "base.test_not_now"
        assert Approval.objects.get().used_at is None
        again = post(client, SETTINGS, CHANGE, **with_pass(token))
        assert again.status_code == 200, again.content
        assert again.json()["pin_policy"] == "always"
        assert Approval.objects.get().used_at is not None
        assert state["runs"] == 2

    def test_one_that_went_through_is_never_repeated_with_it(self, client, adam, eva):
        token = granted(client)
        assert post(client, SETTINGS, CHANGE, **with_pass(token)).status_code == 200
        again = post(client, SETTINGS, CHANGE, **with_pass(token))
        assert again.status_code == 403
        assert code(again) == "requires_elevation"


@pytest.mark.django_db(transaction=True)
def test_two_at_once_with_the_same_pass_only_one_runs(make_user, monkeypatch):
    """rv-hub-244: the pass's row is locked in the command's transaction: the second waits, finds it spent and is
    refused; the command runs once."""
    import threading

    from django.db import connections
    from django.test import Client

    make_user("saas:2", host="a", role=Membership.Role.ADMIN, first_name="Adam")
    with_pin("saas:2", "2580")
    eva = make_user("saas:3", host="a", role=Membership.Role.EMPLOYEE, first_name="Eva")
    first, second = Client(), Client()
    first.force_login(eva)
    second.force_login(eva)
    token = granted(first)
    state = failing_once(monkeypatch, wait=1.0)
    state["fail"] = False
    answers: dict[str, object] = {}

    def run(name, client):
        try:
            answers[name] = post(client, SETTINGS, CHANGE, **with_pass(token))
        finally:
            connections.close_all()

    one = threading.Thread(target=run, args=("first", first))
    one.start()
    assert state["entered"].wait(10)
    two = threading.Thread(target=run, args=("second", second))
    two.start()
    one.join(20)
    two.join(20)
    statuses = sorted(answer.status_code for answer in answers.values())
    assert statuses == [200, 403], [answer.content for answer in answers.values()]
    assert code(next(a for a in answers.values() if a.status_code == 403)) == "requires_elevation"
    assert state["runs"] == 1



def test_the_spend_opens_the_transaction_on_the_alias_the_tenancy_gave_never_one_of_its_own(monkeypatch):
    """rv-hub-244 (ronda 2): ``spending`` never chooses a database: the transaction it opens is on the alias the tenancy
    handed the command (phase 2, S5: the hub's own), so the pass and the command share one transaction there too.
    In the shared mode every alias is ``default`` and no request can tell; this pins the contract."""
    from contextlib import contextmanager
    from types import SimpleNamespace

    from live.operations import get as get_operation

    from base import approval_spend
    from base.approvals import Approved

    opened: list[str] = []

    @contextmanager
    def atomic(using=None, **_kwargs):
        opened.append(using)
        yield

    monkeypatch.setattr(approval_spend.transaction, "atomic", atomic)
    monkeypatch.setattr(approval_spend, "get", lambda name: lambda ctx, data: SimpleNamespace(spent=True))
    op = get_operation(APPROVABLE)
    request = SimpleNamespace(approved=Approved(operation=APPROVABLE, permission=op.permission, token="elev_x", fingerprint="f"))
    with approval_spend.spending(op, SimpleNamespace(request=request), "hub_0123") as alias:
        assert alias == "hub_0123"
    assert opened == ["hub_0123"]
