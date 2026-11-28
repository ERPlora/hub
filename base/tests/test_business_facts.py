"""What the Hub's assistant knows of the business from the start of every conversation
(``base.assistant.business_facts``): its country, its clock and the moment it is there, its language and the person's
own, its sector, its apps on, for who runs it its plan, and the settings each app on gives to whoever may read them;
and that the hours its tools give reach the model on that clock.

The QA saw a bar in Madrid hear «15:18» for what happened there at 16:18: the model knew no zone and its tools spoke
UTC. It also had to read how the till and the drawer were set before saying it, drew a reservation's card without the
phone the business requires, and offered to put in Spanish a profile already in Spanish.
"""

import datetime as dt
import json
from zoneinfo import ZoneInfo

from django.utils import timezone
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs
from live.operations import get

from apps.cash_register.models import Settings as DrawerSettings
from apps.demo.models import Item
from apps.reservation.models import Settings as BookSettings
from apps.sale.models.settings import Settings as TillSettings
from base import assistant
from base.models import Membership
from base.models.activation import AppActivation
from base.models.profile import Profile
from base.tenancy.context import use_hub
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.test_plan_usage_figures import STARTER, chose_only
from base.tests.test_services_assistant import ASK, asked, call

#: The fixture these tests take from elsewhere.
__all__ = ["in_business_a"]

pytestmark = HUB_DB
STAFF = frozenset({"base.view_home", "demo.*"})
RUNS_IT = STAFF | {"base.administer_hub"}
MADRID = ZoneInfo("Europe/Madrid")
MEXICO = ZoneInfo("America/Mexico_City")
#: 15:18 in UTC, a Sunday: 16:18 in Madrid, 09:18 in Mexico City.
WINTER = dt.datetime(2026, 11, 22, 15, 18, tzinfo=dt.UTC)


def registered(
    hub, *, country="ES", zone="Europe/Madrid", vertical="restaurant", plan=STARTER, language="es"
) -> None:
    """``hub`` as erplora.com registered it, on the row the business at work reads."""
    hub.country, hub.timezone, hub.vertical, hub.language = country, zone, vertical, language
    hub.state = {"plan": plan} if plan else {}
    hub.save()


def turn_of(hub, permissions=RUNS_IT, *, language="en", **data) -> dict:
    op = get("base.assistant.turn")
    ctx = OperationContext(scope=Scope("host", hub.slug), actor="ana", permissions=permissions, language=language)
    with use_hub(hub):
        return op(ctx, op.input.model_validate({"messages": [ASK], **data})).model_dump(mode="json")


def facts(hub, permissions=RUNS_IT, *, language="en", now=WINTER, actor="ana") -> str:
    ctx = OperationContext(scope=Scope("host", hub.slug), actor=actor, permissions=permissions, language=language)
    with use_hub(hub):
        business = get("base.business.get")(ctx, get("base.business.get").input()).model_dump(mode="json")
        return assistant.business_facts.block(ctx, business, assistant.tools.active_apps(ctx.scope), now=now)


# ── What the model is told of the business ───────────────────────────────────────────────────────────────────────


def test_every_turn_tells_the_model_the_business_where_it_is_its_clock_sector_apps_and_plan(in_business_a):
    registered(in_business_a)
    chose_only(in_business_a, "demo", "customer")
    text = turn_of(in_business_a)["instructions"]
    assert "- Country: Spain (ES)." in text
    assert "- Time zone: Europe/Madrid." in text
    assert "- Sector: restaurant." in text
    assert "- Apps on: Customers, Demo." in text
    assert "- Plan: starter." in text


def test_the_moment_is_told_on_the_business_clock_with_its_weekday(in_business_a):
    registered(in_business_a)
    assert "Now there: Sunday 2026-11-22 16:18 (UTC+01:00)." in facts(in_business_a)
    summer = dt.datetime(2026, 7, 1, 10, 0, tzinfo=dt.UTC)
    assert "Now there: Wednesday 2026-07-01 12:00 (UTC+02:00)." in facts(in_business_a, now=summer)


