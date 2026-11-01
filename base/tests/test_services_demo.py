"""The demo hubs (plan 2026-10-17, §1.5–§1.7; round 2026-10-30 of PLAN-DB, S2a): an empty hub with a database of its
own for one browser of the SaaS, entered with a one-time code, dropped and purged by the worker once its hour is up.

``base.demo.create`` (``POST /internal/demos``) gives a browser, named by the sha256 of its SaaS token, its live demo
or a new ``demo-<8 hex>`` up to ``MAX_CONCURRENT_DEMOS``, ``requested`` until the worker makes its database
(``base/tenancy/tests/test_provision.py``; here :func:`ready` stands in for it); ``base.demo.code_create`` (``POST …/{slug}/codes``) a code
of a minute for the browser that owns it, which the demo's ``/auth/callback`` redeems here (``redeem_demo_code``) and
turns into a session as ``demo:<slug>``, the owner (``open_demo_session``). ``base.demo.expire`` ends one now; the
reaper (``reap_demos``) purges those that ended and, after ``DEMO_TOMBSTONE_DAYS``, forgets them.
"""

import contextlib
import datetime as dt
import hashlib
import logging
import re
import threading
import uuid

import pydantic
import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.utils import timezone
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, NotFound, OperationError, PermissionDenied
from live.models import OutboxEvent

from base import registry, services
from base.models import DemoCode, Hub, Membership
from base.tenancy import names, ops, provision
from base.tenancy.connections import control_name
from control.models import HubDue
from base.queries import demo_get
from base.schemas import DemoCodeIn, DemoCreateIn, DemoSlugIn
from base.services import (
    InactiveUser,
    demo_code_create,
    demo_create,
    demo_expire,
    demo_purge,
    open_demo_session,
    purge_demo_data,
    reap_demo_tombstones,
    reap_demos,
    redeem_demo_code,
)

pytestmark = pytest.mark.django_db

SYSTEM = system_context(registry.REGISTRY_SCOPE)
ANA = hashlib.sha256(b"ana's browser").hexdigest()
BEA = hashlib.sha256(b"bea's browser").hexdigest()
CARLA = hashlib.sha256(b"carla's browser").hexdigest()
MINUTE = dt.timedelta(minutes=1)


def create(session_key: str = ANA, **changes):
    return demo_create(SYSTEM, DemoCreateIn(session_key=session_key, **changes))


def ready(answer):
    """The worker made the demo's database (``base.tenancy.provision``): it is ready."""
    Hub.objects.filter(slug=answer.slug).update(status="ready", ready_at=timezone.now())
    return answer


def code_for(slug: str, session_key: str = ANA, language: str = "en"):
    return demo_code_create(SYSTEM, DemoCodeIn(slug=slug, session_key=session_key, language=language))


def lapse(slug: str) -> None:
    """The demo's hour ran out a minute ago, and the reaper has not come yet."""
    Hub.objects.filter(slug=slug).update(expires_at=timezone.now() - MINUTE)


def events(name: str) -> list[dict]:
    return list(OutboxEvent.objects.filter(name=name).values_list("payload", flat=True))


def a_user_context(**fields) -> OperationContext:
    user = get_user_model().objects.create_user(username="ana", password="pw", **fields)
    return OperationContext(scope=registry.REGISTRY_SCOPE, actor=user, permissions=frozenset({"*"}))


def a_request(rf):
    request = rf.post("/auth/callback")
    SessionMiddleware(lambda request: None).process_request(request)
    return request


def entered(rf, slug: str, session_key: str = ANA):
    """The demo ``slug`` as its browser leaves it once inside: a code spent and the owner's session open."""
    Hub.objects.filter(slug=slug).update(status="ready")
    redeemed = redeem_demo_code(slug, code_for(slug, session_key).code)
    open_demo_session(a_request(rf), redeemed.hub)
    return redeemed


