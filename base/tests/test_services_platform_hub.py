"""ERPlora's own hub in the registry (``base.services.platform_hub``): its row, its name, and what nobody does to it.

Its name changes as any business's address does (``base.services.address_change``): what is kept under the name it
leaves goes with it, one way and back.
"""

import datetime as dt

import pytest
from django.db import IntegrityError, OperationalError, transaction
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import get

from base import activation
from base.models import Hub, Membership
from base.models.activation import AppActivation
from base.registry import REGISTRY_SCOPE
from base.services import address_change, platform_hub
from base.tenancy.context import current, use_hub
from base.tenancy.tests.business import HUB_DB
from base.tests.test_session_revoke import ANA, OLGA, alive, login
from control.models import HubVisit
from control.tests.conftest import events

pytestmark = HUB_DB

DAY = dt.date(2026, 11, 24)
SYSTEM = system_context(REGISTRY_SCOPE)


@pytest.fixture
def own(hub_b):
    """ERPlora's own hub, its row under the name it had before and its apps written down under it."""
    Hub.objects.filter(pk=hub_b.pk).update(slug="erplora", is_platform=True)
    with use_hub(hub_b):
        AppActivation.objects.filter(host=hub_b.slug).update(host="erplora")
        AppActivation.objects.filter(host="erplora", app="task").update(state="off", chosen=False)
    return row_of(hub_b)


def row_of(hub) -> Hub:
    return Hub.objects.get(pk=hub.pk)


def rename(hub, ctx: OperationContext = SYSTEM) -> Hub:
    op = get("base.hub.platform_rename")
    op(ctx, op.input(id=hub.pk))
    return row_of(hub)


def kept_at(hub, name: str) -> dict:
    """What is kept under ``name``: who is in it and with which role, who came in and, in its own database, its apps."""
    with use_hub(hub):
        rows = AppActivation.objects.filter(host=name).values_list("app", "state", "chosen")
        apps = {app: (state, chosen) for app, state, chosen in rows}
    return {
        "people": set(Membership.objects.filter(host=name).values_list("user__username", "role")),
        "visits": set(HubVisit.objects.filter(host=name).values_list("saas_user_id", "day")),
        "apps": apps,
    }


NOBODY = {"people": set(), "visits": set()}


def in_control(kept: dict) -> dict:
    return {what: kept[what] for what in NOBODY}


@pytest.fixture
def peopled(own):
    """``own`` with its people, who came in and a session of each, all at its former name."""
    own.sessions = [login(ANA, own, role="hub_owner"), login(OLGA, own, role="hub_manager")]
    HubVisit.objects.create(host=own.slug, saas_user_id="0199c4b0-0000-7000-8000-00000000c0c0", day=DAY)
    return own


# ── Its row ───────────────────────────────────────────────────────────────────────────────────────────────────────


def test_its_rows_are_the_ones_that_say_so_whatever_their_name(own, hub_a):
    assert [row.pk for row in platform_hub.platform_rows()] == [own.pk]


def test_without_one_there_is_none(hub_a):
    Hub.objects.filter(pk=hub_a.pk).update(slug="erplora")
    assert platform_hub.platform_rows() == []


def test_renaming_it_changes_its_name_alone_in_its_row(own):
    before = Hub.objects.filter(pk=own.pk).values().get()

    renamed = rename(own)

    after = Hub.objects.filter(pk=own.pk).values().get()
    assert (renamed.pk, renamed.slug) == (own.pk, "erp")
    assert {**after, "updated_at": None} == {**before, "slug": "erp", "updated_at": None}
    assert events("base.hub.registered") == [{"id": str(own.pk), "slug": "erp", "created": False}]


def test_its_database_opens_under_the_new_name_as_before(own):
    with use_hub(own):
        before = current().alias

    with use_hub(rename(own)):
        assert (current().alias, current().hub.slug) == (before, "erp")


def test_a_name_another_row_bears_is_never_taken(own, hub_a):
    Hub.objects.filter(pk=hub_a.pk).update(slug="erp")

    with pytest.raises(IntegrityError), transaction.atomic():
        rename(own)

    assert row_of(own).slug == "erplora"


