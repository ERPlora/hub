"""Every event «Choose what happens» offers has its words in English and in Spanish (FLOW-F10).

The editor names an event by ``flow.events.<app>__<entity>__<fact>`` of ``frontend/locale/{en,es}.json``
(``eventLabel`` of ``frontend/lib/phrasing.ts``). Without them the name is composed from the internal one, half in
English on a Spanish screen («WhatsApp inbox: template created»), so this walks every event an app declares.

What only the platform records, never something done in the business (an app's ``events.SYSTEM_ONLY``: the hourly
prune of old prints, what a recovery from a separate copy brings back), starts no automation and is not offered.
"""

import json
from pathlib import Path

from django.apps import apps
from live.meta import declared_events

from apps.flow import queries
from apps.flow.schemas.triggers import EventTrigger

from .conftest import A, HUB_DB, run

pytestmark = HUB_DB

LOCALE = Path(apps.get_app_config("flow").path) / "frontend" / "locale"

#: What the platform alone records: the hourly prune, and the recovery from a separate copy, whose events never start
#: an automation (``services.runs.react``).
SYSTEM_ONLY = {
    "printing.job.pruned",
    "appointment.appointment.restored",
    "appointment.recurring.restored",
    "customer.customer.restored",
    "inventory.product.restored",
}


def events(language: str) -> dict[str, str]:
    return json.loads((LOCALE / f"{language}.json").read_text(encoding="utf-8"))["flow"]["events"]


def offered() -> set[str]:
    return set(queries.catalog.catalog_events(A))


def test_the_list_reaches_every_event_an_app_declares_but_what_only_the_platform_records():
    of_the_apps = {name for name in declared_events() if name.split(".", 1)[0] in queries.catalog.installed_apps()}
    assert offered() == of_the_apps - SYSTEM_ONLY


def test_every_event_the_list_offers_has_its_words_in_both_languages():
    en, es = events("en"), events("es")
    without_words = [
        name
        for name in sorted(offered())
        if not (en.get(key := name.replace(".", "__"), "").strip() and es.get(key, "").strip())
    ]
    assert without_words == []


def test_what_only_the_platform_records_cannot_start_an_automation():
    listed = {event.name for event in run("flow.catalog.read", {}).events}
    assert not listed & SYSTEM_ONLY
    for name in sorted(SYSTEM_ONLY):
        problems, _ = queries.problems.catalog_problems(A, EventTrigger(kind="event", event=name), [])
        assert set(problems) == {"trigger.event"}, name