class TestCreate:
    def test_a_new_demo_is_requested_with_a_database_of_its_own_to_make_for_an_hour(self, settings):
        settings.DEMO_TTL_MINUTES = 60
        before = timezone.now()
        answer = create(vertical="restaurant", language="es")
        after = timezone.now()
        assert (answer.created, answer.status) == (True, "requested")
        assert re.fullmatch(r"demo-[0-9a-f]{8}", answer.slug)
        hub = Hub.objects.get(slug=answer.slug)
        assert (hub.id, hub.is_demo, hub.status, hub.vertical, hub.language, hub.demo_session_key) == (
            answer.id,
            True,
            "requested",
            "restaurant",
            "es",
            ANA,
        )
        assert before + 60 * MINUTE <= hub.expires_at <= after + 60 * MINUTE
        assert answer.expires_at == hub.expires_at and hub.ready_at is None
        # Its own database, never control's (round 2026-10-30, decision 1), made by the worker it is due in.
        assert hub.db_name == names.demo_db_name(control_name(), hub.id)
        assert HubDue.objects.get(pk=hub.pk).lease_until is None
        assert events("base.demo.created") == [{"id": str(hub.id), "slug": hub.slug, "vertical": "restaurant"}]

    def test_its_hour_is_the_setting_s(self, settings):
        settings.DEMO_TTL_MINUTES = 15
        answer = create()
        assert 14 * MINUTE < answer.expires_at - timezone.now() <= 15 * MINUTE

    def test_the_same_browser_gets_its_live_demo_again_and_no_new_one(self):
        first = create()
        again = create()
        assert (again.created, again.id, again.slug, again.expires_at) == (False, first.id, first.slug, first.expires_at)
        assert Hub.objects.filter(is_demo=True).count() == 1
        assert len(events("base.demo.created")) == 1

    @pytest.mark.parametrize("status", ["requested", "creating", "migrating", "seeding", "ready"])
    def test_a_demo_still_being_made_is_the_browsers_live_one_too(self, status):
        first = create()
        Hub.objects.filter(slug=first.slug).update(status=status)
        again = create()
        assert (again.created, again.slug, again.status) == (False, first.slug, status)

    def test_a_demo_whose_preparation_failed_is_no_live_one_the_browser_gets_another(self):
        failed = create()
        Hub.objects.filter(slug=failed.slug).update(status="failed", attempts=1)
        HubDue.objects.filter(pk=failed.id).delete()
        again = create()
        assert again.created and again.slug != failed.slug and again.status == "requested"
        # The failed one ends: its database (if any) is dropped by the reaper, as a demo that ran out.
        assert Hub.objects.get(slug=failed.slug).status == "expired"
        assert HubDue.objects.filter(pk=failed.id).exists()

    def test_a_failed_demo_of_another_browser_never_takes_a_place_under_the_cap(self, settings):
        settings.MAX_CONCURRENT_DEMOS = 1
        Hub.objects.filter(slug=create(ANA).slug).update(status="failed")
        assert create(BEA).created

    def test_demos_still_being_made_count_against_the_cap(self, settings):
        settings.MAX_CONCURRENT_DEMOS = 1
        create(ANA)
        with pytest.raises(OperationError) as full:
            create(BEA)
        assert full.value.code == "base.demo_full"

    def test_another_browser_gets_another_demo(self):
        assert create(ANA).slug != create(BEA).slug

    def test_a_browser_whose_demo_ran_out_gets_a_new_one_and_the_old_one_waits_for_the_reaper(self):
        first = create()
        lapse(first.slug)
        again = create()
        assert again.created and again.slug != first.slug
        assert Hub.objects.get(slug=first.slug).status == "expired"

    def test_the_cap_of_live_demos_is_a_503_demo_full(self, settings):
        settings.MAX_CONCURRENT_DEMOS = 2
        create(ANA)
        create(BEA)
        with pytest.raises(OperationError) as full:
            create(CARLA)
        assert (full.value.status, full.value.code) == (503, "base.demo_full")
        assert Hub.objects.filter(is_demo=True).count() == 2

    def test_a_browser_with_its_demo_is_answered_even_at_the_cap(self, settings):
        settings.MAX_CONCURRENT_DEMOS = 1
        first = create(ANA)
        assert create(ANA).slug == first.slug

    def test_demos_that_ran_out_and_businesses_never_count_against_the_cap(self, settings):
        settings.MAX_CONCURRENT_DEMOS = 1
        lapse(create(ANA).slug)
        # ``a`` and ``b`` (conftest) are ready hubs too, and no demos.
        assert create(BEA).created

    def test_two_calls_of_one_browser_at_once_end_in_one_demo(self, monkeypatch):
        # The second call did not see the first one's demo yet; the unique constraint catches it.
        first = create()
        real, looks = services._live_demo_of, []

        def late(session_key, now):
            looks.append(session_key)
            return None if len(looks) == 1 else real(session_key, now)

        monkeypatch.setattr(services, "_live_demo_of", late)
        again = create()
        assert (again.created, again.slug) == (False, first.slug)
        assert Hub.objects.filter(is_demo=True).count() == 1

    def test_an_address_already_taken_is_drawn_again(self, monkeypatch):
        Hub.objects.create(slug="demo-0000beef", is_demo=True, status="purged")
        draws = iter(["0000beef", "0000cafe"])
        monkeypatch.setattr(services.secrets, "token_hex", lambda nbytes: next(draws))
        assert create().slug == "demo-0000cafe"

    def test_no_free_address_after_a_few_draws_is_a_503(self, monkeypatch):
        Hub.objects.create(slug="demo-0000beef", is_demo=True, status="purged")
        monkeypatch.setattr(services.secrets, "token_hex", lambda nbytes: "0000beef")
        with pytest.raises(OperationError) as refused:
            create()
        assert (refused.value.status, refused.value.code) == (503, "base.demo_unavailable")

    def test_only_the_platform_creates_one(self):
        with pytest.raises(PermissionDenied) as refused:
            demo_create(a_user_context(), DemoCreateIn(session_key=ANA))
        assert refused.value.code == "base.internal_only"
        assert not Hub.objects.filter(is_demo=True).exists()

    @pytest.mark.parametrize("session_key", ["", "k" * 64, ANA.upper(), ANA[:-1], ANA + "0"])
    def test_the_browser_is_named_by_a_sha256_in_hex(self, session_key):
        with pytest.raises(pydantic.ValidationError):
            DemoCreateIn(session_key=session_key)


