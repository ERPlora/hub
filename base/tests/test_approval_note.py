"""An action a manager may approve, done by somebody who may do it themselves, is on the record too (BASE-F85).

It is written in the transaction of the action, with who did it, when, what and its figures, with no pass and nobody who
approved it. What was refused, what was undone, what changed nothing, what a pass let through (it is on the record
already) and what the platform does by itself are not written.
"""

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from live.context import OperationContext, system_context
from live.errors import Conflict
from live.models import OutboxEvent
from live.operations import get as get_operation

from base import approval_note
from base.api_keys import KeyCaller
from base.models import Membership
from base.models.access import AccessSettings
from base.models.approvals import Approval
from base.permissions import ADMINISTER_HUB, VIEW_HOME, access_for
from base.roles import APPROVAL, OFF, ON
from base.tenancy.context import use_hub
from base.tenancy.tests.business import A, B, HUB_DB, in_business_a
from base.tests import card_turn
from base.tests.test_approval_spend import failing_once
from base.tests.test_approval_states import B_HOST, given
from base.tests.test_approvals import (
    APPROVABLE,
    CHANGE,
    FIGURED,
    SETTINGS,
    THIRTY,
    adam,
    approvable,
    code,
    declare,
    eva,
    get,
    granted,
    mario,
    post,
    refused,
    with_pass,
)

__all__ = ["adam", "approvable", "eva", "in_business_a", "mario"]

pytestmark = HUB_DB

ADD_LINE = "demo.item.add_line"
MAY = frozenset({ADMINISTER_HUB, VIEW_HOME})


def changed() -> bool:
    return AccessSettings.objects.filter(pin_policy="always").exists()


def noted_events() -> list[dict]:
    return list(OutboxEvent.objects.filter(name="base.approval.noted").values_list("payload", flat=True))


@pytest.fixture
def olga(make_user):
    return make_user("saas:1", host=A.key, role=Membership.Role.OWNER, first_name="Olga")


class TestWhoMayDoIt:
    def test_leaves_who_did_it_what_and_when_with_no_pass_and_nobody_who_approved(self, client, adam):
        client.force_login(adam)

        assert post(client, SETTINGS, CHANGE).status_code == 200

        row = Approval.objects.get()
        assert (row.operation, row.permission, row.way) == (APPROVABLE, ADMINISTER_HUB, "role")
        assert (row.requested_by, row.requested_by_name) == ("saas:2", "Adam")
        assert (row.approved_by, row.approved_by_name) == ("", "")
        assert (row.token_digest, row.fingerprint, row.expires_at) == (None, "", None)
        assert row.used_at is not None
        assert row.figures is None
        assert noted_events() == [{"id": str(row.pk), "operation": APPROVABLE}]

    def test_leaves_its_figures_those_its_sentences_name_and_no_others(self, client, adam, monkeypatch):
        declare(monkeypatch, FIGURED)
        client.force_login(adam)

        assert post(client, SETTINGS, THIRTY).status_code == 200

        assert Approval.objects.get().figures == {"pin_inactivity_minutes": 30, "pin_length": None}

    def test_is_also_the_owner(self, client, olga):
        client.force_login(olga)

        assert post(client, SETTINGS, CHANGE).status_code == 200

        assert Approval.objects.get().requested_by_name == "Olga"

    def test_is_also_whoever_a_role_of_the_business_allows_it(self, client, eva):
        given(eva, ON)

        assert post(client, SETTINGS, CHANGE).status_code == 200

        row = Approval.objects.get()
        assert (row.requested_by_name, row.way) == ("Eva", "role")

    def test_leaves_one_row_each_time(self, client, adam):
        client.force_login(adam)
        for _ in range(2):
            assert post(client, SETTINGS, CHANGE).status_code == 200

        assert Approval.objects.count() == 2

    def test_leaves_no_pass_anybody_could_spend(self, client, adam, eva):
        client.force_login(adam)
        post(client, SETTINGS, CHANGE)
        client.force_login(eva)

        assert code(post(client, SETTINGS, CHANGE, **with_pass("elev_"))) == "requires_elevation"
        assert Approval.objects.count() == 1

    def test_is_read_by_the_name_of_my_profile_and_never_an_address(self, client, make_user):
        boss = make_user("saas:7", host=A.key, role=Membership.Role.ADMIN, first_name="", email="boss@example.com")
        client.force_login(boss)

        post(client, SETTINGS, CHANGE)

        # With no name anywhere, what goes before the «@»: never the address, nor the account's internal id.
        assert Approval.objects.get().requested_by_name == "boss"