def test_today_is_the_business_s_day_when_utc_is_still_on_the_one_before(in_business_a):
    """At 00:48 in Madrid «desde hoy» made a tax rule start on the day before, the one UTC was still on."""
    registered(in_business_a)
    past_midnight = dt.datetime(2026, 11, 22, 23, 48, tzinfo=dt.UTC)
    assert "Now there: Monday 2026-11-23 00:48 (UTC+01:00)." in facts(in_business_a, now=past_midnight)


def test_the_moment_of_a_turn_is_now_on_the_business_clock(in_business_a):
    registered(in_business_a, zone="America/Mexico_City")
    before = timezone.localtime(timezone.now(), MEXICO)
    text = turn_of(in_business_a)["instructions"]
    after = timezone.localtime(timezone.now(), MEXICO)
    told = {f"Now there: {moment:%A %Y-%m-%d %H:%M} (UTC-06:00)." for moment in (before, after)}
    assert any(line in text for line in told)


def test_the_country_and_the_apps_are_named_in_the_language_of_the_chat(in_business_a):
    registered(in_business_a)
    chose_only(in_business_a, "customer")
    text = turn_of(in_business_a, language="es")["instructions"]
    assert "- Country: España (ES)." in text
    assert "- Apps on: Clientes." in text


def test_an_app_turned_off_is_not_told_as_on(in_business_a):
    registered(in_business_a)
    chose_only(in_business_a, "demo")
    assert "Customers" not in facts(in_business_a)


def test_the_plan_is_told_only_to_who_runs_the_business(in_business_a):
    registered(in_business_a)
    assert "- Plan: starter." in facts(in_business_a, RUNS_IT)
    assert "Plan:" not in facts(in_business_a, STAFF)


def came_with_another(hub, label: str) -> None:
    """App ``label`` on in ``hub`` without the business choosing it, as one that came with another app."""
    with use_hub(hub):
        AppActivation.objects.filter(host=hub.slug, app=label).update(state=AppActivation.State.ON, chosen=False)


def test_the_plan_says_how_many_apps_it_counts_and_which_ones(in_business_a):
    """Apps says «21 apps on · 14 of 40 of your plan»: told only the apps on, the assistant could not explain why
    the two figures differ."""
    registered(in_business_a, plan={**STARTER, "max_apps": 40})
    chose_only(in_business_a, "demo", "customer")
    came_with_another(in_business_a, "inventory")
    text = facts(in_business_a)
    assert "- Apps on: Customers, Demo, Inventory." in text
    assert (
        "- Plan: starter. Apps it counts: 2 of 40 (only those the business chose, not one that came with another app "
        "or was on from the start)."
    ) in text


def test_a_plan_with_no_limit_of_apps_says_so(in_business_a):
    registered(in_business_a, plan={**STARTER, "max_apps": 0})
    chose_only(in_business_a, "demo")
    assert "- Plan: starter. Apps it counts: 1, with no limit (only those the business chose" in facts(in_business_a)


def test_what_erplora_com_did_not_register_is_not_told(in_business_a):
    """A demo has no country, sector nor plan: those lines are not there, never a guess."""
    registered(in_business_a, country="", vertical="", plan=None)
    text = facts(in_business_a)
    assert "Country:" not in text and "Sector:" not in text and "Plan:" not in text
    assert "- Time zone: Europe/Madrid." in text


def test_each_business_hears_its_own_clock(hub_a, hub_b):
    registered(hub_a, zone="Europe/Madrid")
    registered(hub_b, country="MX", zone="America/Mexico_City", vertical="hair_salon")
    a, b = turn_of(hub_a)["instructions"], turn_of(hub_b)["instructions"]
    assert "Europe/Madrid" in a and "America/Mexico_City" not in a
    assert "America/Mexico_City" in b and "Europe/Madrid" not in b
    assert "- Sector: hair_salon." in b and "hair_salon" not in a


# ── The hours of its tools, on the business's clock ──────────────────────────────────────────────────────────────


