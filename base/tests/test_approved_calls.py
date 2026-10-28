"""BASE-F84: what a command a manager approved asks of another app goes with it (hub#250).

A command let through with a manager's pass may run, on the way, a command of another app (Sales' void: the rectifying
invoice of Invoicing, the voucher's sessions Services gives back). That one goes with the approval, as when the manager
does it themselves: the platform gives it its permission (``base.approvals.consequence_context``), and an app calls
another's operation through ``base.operations.call``, never with its own copy. Only while the approved command runs, in
that very request, and only for a command of another app with a permission: a read never, a command of the approved
command's own app never, the next request never, the assistant outside the approved command never; without an approval,
the caller's own permissions decide. The pass is still spent once, in the approved command's transaction, and its
fingerprint is that of the request.
"""

import contextlib
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.core.cache import cache
from live.context import OperationContext, Scope
from live.errors import AppInactive, Conflict, InvalidPayload, PermissionDenied
from live.operations import UnknownOperation, current_operation
from live.operations import get as get_operation

from apps.demo.models import Item
from base.approvals import Approved, approval_of, consequence_context
from base.models import Approval, Membership
from base.operations import call
from base.tests.test_approvals import APPROVABLE, CHANGE, SETTINGS, approve, code, post, with_pass
from base.tests.test_people import with_pin

pytestmark = pytest.mark.django_db

A = Scope("host", "a")
#: A command of another app (demo) that the employee may not run, and a read of that app with the very same permission.
OTHER_COMMAND = "demo.item.create"
OTHER_READ = "demo.item.stats"
OTHER_PERMISSION = "demo.manage"
#: A command of the approved command's own app (base) that the employee may not run either, with another permission.
OWN_COMMAND = "base.file.delete"


@pytest.fixture(autouse=True)
def approvable(monkeypatch):
    """``base`` names one of its commands as approvable, as an app would in its ``LiveAppConfig``."""
    monkeypatch.setattr(apps.get_app_config("base"), "approvals", {APPROVABLE: "Change how the till asks who is there"}, raising=False)
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def adam(make_user):
    user = make_user("saas:2", host="a", role=Membership.Role.ADMIN, first_name="Adam")
    with_pin("saas:2", "2580")
    return user


@pytest.fixture
def eva(make_user, client):
    user = make_user("saas:3", host="a", role=Membership.Role.EMPLOYEE, first_name="Eva")
    client.force_login(user)
    return user


@pytest.fixture
def on_the_way(monkeypatch):
    """The approvable command also runs ``name`` of another app with ``data`` once its own work is done, through
    ``base.operations.call``, as Sales' void runs Invoicing's rectifying invoice."""

    def runs(name: str, data: dict) -> None:
        op = get_operation(APPROVABLE)
        own = op.fn

        def fn(ctx, data_in):
            result = own(ctx, data_in)
            call(ctx, name, data)
            return result

        monkeypatch.setattr(op, "fn", fn)

    return runs


def asked(client) -> dict:
    response = post(client, SETTINGS, CHANGE)
    assert response.status_code == 403, response.content
    assert code(response) == "requires_elevation"
    return response.json()["error"]["approval"]


def granted(client) -> tuple[dict, str]:
    question = asked(client)
    response = approve(client, question, "saas:2")
    assert response.status_code == 200, response.content
    return question, response.json()["token"]


# ── Through the door: the employee's request, approved by the manager's PIN ──────────────────────────────────────────