class TestCreateAtOnce:
    """Two browsers asking for the last free demo at the same instant, each in its own session and transaction."""

    @pytest.mark.django_db(transaction=True)
    def test_two_browsers_at_once_never_pass_the_cap(self, settings, monkeypatch, transactional_db):
        # Each call stops between counting the live demos and drawing its address until the other one gets there
        # too (or two seconds pass): without a lock both count none and both make one; with it the second one
        # counts only after the first has committed, and is told the demos are full.
        settings.MAX_CONCURRENT_DEMOS = 1
        draw, both_counted = services.secrets.token_hex, threading.Barrier(2)

        def counted_then_draw(nbytes):
            with contextlib.suppress(threading.BrokenBarrierError):
                both_counted.wait(2)
            return draw(nbytes)

        monkeypatch.setattr(services.secrets, "token_hex", counted_then_draw)
        results = at_once(lambda: create(ANA), lambda: create(BEA))
        assert sorted(getattr(result, "code", "created") for result in results) == ["base.demo_full", "created"]
        assert Hub.objects.filter(is_demo=True).count() == 1


def at_once(*calls):
    """Runs every ``call`` in its own thread (its own connection), released together; their results or errors."""
    start = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def run(index, call):
        try:
            start.wait(5)
            results[index] = call()
        except Exception as error:  # the test reads the error, an unexpected one included
            results[index] = error
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(index, call)) for index, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