def read_items(hub) -> dict:
    """What the model reads of business ``hub``'s items, one changed at 15:18 UTC."""
    with use_hub(hub):
        Item.objects.create(name="Terraza")
        Item.objects.update(updated_at=WINTER)
    read = call("demo.item.list", {})
    [result] = turn_of(hub, messages=[ASK, asked(read)], pending=[read])["append"]
    return json.loads(result["content"])


def test_a_read_reaches_the_model_on_the_business_clock_not_in_utc(in_business_a):
    registered(in_business_a)
    [row] = read_items(in_business_a)["rows"]
    assert row["updated_at"] == "2026-11-22T16:18:00+01:00"


def test_each_business_reads_its_hours_on_its_own_clock(hub_a, hub_b):
    registered(hub_a, zone="Europe/Madrid")
    registered(hub_b, zone="America/Mexico_City")
    assert read_items(hub_a)["rows"][0]["updated_at"] == "2026-11-22T16:18:00+01:00"
    assert read_items(hub_b)["rows"][0]["updated_at"] == "2026-11-22T09:18:00-06:00"


def test_what_a_write_gives_back_after_the_yes_is_on_the_business_clock_too(in_business_a):
    registered(in_business_a, zone="America/Mexico_City")
    write = call("demo.item.create", {"name": "Mesa 4"})
    drawn = turn_of(in_business_a, messages=[ASK, asked(write)], pending=[write])
    yes = turn_of(
        in_business_a,
        messages=[ASK, asked(write)],
        pending=drawn["pending"],
        decision={"call_id": "c1", "accepted": True},
    )
    [result] = yes["append"]
    assert json.loads(result["content"])["updated_at"].endswith("-06:00")


# ── Its language and the person's own ────────────────────────────────────────────────────────────────────────────


def a_person(hub, make_user, *, own: str = ""):
    """A person of business ``hub`` who chose ``own`` in «My profile» (empty: none, the business's)."""
    user = make_user("saas:7", host=hub.slug, role=Membership.Role.OWNER)
    if own:
        with use_hub(hub):
            Profile.objects.create(username="saas:7", language=own)
    return user


def test_the_business_s_language_and_the_one_the_person_chose_are_told(in_business_a, make_user):
    """In Spanish, with «My profile» already in Spanish, the QA heard an offer to put it in Spanish."""
    registered(in_business_a, language="en")
    person = a_person(in_business_a, make_user, own="es")
    text = facts(in_business_a, actor=person)
    assert "- Language of the business: English (en). This person's own, in My profile: Spanish (es)." in text


def test_a_person_who_chose_no_language_sees_the_business_s(in_business_a, make_user):
    registered(in_business_a, language="es")
    text = facts(in_business_a, actor=a_person(in_business_a, make_user))
    assert "- Language of the business: Spanish (es). This person's own, in My profile: none, so the business's." in text


def test_a_business_that_could_not_be_read_has_no_language_told(in_business_a):
    """``base.business.get`` failed: the turn goes on with nothing of it, never a guess."""
    ctx = OperationContext(scope=Scope("host", in_business_a.slug), actor="ana", permissions=RUNS_IT, language="en")
    with use_hub(in_business_a):
        text = assistant.business_facts.block(ctx, {}, assistant.tools.active_apps(ctx.scope), now=WINTER)
    assert "Language" not in text


def test_with_no_person_behind_only_the_business_s_language_is_told(in_business_a):
    """An API key or an automation's step has no «My profile»."""
    registered(in_business_a, language="es")
    text = facts(in_business_a)
    assert "- Language of the business: Spanish (es)." in text
    assert "My profile" not in text


# ── The settings of its apps on, as each reads them ──────────────────────────────────────────────────────────────

#: Whoever sells, counts the drawer and reads the book's rules.
READS_SETTINGS = RUNS_IT | {"sale.view_sale", "cash_register.view_session", "reservation.view_settings"}
TILL, DRAWER, BOOK = "sale__pos_settings__get", "cash_register__settings__get", "reservation__settings__get"


def told_settings(text: str, tool: str) -> dict:
    """The settings the instructions tell as ``tool`` reads them now, as it answers; empty when they are not told."""
    told = [line for line in text.splitlines() if line.startswith("- Settings of ") and f"`{tool}`" in line]
    assert len(told) <= 1, told
    return json.loads(told[0].split(": ", 1)[1]) if told else {}