class TestTheApprovedCommandsConsequences:
    def test_a_command_of_another_app_it_runs_goes_with_the_approval(self, client, adam, eva, on_the_way):
        on_the_way(OTHER_COMMAND, {"name": "Given back with the approval"})
        question, token = granted(client)
        response = post(client, SETTINGS, CHANGE, **with_pass(token))
        assert response.status_code == 200, response.content
        assert list(Item.objects.values_list("name", flat=True)) == ["Given back with the approval"]
        spent = Approval.objects.get()
        assert spent.used_at is not None
        assert spent.fingerprint == question["fingerprint"]

    def test_the_pass_is_spent_once_with_what_went_with_it(self, client, adam, eva, on_the_way):
        on_the_way(OTHER_COMMAND, {"name": "Once"})
        _question, token = granted(client)
        assert post(client, SETTINGS, CHANGE, **with_pass(token)).status_code == 200
        again = post(client, SETTINGS, CHANGE, **with_pass(token))
        assert code(again) == "requires_elevation"
        assert Item.objects.count() == 1

    def test_a_read_of_another_app_is_never_opened(self, client, adam, eva, on_the_way):
        """``demo.item.stats`` asks the very permission ``demo.item.create`` gets: a read still never has it."""
        on_the_way(OTHER_READ, {})
        _question, token = granted(client)
        response = post(client, SETTINGS, CHANGE, **with_pass(token))
        assert response.status_code == 403, response.content
        assert code(response) == "permission_denied"
        # The command failed: its pass is left unspent, as always.
        assert Approval.objects.get().used_at is None

    def test_a_command_of_the_approved_commands_own_app_is_not_opened(self, client, adam, eva, on_the_way):
        on_the_way(OWN_COMMAND, {"path": "Invoices/2025"})
        _question, token = granted(client)
        response = post(client, SETTINGS, CHANGE, **with_pass(token))
        assert response.status_code == 403, response.content
        assert code(response) == "permission_denied"

    def test_the_next_request_holds_only_the_callers_own(self, client, adam, eva, on_the_way):
        on_the_way(OTHER_COMMAND, {"name": "With the approval"})
        _question, token = granted(client)
        assert post(client, SETTINGS, CHANGE, **with_pass(token)).status_code == 200
        response = post(client, "/demo/items", {"name": "Alone"})
        assert response.status_code == 403, response.content
        assert code(response) == "permission_denied"
        assert list(Item.objects.values_list("name", flat=True)) == ["With the approval"]


# ── The rule, on its own: which context a command of another app runs with ────────────────────────────────────────────


def context(*, approved: object = None, permissions: frozenset[str] = frozenset()) -> OperationContext:
    """An employee's context on hub ``a``; ``approved`` is the mark of its request (none: no request at all)."""
    request = SimpleNamespace(approved=approved) if approved is not None else None
    return OperationContext(scope=A, actor="eva", permissions=permissions, request=request)


def mark(operation: str = APPROVABLE) -> Approved:
    return Approved(operation=operation, permission=get_operation(operation).permission or "", token="elev_x", fingerprint="f" * 64)


@contextlib.contextmanager
def running(name: str | None):
    """As while the operation ``name`` runs (live's ``current_operation``); ``None``: outside any."""
    token = current_operation.set(get_operation(name) if name else None)
    try:
        yield
    finally:
        current_operation.reset(token)


class TestWhatGoesWithIt:
    def test_a_command_of_another_app_the_approved_command_runs_gets_its_permission(self):
        ctx = context(approved=mark(), permissions=frozenset({"demo.view"}))
        with running(APPROVABLE):
            returned = consequence_context(ctx, get_operation(OTHER_COMMAND))
        assert returned.has(OTHER_PERMISSION)
        assert returned.permissions == frozenset({"demo.view", OTHER_PERMISSION})
        assert returned.request is ctx.request and returned.actor == ctx.actor and returned.scope == ctx.scope

    def test_a_read_never(self):
        ctx = context(approved=mark())
        with running(APPROVABLE):
            assert consequence_context(ctx, get_operation(OTHER_READ)) is ctx

    def test_who_already_may_keeps_their_context(self):
        ctx = context(approved=mark(), permissions=frozenset({OTHER_PERMISSION}))
        with running(APPROVABLE):
            assert consequence_context(ctx, get_operation(OTHER_COMMAND)) is ctx

    def test_without_an_approval_the_callers_own(self):
        ctx = context()
        with running(APPROVABLE):
            assert consequence_context(ctx, get_operation(OTHER_COMMAND)) is ctx

    def test_a_mark_that_is_no_managers_approval_opens_nothing(self):
        ctx = context(approved={"operation": APPROVABLE, "permission": OTHER_PERMISSION})
        with running(APPROVABLE):
            assert consequence_context(ctx, get_operation(OTHER_COMMAND)) is ctx

    def test_only_while_the_approved_command_runs(self):
        """The assistant marks its turn's request and runs other tools in it: only the approved one carries."""
        ctx = context(approved=mark())
        with running("base.assistant.turn"):
            assert consequence_context(ctx, get_operation(OTHER_COMMAND)) is ctx
        with running(None):
            assert consequence_context(ctx, get_operation(OTHER_COMMAND)) is ctx

    def test_never_a_command_of_the_approved_commands_own_app(self):
        ctx = context(approved=mark())
        with running(APPROVABLE):
            assert consequence_context(ctx, get_operation(OWN_COMMAND)) is ctx

    def test_a_command_without_a_permission_has_nothing_to_add(self):
        ctx = context(approved=mark())
        no_permission = SimpleNamespace(kind="command", permission=None, app_label="demo", name="demo.item.open")
        with running(APPROVABLE):
            assert consequence_context(ctx, no_permission) is ctx

    def test_approval_of_reads_the_requests_mark(self):
        approved = mark()
        assert approval_of(context(approved=approved)) is approved
        assert approval_of(context()) is None
        assert approval_of(context(approved=True)) is None