class TestCodeCreate:
    def test_a_demo_being_made_gives_no_code_yet(self):
        demo = create()
        with pytest.raises(OperationError) as preparing:
            code_for(demo.slug)
        assert (preparing.value.status, preparing.value.code) == (503, "base.hub_preparing")
        assert not DemoCode.objects.exists()

    def test_another_browser_never_learns_a_demo_is_being_made(self):
        demo = create(ANA)
        with pytest.raises(PermissionDenied):
            code_for(demo.slug, BEA)

    def test_the_owner_gets_a_one_time_code_of_a_minute_kept_by_its_hash(self):
        demo = ready(create())
        before = timezone.now()
        answer = code_for(demo.slug, language="es")
        after = timezone.now()
        assert len(answer.code) >= 43
        [row] = DemoCode.objects.all()
        assert row.code_hash == hashlib.sha256(answer.code.encode()).hexdigest()
        assert (row.hub.slug, row.language, row.used_at, row.expires_at) == (demo.slug, "es", None, answer.expires_at)
        assert before + MINUTE <= answer.expires_at <= after + MINUTE
        # The code itself is in no event.
        assert events("base.demo.code_created") == [{"slug": demo.slug}]

    def test_every_code_is_another(self):
        demo = ready(create())
        assert code_for(demo.slug).code != code_for(demo.slug).code
        assert DemoCode.objects.count() == 2

    def test_another_browser_is_refused_with_403(self):
        demo = create(ANA)
        with pytest.raises(PermissionDenied) as refused:
            code_for(demo.slug, BEA)
        assert (refused.value.status, refused.value.code) == (403, "base.demo_not_owner")
        assert not DemoCode.objects.exists()

    def test_a_demo_that_ran_out_is_410_hub_gone(self):
        demo = create()
        lapse(demo.slug)
        with pytest.raises(OperationError) as gone:
            code_for(demo.slug)
        assert (gone.value.status, gone.value.code) == (410, "base.hub_gone")

    def test_a_purged_demo_is_410_too(self):
        Hub.objects.create(slug="demo-0000beef", is_demo=True, status="purged", demo_session_key=ANA)
        with pytest.raises(OperationError) as gone:
            code_for("demo-0000beef")
        assert gone.value.status == 410

    @pytest.mark.parametrize("slug", ["demo-00000000", "a"])
    def test_a_slug_that_names_no_demo_is_404(self, slug):
        with pytest.raises(NotFound):
            code_for(slug)

    def test_only_the_platform_asks_for_one(self):
        demo = create()
        with pytest.raises(PermissionDenied) as refused:
            demo_code_create(a_user_context(), DemoCodeIn(slug=demo.slug, session_key=ANA))
        assert refused.value.code == "base.internal_only"


class TestRedeem:
    def test_a_code_opens_once(self):
        demo = ready(create())
        code = code_for(demo.slug).code
        redeemed = redeem_demo_code(demo.slug, code)
        assert redeemed.hub.slug == demo.slug and redeemed.used_at is not None
        assert DemoCode.objects.get().used_at is not None
        assert redeem_demo_code(demo.slug, code) is None

    def test_a_code_past_its_minute_is_refused(self):
        demo = ready(create())
        code = code_for(demo.slug).code
        assert redeem_demo_code(demo.slug, code, now=timezone.now() + dt.timedelta(seconds=61)) is None
        assert DemoCode.objects.get().used_at is None

    def test_a_code_of_another_demo_is_refused_and_stays_unspent(self):
        mine, other = ready(create(ANA)), ready(create(BEA))
        code = code_for(mine.slug).code
        assert redeem_demo_code(other.slug, code) is None
        assert redeem_demo_code(mine.slug, code) is not None

    def test_a_code_of_a_demo_that_ran_out_is_refused(self):
        demo = ready(create())
        code = code_for(demo.slug).code
        lapse(demo.slug)
        assert redeem_demo_code(demo.slug, code) is None

    @pytest.mark.parametrize("code", [None, "", "   ", "not-a-code"])
    def test_no_code_or_an_unknown_one_is_refused(self, code):
        demo = ready(create())
        code_for(demo.slug)
        assert redeem_demo_code(demo.slug, code) is None


