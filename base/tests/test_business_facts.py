"""What the Hub's assistant knows of the business from the start of every conversation
(``base.assistant.business_facts``): its country, its clock and the moment it is there, its sector, its apps on and,
for who runs it, its plan; and that the hours its tools give reach the model on that clock.

The QA saw a bar in Madrid hear «15:18» for what happened there at 16:18: the model knew no zone and its tools spoke
UTC.
"""

import datetime as dt
import json
from zoneinfo import ZoneInfo

from django.utils import timezone
from live.context import OperationContext, Scope
from live.operations import get

from apps.demo.models import Item
from base import assistant
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


def registered(hub, *, country="ES", zone="Europe/Madrid", vertical="restaurant", plan=STARTER) -> None:
    """``hub`` as erplora.com registered it, on the row the business at work reads."""
    hub.country, hub.timezone, hub.vertical = country, zone, vertical
    hub.state = {"plan": plan} if plan else {}
    hub.save()


def turn_of(hub, permissions=RUNS_IT, *, language="en", **data) -> dict:
    op = get("base.assistant.turn")
    ctx = OperationContext(scope=Scope("host", hub.slug), actor="ana", permissions=permissions, language=language)
    with use_hub(hub):
        return op(ctx, op.input.model_validate({"messages": [ASK], **data})).model_dump(mode="json")


def facts(hub, permissions=RUNS_IT, *, language="en", now=WINTER) -> str:
    ctx = OperationContext(scope=Scope("host", hub.slug), actor="ana", permissions=permissions, language=language)
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