def test_a_business_is_never_renamed(hub_a):
    with pytest.raises(NotFound):
        rename(hub_a)

    assert row_of(hub_a).slug == hub_a.slug


def test_only_the_platform_renames_it(own, make_user):
    person = OperationContext(
        scope=REGISTRY_SCOPE, actor=make_user("ana"), permissions=frozenset({"*"}), language="en"
    )
    with pytest.raises(PermissionDenied) as refused:
        rename(own, person)

    assert refused.value.code == "base.internal_only"
    assert row_of(own).slug == "erplora"


def test_only_its_row_is_refused(own, hub_a):
    with pytest.raises(Conflict) as refused:
        platform_hub.refuse_platform_hub(own)
    assert (refused.value.code, refused.value.status) == ("base.platform_hub_kept", 409)
    platform_hub.refuse_platform_hub(hub_a)


# ── What goes with its name ───────────────────────────────────────────────────────────────────────────────────────


def test_its_people_who_came_in_and_its_apps_go_with_it_and_come_back_with_it(peopled, settings):
    before = kept_at(peopled, "erplora")
    assert len(before["people"]) == 2 and len(before["visits"]) == 3 and before["apps"]["task"] == ("off", False)

    here = rename(peopled)

    assert here.slug == "erp"
    assert kept_at(here, "erp") == before
    assert in_control(kept_at(here, "erplora")) == NOBODY

    settings.PLATFORM_HUB_SLUG = "erplora"
    back = rename(here)

    assert back.slug == "erplora"
    assert kept_at(back, "erplora") == before
    assert in_control(kept_at(back, "erp")) == NOBODY


def test_what_changed_under_the_new_name_comes_back_too(peopled, settings):
    here = rename(peopled)
    Membership.objects.filter(host="erp", role="hub_manager").delete()
    with use_hub(here):
        AppActivation.objects.filter(host="erp", app="task").update(state="on", chosen=True)

    settings.PLATFORM_HUB_SLUG = "erplora"
    back = rename(here)

    kept = kept_at(back, "erplora")
    assert {role for _, role in kept["people"]} == {"hub_owner"}
    assert kept["apps"]["task"] == ("on", True)


def test_the_sessions_opened_under_its_former_name_end_as_at_any_address_change(peopled, hub_a, settings):
    another = login(ANA, hub_a, role="hub_owner")

    here = rename(peopled)

    assert [alive(session) for session in peopled.sessions] == [False, False]
    assert alive(another)

    entered = login(ANA, here, role="hub_owner")
    assert alive(entered)
    settings.PLATFORM_HUB_SLUG = "erplora"
    rename(here)

    assert not alive(entered)
    assert [alive(session) for session in peopled.sessions] == [False, False]
    assert alive(another)


def test_another_business_keeps_all_its_own(peopled, hub_a, settings):
    login(OLGA, hub_a, role="hub_owner")
    before = kept_at(hub_a, hub_a.slug)

    here = rename(peopled)
    settings.PLATFORM_HUB_SLUG = "erplora"
    rename(here)

    assert kept_at(hub_a, hub_a.slug) == before
    assert before["people"] and before["apps"]


def test_under_the_name_it_has_already_nothing_changes_and_no_session_ends(peopled, settings):
    settings.PLATFORM_HUB_SLUG = "erplora"
    before = kept_at(peopled, "erplora")

    assert rename(peopled).slug == "erplora"

    assert kept_at(peopled, "erplora") == before
    assert all(alive(session) for session in peopled.sessions)


def test_a_rename_whose_database_cannot_be_reached_leaves_it_as_it_was(peopled, monkeypatch):
    def unreachable(*args, **kwargs):
        raise OperationalError("the connection is gone")

    before = kept_at(peopled, "erplora")
    monkeypatch.setattr(address_change, "_bring_apps", unreachable)

    with pytest.raises(OperationalError):
        rename(peopled)

    assert row_of(peopled).slug == "erplora"
    assert kept_at(peopled, "erplora") == before
    assert all(alive(session) for session in peopled.sessions)


def test_every_app_stays_on_in_it_whatever_is_written_down(peopled):
    here = rename(peopled)

    with use_hub(here):
        assert activation.off_apps(Scope("host", here.slug)) == frozenset()