class TestOpenSession:
    def test_opens_a_session_as_the_demo_s_owner_never_staff(self, rf):
        hub = Hub.objects.get(slug=create().slug)
        request = a_request(rf)
        user = open_demo_session(request, hub)
        assert (user.username, user.first_name, user.is_staff, user.is_superuser, user.has_usable_password()) == (
            f"demo:{hub.slug}",
            "Demo",
            False,
            False,
            False,
        )
        assert list(Membership.objects.filter(user=user).values_list("host", "role")) == [(hub.slug, "hub_owner")]
        assert request.session["_auth_user_id"] == str(user.pk)
        assert request.session["demo_slug"] == hub.slug

    def test_entering_again_keeps_one_user_and_one_role(self, rf):
        hub = Hub.objects.get(slug=create().slug)
        first = open_demo_session(a_request(rf), hub)
        again = open_demo_session(a_request(rf), hub)
        assert first.pk == again.pk
        assert Membership.objects.filter(host=hub.slug).count() == 1

    def test_a_demo_user_raised_to_staff_by_hand_is_lowered_again(self, rf):
        hub = Hub.objects.get(slug=create().slug)
        user = open_demo_session(a_request(rf), hub)
        get_user_model().objects.filter(pk=user.pk).update(is_staff=True, is_superuser=True, first_name="Root")
        user = open_demo_session(a_request(rf), hub)
        assert (user.is_staff, user.is_superuser, user.first_name) == (False, False, "Demo")

    def test_a_demo_user_deactivated_in_the_admin_is_refused(self, rf):
        hub = Hub.objects.get(slug=create().slug)
        user = open_demo_session(a_request(rf), hub)
        get_user_model().objects.filter(pk=user.pk).update(is_active=False)
        request = a_request(rf)
        with pytest.raises(InactiveUser):
            open_demo_session(request, hub)
        assert "_auth_user_id" not in request.session


class TestExpire:
    def test_ends_the_demo_now_and_its_host_is_gone(self):
        demo = create()
        answer = demo_expire(SYSTEM, DemoSlugIn(slug=demo.slug))
        hub = Hub.objects.get(slug=demo.slug)
        assert (answer.slug, answer.status, hub.status) == (demo.slug, "expired", "expired")
        assert hub.expires_at <= timezone.now() and registry.is_gone(hub)
        assert events("base.demo.expired") == [{"id": str(hub.id), "slug": demo.slug}]

    def test_its_browser_may_start_another_one(self):
        demo = create()
        demo_expire(SYSTEM, DemoSlugIn(slug=demo.slug))
        assert create().slug != demo.slug

    def test_a_demo_that_ended_stays_as_it_is(self):
        demo = create()
        demo_expire(SYSTEM, DemoSlugIn(slug=demo.slug))
        ended_at = Hub.objects.get(slug=demo.slug).expires_at
        demo_expire(SYSTEM, DemoSlugIn(slug=demo.slug))
        assert Hub.objects.get(slug=demo.slug).expires_at == ended_at
        assert len(events("base.demo.expired")) == 1

    @pytest.mark.parametrize("slug", ["demo-00000000", "a"])
    def test_a_slug_that_names_no_demo_is_404(self, slug):
        with pytest.raises(NotFound):
            demo_expire(SYSTEM, DemoSlugIn(slug=slug))
        assert Hub.objects.get(slug="a").status == "ready"

    def test_the_platform_s_admins_may_end_one_from_the_hub_admin(self):
        demo = create()
        staff = a_user_context(is_staff=True, is_superuser=True)
        assert demo_expire(staff, DemoSlugIn(slug=demo.slug)).status == "expired"

    @pytest.mark.parametrize("host", ["a", "demo"])
    def test_staff_acting_on_a_business_s_scope_never_ends_one(self, host):
        """Review of hub#490: ERPlora's staff passes only on the platform's scope (the Hub admin, REGISTRY_SCOPE); on a
        business's host, its own or the demo's, it is no more than anyone there."""
        demo = create()
        user = get_user_model().objects.create_user(username="ana", password="pw", is_staff=True, is_superuser=True)
        Membership.objects.create(user=user, host="a", role=Membership.Role.ADMIN)
        scope = Scope("host", demo.slug if host == "demo" else host)
        with pytest.raises(PermissionDenied) as refused:
            demo_expire(OperationContext(scope=scope, actor=user, permissions=frozenset({"*"})), DemoSlugIn(slug=demo.slug))
        assert refused.value.code == "base.internal_only"
        assert Hub.objects.get(slug=demo.slug).status == "requested"

    @pytest.mark.parametrize("fields", [{}, {"is_staff": True}, {"is_superuser": True}])
    def test_nobody_else_ends_one(self, fields):
        demo = create()
        with pytest.raises(PermissionDenied) as refused:
            demo_expire(a_user_context(**fields), DemoSlugIn(slug=demo.slug))
        assert refused.value.code == "base.internal_only"
        assert Hub.objects.get(slug=demo.slug).status == "requested"

    @pytest.mark.parametrize("status", ["requested", "creating", "failed", "ready"])
    def test_a_demo_still_being_made_is_ended_too_and_due_to_be_dropped(self, status):
        demo = create()
        Hub.objects.filter(slug=demo.slug).update(status=status)
        HubDue.objects.filter(pk=demo.id).delete()
        assert demo_expire(SYSTEM, DemoSlugIn(slug=demo.slug)).status == "expired"
        assert HubDue.objects.filter(pk=demo.id).exists()