class TestWhatIsNotDone:
    def test_a_refusal_leaves_nothing(self, client, adam, eva):
        refused(client)
        given(eva, OFF)
        assert code(post(client, SETTINGS, CHANGE)) == "permission_denied"

        assert not Approval.objects.exists()
        assert noted_events() == []

    def test_an_action_that_fails_leaves_nothing(self, client, adam, monkeypatch):
        client.force_login(adam)
        failing_once(monkeypatch)
        assert post(client, SETTINGS, CHANGE).status_code == 409
        assert not Approval.objects.exists()

        assert post(client, SETTINGS, CHANGE).status_code == 200
        assert Approval.objects.count() == 1

    def test_the_action_and_its_row_are_undone_together(self, client, adam, monkeypatch):
        noted = approval_note.note_own_right

        def noted_and_undone(*args) -> None:
            noted(*args)
            assert Approval.objects.exists()
            raise Conflict("Not now.", code="base.test_not_now")

        monkeypatch.setattr(approval_note, "note_own_right", noted_and_undone)
        client.force_login(adam)

        assert code(post(client, SETTINGS, CHANGE)) == "base.test_not_now"

        assert not Approval.objects.exists()
        assert noted_events() == []
        assert not changed()

    def test_an_action_that_changed_nothing_leaves_nothing(self, client, adam, monkeypatch):
        """The answer given again to a request repeated with its key, or an edit that edits nothing: no event."""
        monkeypatch.setattr(get_operation(APPROVABLE), "fn", lambda ctx, data: {**CHANGE, "can_change": True})
        client.force_login(adam)

        assert post(client, SETTINGS, CHANGE).status_code == 200

        assert not Approval.objects.exists()

    def test_a_command_no_app_names_and_a_read_leave_nothing(self, client, adam):
        client.force_login(adam)
        assert post(client, "/demo/items", {"name": "Mesa 4"}).status_code == 201
        assert get(client, "/devices").status_code == 200

        assert not Approval.objects.exists()


class TestWhatAPassLetsThrough:
    def test_is_on_the_record_once_with_who_approved_it(self, client, adam, eva):
        assert post(client, SETTINGS, CHANGE, **with_pass(granted(client))).status_code == 200

        row = Approval.objects.get()
        assert (row.way, row.approved_by_name, row.requested_by_name) == ("pin", "Adam", "Eva")
        assert noted_events() == []

    def test_is_on_the_record_once_for_a_role_that_leaves_it_to_approval(self, client, adam, eva):
        given(eva, APPROVAL)

        assert post(client, SETTINGS, CHANGE, **with_pass(granted(client))).status_code == 200

        assert Approval.objects.get().way == "pin"

    def test_what_it_asks_of_another_app_on_the_way_is_not_on_it_apart(self, client, adam, eva, monkeypatch):
        from base.operations import call

        monkeypatch.setattr(apps.get_app_config("demo"), "approvals", {"demo.item.create": "Make an item"}, raising=False)
        op = get_operation(APPROVABLE)
        own = op.fn

        def and_an_item(ctx, data):
            result = own(ctx, data)
            call(ctx, "demo.item.create", {"name": "Given back"})
            return result

        monkeypatch.setattr(op, "fn", and_an_item)

        assert post(client, SETTINGS, CHANGE, **with_pass(granted(client))).status_code == 200

        assert Approval.objects.get().operation == APPROVABLE


def run(ctx: OperationContext) -> None:
    op = get_operation(APPROVABLE)
    op(ctx, op.input.model_validate(CHANGE))


class TestWhoActs:
    def test_the_platform_leaves_nothing(self):
        run(system_context(A))

        assert changed()
        assert not Approval.objects.exists()

    def test_an_automation_leaves_nothing(self):
        """It keeps its own runs; the permission is the one it was granted, not somebody's."""
        run(OperationContext(scope=A, actor="flow_run:0190a1b2", permissions=MAY))

        assert changed()
        assert not Approval.objects.exists()

    def test_an_api_key_leaves_its_name(self):
        key = KeyCaller(key_id="k1", name="Shop", prefix="erpk_live_x", permissions=MAY, owner="saas:1")

        run(OperationContext(scope=A, actor=key, permissions=key.permissions))

        row = Approval.objects.get()
        assert (row.requested_by, row.requested_by_name, row.way) == ("API · Shop", "API · Shop", "role")

    def test_the_assistant_leaves_the_person_who_said_yes_and_only_then(self, make_user):
        mario = make_user("saas:4", host=A.key, role=Membership.Role.MANAGER, first_name="Mario")
        item = get_operation("demo.item.create")
        created = item(asking(mario), item.input.model_validate({"name": "Mesa 4"}))
        call = card_turn.call(ADD_LINE, {"id": str(created.id), "text": "Coffee", "qty": 2})

        drawn = card_turn.turn(asking(mario), call, said="add 2 coffees")
        assert not Approval.objects.exists()
        decision = {"call_id": "c1", "accepted": True, "typed": "CONFIRM"}
        card_turn.turn(asking(mario), drawn["pending"][0], said="add 2 coffees", decision=decision)

        row = Approval.objects.get()
        assert (row.operation, row.requested_by_name, row.way) == (ADD_LINE, "Mario", "role")
        assert row.figures == {"qty": "2", "text": "Coffee"}

    def test_a_business_never_reads_what_was_done_in_another(self, client, hub_b):
        bea = get_user_model().objects.create(username="saas:21", first_name="Bea")
        for slug in (A.key, B.key):
            Membership.objects.create(user=bea, host=slug, role=Membership.Role.ADMIN)
        client.force_login(bea)

        assert post(client, SETTINGS, CHANGE).status_code == 200

        assert [row["requested_by"] for row in get(client, "/approvals").json()["approvals"]] == ["Bea"]
        assert get(client, "/approvals", host=B_HOST).json()["approvals"] == []
        with use_hub(hub_b):
            assert not Approval.objects.exists()


def asking(user) -> OperationContext:
    return OperationContext(scope=A, actor=user, permissions=access_for(user, A), language="en")