def saved(hub, model, **values) -> None:
    with use_hub(hub):
        model.objects.create(**values)


def test_the_till_and_the_drawer_are_told_as_they_are_set_with_their_apps_on(in_business_a):
    """Asked how the till and the drawer were set, the model had to read them first: every turn tells them now."""
    registered(in_business_a)
    chose_only(in_business_a, "sale", "cash_register")
    saved(in_business_a, TillSettings, allow_transfer=False, max_discount_percent=20)
    saved(in_business_a, DrawerSettings, require_blind_count=True, auto_close_time=dt.time(4, 0))
    text = turn_of(in_business_a, READS_SETTINGS)["instructions"]
    till, drawer = told_settings(text, TILL), told_settings(text, DRAWER)
    assert (till.get("allow_transfer"), till.get("max_discount_percent")) == (False, 20)
    assert (drawer.get("require_blind_count"), drawer.get("auto_close_time")) == (True, "04:00")


def test_the_settings_are_named_by_their_app_in_the_language_of_the_chat(in_business_a):
    registered(in_business_a)
    chose_only(in_business_a, "cash_register")
    text = facts(in_business_a, READS_SETTINGS, language="es")
    assert "- Settings of Caja, read now with `cash_register__settings__get` (no need to read them again): {" in text


def test_an_app_turned_off_tells_none_of_its_settings(in_business_a):
    registered(in_business_a)
    chose_only(in_business_a, "cash_register")
    text = facts(in_business_a, READS_SETTINGS)
    assert told_settings(text, DRAWER) != {}
    assert told_settings(text, TILL) == {}


def test_settings_the_person_may_not_read_are_not_told(in_business_a):
    registered(in_business_a)
    chose_only(in_business_a, "sale", "cash_register")
    text = facts(in_business_a, RUNS_IT | {"sale.view_sale"})
    assert told_settings(text, TILL) != {}
    assert told_settings(text, DRAWER) == {}


def test_the_book_says_whether_every_reservation_needs_a_phone(in_business_a):
    """The QA saw a reservation's card drawn without a phone fail on «yes»: the business requires one."""
    registered(in_business_a)
    chose_only(in_business_a, "customer", "reservation")
    saved(in_business_a, BookSettings, require_phone=True)
    assert told_settings(facts(in_business_a, READS_SETTINGS), BOOK).get("require_phone") is True


def test_the_hour_the_settings_were_saved_is_on_the_business_clock(in_business_a):
    registered(in_business_a)
    chose_only(in_business_a, "sale")
    saved(in_business_a, TillSettings)
    with use_hub(in_business_a):
        TillSettings.objects.update(updated_at=WINTER)
    assert told_settings(facts(in_business_a, READS_SETTINGS), TILL).get("updated_at") == "2026-11-22T16:18:00+01:00"


def test_each_business_hears_its_own_settings(hub_a, hub_b):
    for hub, transfer in ((hub_a, False), (hub_b, True)):
        registered(hub)
        chose_only(hub, "sale")
        saved(hub, TillSettings, allow_transfer=transfer)
    assert told_settings(facts(hub_a, READS_SETTINGS), TILL).get("allow_transfer") is False
    assert told_settings(facts(hub_b, READS_SETTINGS), TILL).get("allow_transfer") is True


def test_what_an_app_declares_as_its_settings_is_a_read_of_its_own_that_needs_no_data():
    """What an app names in its ``assistant_settings`` is run with nothing said in every turn: a write, a read of
    another app or one that needs a datum would never be told, or tell what is not the app's."""
    declared = {
        config.label: getattr(config, assistant.business_facts.SETTINGS_HOOK, ()) for config in all_live_app_configs()
    }
    assert {label for label, names in declared.items() if names} >= {"sale", "cash_register", "reservation"}
    for label, names in declared.items():
        for name in names:
            op = get(name)
            assert (name.split(".")[0], op.kind) == (label, "query"), name
            op.input.model_validate({})