class TestGet:
    def test_answers_a_demo_s_status(self):
        demo = ready(create())
        answer = demo_get(SYSTEM, DemoSlugIn(slug=demo.slug))
        assert (answer.slug, answer.status, answer.expires_at) == (demo.slug, "ready", demo.expires_at)

    @pytest.mark.parametrize("slug", ["demo-00000000", "a"])
    def test_a_slug_that_names_no_demo_is_404(self, slug):
        with pytest.raises(NotFound):
            demo_get(SYSTEM, DemoSlugIn(slug=slug))

    def test_only_for_the_platform(self):
        demo = create()
        with pytest.raises(PermissionDenied):
            demo_get(a_user_context(), DemoSlugIn(slug=demo.slug))


class TestReaper:
    def test_purges_only_the_demos_whose_time_is_up(self, rf):
        ended, live = create(ANA), create(BEA)
        entered(rf, ended.slug, ANA)
        entered(rf, live.slug, BEA)
        code_for(ended.slug, ANA)
        lapse(ended.slug)
        assert reap_demos() == 1
        hub = Hub.objects.get(slug=ended.slug)
        assert (hub.status, hub.purged_at is not None) == ("purged", True)
        assert not Membership.objects.filter(host=ended.slug).exists()
        assert not get_user_model().objects.filter(username=f"demo:{ended.slug}").exists()
        assert not DemoCode.objects.filter(hub=hub).exists()
        assert events("base.demo.purged") == [{"id": str(hub.id), "slug": ended.slug}]
        # The live demo is untouched: its row, its owner and its code.
        assert Hub.objects.get(slug=live.slug).status == "ready"
        assert Membership.objects.filter(host=live.slug).exists()
        assert DemoCode.objects.filter(hub__slug=live.slug).exists()

    def test_a_demo_ended_by_hand_is_purged_too(self):
        demo = create()
        demo_expire(SYSTEM, DemoSlugIn(slug=demo.slug))
        assert reap_demos() == 1
        assert Hub.objects.get(slug=demo.slug).status == "purged"

    def test_the_other_hubs_and_their_members_are_never_touched(self, make_user):
        make_user("bea", host="a", role="hub_owner")
        Hub.objects.create(slug="acme", status="ready", expires_at=timezone.now() - MINUTE)
        assert reap_demos() == 0
        assert Membership.objects.filter(host="a").exists()
        assert Hub.objects.get(slug="acme").status == "ready"

    def test_hands_each_purged_demo_to_purge_demo_data(self, monkeypatch):
        purged = []
        monkeypatch.setattr(services, "purge_demo_data", lambda hub: purged.append(hub.slug))
        demo = create()
        lapse(demo.slug)
        reap_demos()
        assert purged == [demo.slug]

    def test_a_demo_whose_purge_fails_is_logged_and_the_others_are_purged(self, monkeypatch, caplog):
        first, second = create(ANA), create(BEA)
        lapse(first.slug)
        lapse(second.slug)

        def purge(hub):
            if hub.slug == first.slug:
                raise RuntimeError("the database went away")

        monkeypatch.setattr(services, "purge_demo_data", purge)
        with caplog.at_level(logging.ERROR, logger="base.services"):
            assert reap_demos() == 1
        # Its purge was undone; it stays on its way out (410) and due again, its lease given back.
        first_hub = Hub.objects.get(slug=first.slug)
        assert first_hub.status == "dropping" and registry.is_gone(first_hub)
        assert HubDue.objects.get(pk=first_hub.pk).lease_until is None
        assert Hub.objects.get(slug=second.slug).status == "purged"
        assert first.slug in caplog.text

    def test_a_demo_whose_drop_fails_waits_longer_each_time_and_is_not_tried_before(self, monkeypatch):
        """Review of hub#471 (I3): a drop the server refuses is noted on the demo (``attempts``, ``last_error``,
        ``next_attempt_at``: 1 min, 5 min…) and its ``hub_due`` waits for it, never every tick of the worker."""
        tried = []

        def refused(hub):
            tried.append(hub.slug)
            raise RuntimeError("permission denied to terminate process")

        monkeypatch.setattr(services, "purge_demo_data", refused)
        demo = create()
        lapse(demo.slug)
        before = timezone.now()

        assert reap_demos() == 0

        hub = Hub.objects.get(slug=demo.slug)
        assert (hub.status, hub.attempts) == ("dropping", 1)
        assert hub.last_error.startswith("drop_failed: RuntimeError: permission denied")
        assert before + MINUTE <= hub.next_attempt_at <= timezone.now() + MINUTE
        assert HubDue.objects.get(pk=hub.pk).due_at == hub.next_attempt_at
        assert reap_demos() == 0 and provision.run_due() == 0
        assert tried == [demo.slug]

        later = hub.next_attempt_at + dt.timedelta(seconds=1)
        assert reap_demos(later) == 0
        hub.refresh_from_db()
        assert (tried, hub.attempts) == ([demo.slug, demo.slug], 2)
        assert hub.next_attempt_at >= later + 5 * MINUTE - dt.timedelta(seconds=1)

    def test_a_demo_whose_preparation_had_failed_is_dropped_at_once_when_it_ends(self, monkeypatch):
        dropped = []
        monkeypatch.setattr(services, "purge_demo_data", lambda hub: dropped.append(hub.slug))
        demo = create()
        Hub.objects.filter(slug=demo.slug).update(
            status="failed", attempts=3, next_attempt_at=timezone.now() + 15 * MINUTE
        )
        lapse(demo.slug)

        assert reap_demos() == 1
        assert dropped == [demo.slug] and Hub.objects.get(slug=demo.slug).status == "purged"

    def test_purging_a_demo_that_has_not_ended_is_refused(self):
        demo = create()
        with pytest.raises(Conflict) as refused:
            demo_purge(SYSTEM, DemoSlugIn(slug=demo.slug))
        assert refused.value.code == "base.demo_live"
        assert Hub.objects.get(slug=demo.slug).status == "requested"

    def test_purging_twice_changes_nothing_more(self):
        demo = create()
        lapse(demo.slug)
        reap_demos()
        purged_at = Hub.objects.get(slug=demo.slug).purged_at
        assert demo_purge(SYSTEM, DemoSlugIn(slug=demo.slug)).status == "purged"
        assert Hub.objects.get(slug=demo.slug).purged_at == purged_at
        assert len(events("base.demo.purged")) == 1

    def test_a_demo_s_data_is_its_whole_database_dropped_on_its_cluster(self, monkeypatch):
        dropped = []
        monkeypatch.setattr(ops, "drop_database", lambda name, *, cluster=None: dropped.append((name, cluster)))
        hub = Hub.objects.get(slug=create().slug)
        purge_demo_data(hub)
        assert dropped == [(hub.db_name, None)]

    def test_a_demo_whose_row_names_another_database_drops_nothing(self, monkeypatch):
        """Review of hub#471 (M2): a DROP only ever takes the demo's own ``<control>_demo_<hex>``, never a business's
        or another demo's database its row might name by mistake."""
        dropped = []
        monkeypatch.setattr(ops, "drop_database", lambda name, *, cluster=None: dropped.append(name))
        hub = Hub.objects.get(slug=create().slug)
        for wrong in (names.hub_db_name(control_name(), hub.id), names.demo_db_name(control_name(), uuid.uuid7())):
            hub.db_name = wrong
            with pytest.raises(names.InvalidDatabaseName, match="not the demo"):
                purge_demo_data(hub)
        assert dropped == []

    def test_purging_a_demos_rows_never_drops_a_database_inside_their_transaction(self, monkeypatch):
        """Review of hub#471 (M3): ``base.demo.purge`` purges rows only; its database went before, outside any
        transaction of control (``base.tenancy.provision.drop``)."""
        dropped = []
        monkeypatch.setattr(ops, "drop_database", lambda name, *, cluster=None: dropped.append(name))
        demo = create()
        lapse(demo.slug)
        assert demo_purge(SYSTEM, DemoSlugIn(slug=demo.slug)).status == "purged"
        assert dropped == []

    def test_a_demo_of_before_its_own_databases_purges_no_data_of_the_apps(self, monkeypatch):
        # Made before round 2026-10-30, it shares the tables of every hub of phase 1, whose rows carry no hub_id (plan
        # §1.7): nothing tells its rows apart, and there is no database of its own to drop.
        dropped = []
        monkeypatch.setattr(ops, "drop_database", lambda name, *, cluster=None: dropped.append(name))
        hub = Hub.objects.create(slug="demo-0000beef", is_demo=True, status="expired")
        before = {model: model.objects.count() for model in (OutboxEvent, Hub, Membership)}
        assert purge_demo_data(hub) is None
        assert {model: model.objects.count() for model in before} == before
        assert dropped == []


class TestTombstones:
    def test_a_purged_demo_is_forgotten_after_its_days(self, settings):
        settings.DEMO_TOMBSTONE_DAYS = 7
        now = timezone.now()
        old = now - dt.timedelta(days=7, minutes=1)
        Hub.objects.create(slug="demo-00000001", is_demo=True, status="purged", purged_at=old)
        Hub.objects.create(slug="demo-00000002", is_demo=True, status="purged", purged_at=now - dt.timedelta(days=6))
        Hub.objects.create(slug="acme", status="cancelled", cancelled_at=now - dt.timedelta(days=30))
        assert reap_demo_tombstones(now) == 1
        assert sorted(Hub.objects.exclude(slug__in=["a", "b"]).values_list("slug", flat=True)) == [
            "acme",
            "demo-00000002",
        ]

    def test_the_reaper_forgets_old_tombstones_on_its_way(self, settings):
        settings.DEMO_TOMBSTONE_DAYS = 7
        eight_days_ago = timezone.now() - dt.timedelta(days=8)
        Hub.objects.create(slug="demo-00000001", is_demo=True, status="purged", purged_at=eight_days_ago)
        reap_demos()
        assert not Hub.objects.filter(slug="demo-00000001").exists()