# ── The one way an app calls another's operation ─────────────────────────────────────────────────────────────────────


class TestCall:
    UNAVAILABLE = Conflict("Demo is not available.", code="base.test_unavailable")

    def test_it_runs_the_operation_with_the_callers_context(self):
        ctx = context(permissions=frozenset({OTHER_PERMISSION}))
        created = call(ctx, OTHER_COMMAND, {"name": "Called"})
        assert created.name == "Called"
        assert Item.objects.get().name == "Called"

    def test_without_an_approval_the_other_apps_command_refuses_the_caller(self):
        ctx = context(permissions=frozenset({"demo.view"}))
        with running(APPROVABLE), pytest.raises(PermissionDenied):
            call(ctx, OTHER_COMMAND, {"name": "Refused"})
        assert not Item.objects.exists()

    def test_inside_the_approved_command_the_other_apps_command_goes_with_it(self):
        ctx = context(approved=mark(), permissions=frozenset({"demo.view"}))
        with running(APPROVABLE):
            call(ctx, OTHER_COMMAND, {"name": "Approved"})
        assert Item.objects.get().name == "Approved"

    def test_inside_the_approved_command_a_read_still_refuses(self):
        ctx = context(approved=mark(), permissions=frozenset({"demo.view"}))
        with running(APPROVABLE), pytest.raises(PermissionDenied):
            call(ctx, OTHER_READ, {})

    def test_an_input_the_other_app_does_not_take_is_the_callers_422(self):
        ctx = context(permissions=frozenset({OTHER_PERMISSION}))
        with pytest.raises(InvalidPayload) as refused:
            call(ctx, OTHER_COMMAND, {})
        assert refused.value.status == 422
        assert "name" in refused.value.fields

    def test_an_app_that_does_not_exist_is_the_callers_unavailable(self):
        ctx = context(permissions=frozenset({OTHER_PERMISSION}))
        with pytest.raises(Conflict) as refused:
            call(ctx, "nowhere.thing.do", {}, unavailable=self.UNAVAILABLE)
        assert refused.value is self.UNAVAILABLE
        with pytest.raises(UnknownOperation):
            call(ctx, "nowhere.thing.do", {})

    def test_an_app_turned_off_is_the_callers_unavailable(self, monkeypatch):
        from base import activation

        monkeypatch.setattr(activation, "off_apps", lambda scope: frozenset({"demo"}))
        ctx = context(permissions=frozenset({OTHER_PERMISSION}))
        with pytest.raises(Conflict) as refused:
            call(ctx, OTHER_COMMAND, {"name": "Off"}, unavailable=self.UNAVAILABLE)
        assert refused.value is self.UNAVAILABLE
        with pytest.raises(AppInactive):
            call(ctx, OTHER_COMMAND, {"name": "Off"})
