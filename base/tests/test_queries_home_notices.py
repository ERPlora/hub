"""The device's notices, ``base.notice.list`` (APPOINTMENT-F28): the rows each module's notices tell, with their
texts in the person's language, the newest first, and which notices the person hears.

The stand-in modules name real operations registered for the test (``declare``), as in ``test_queries_home.py``.
"""

import logging

from django.utils import timezone
from django.utils.translation import gettext_lazy
from live.meta import DeviceNotice, SetupCheck
from live.operations import get

from base.schemas.home import NoticeListIn
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.test_queries_home import ctx, declare, module, modules

__all__ = ["declare", "in_business_a", "modules"]
pytestmark = HUB_DB


def notice_list(context):
    return get("base.notice.list")(context, NoticeListIn()).model_dump(mode="json")["notices"]


def notice(key="added", operation="stock.item.changes", **fields):
    return DeviceNotice(
        key=key,
        operation=operation,
        title=fields.pop("title", (gettext_lazy("New item · {name}"), gettext_lazy("New item"))),
        route=fields.pop("route", "/stock?day={at:.10}"),
        **fields,
    )


CHANGES = {
    "rows": [
        {"id": 7, "at": "2026-10-23T09:45:00Z", "kind": "removed", "name": "Pen", "sku": "P-1", "shelf": ""},
        {"id": 3, "at": "2026-10-23T09:40:00Z", "kind": "added", "name": "", "sku": "B-2", "shelf": "A"},
        {"id": 5, "at": "2026-10-23T09:44:00+02:00", "kind": "added", "name": "Ink", "sku": "I-9", "shelf": "C"},
    ]
}


def test_the_rows_each_notice_tells_with_its_texts_the_newest_first(modules, declare):
    """Each declaration takes the rows that pass its ``when``; the title is the first template filled in, the body
    joins the parts filled in, and the route is filled in too. One query for the notices that share it."""
    calls = []
    declare("stock.item.changes", lambda c, data: calls.append(data) or CHANGES)
    modules(
        module(
            "stock",
            notices=[
                notice(when=[SetupCheck(field="kind", equals="added")], body=["{sku}", gettext_lazy("shelf {shelf}")]),
                notice("removed", when=[SetupCheck(field="kind", equals="removed")], title=["Item removed · {name}"]),
            ],
        )
    )

    assert notice_list(ctx()) == [
        {
            "key": "stock.removed",
            "app": "stock",
            "id": "7",
            "at": "2026-10-23T09:45:00Z",
            "title": "Item removed · Pen",
            "body": "",
            "route": "/stock?day=2026-10-23",
        },
        {
            "key": "stock.added",
            "app": "stock",
            "id": "3",
            "at": "2026-10-23T09:40:00Z",
            "title": "New item",
            "body": "B-2 · shelf A",
            "route": "/stock?day=2026-10-23",
        },
        {
            "key": "stock.added",
            "app": "stock",
            "id": "5",
            "at": "2026-10-23T09:44:00+02:00",
            "title": "New item · Ink",
            "body": "I-9 · shelf C",
            "route": "/stock?day=2026-10-23",
        },
    ]
    assert len(calls) == 1


def test_the_texts_are_in_the_persons_language(modules, declare):
    declare("stock.item.changes", CHANGES)
    modules(module("stock", notices=[notice(when=[SetupCheck(field="id", equals=5)], title=[gettext_lazy("Failed events")])]))

    assert [n["title"] for n in notice_list(ctx(language="es"))] == ["Eventos caídos"]


def test_the_query_runs_as_the_person_with_the_notices_params(modules, declare):
    seen = []
    declare("stock.item.changes", lambda c, data: seen.append((c.actor, data.model_dump())) or {"rows": []})
    modules(module("stock", notices=[notice(params={"limit": 5})]))

    assert notice_list(ctx(actor="bea")) == []
    assert seen == [("bea", {"limit": 5})]


def test_a_notice_the_person_may_not_see_or_whose_query_fails_is_left_out(modules, declare, caplog):
    def broken(c, data):
        raise RuntimeError("boom")

    declare("stock.item.changes", CHANGES)
    declare("stock.broken.changes", broken)
    modules(
        module(
            "stock",
            permissions=["stock.view"],
            notices=[notice(permission="stock.view"), notice("broken", "stock.broken.changes")],
        )
    )

    with caplog.at_level(logging.WARNING, logger="base.home"):
        assert notice_list(ctx()) == []
    assert "stock.broken" in caplog.text
    assert len(notice_list(ctx("stock.view"))) == 3


def test_a_template_its_translation_breaks_falls_to_the_next_and_is_logged(modules, declare, caplog):
    """A translator's typo in a field (``{nombre}``) must not lose the notice: the next title, and a line in the log."""
    declare("stock.item.changes", {"rows": [CHANGES["rows"][2]]})
    modules(module("stock", notices=[notice(title=["{nombre}", "New item"], body=["{sku:%Y}", "{shelf}"])]))

    with caplog.at_level(logging.WARNING, logger="base.home"):
        [told] = notice_list(ctx())
    assert (told["title"], told["body"]) == ("New item", "C")
    assert "stock.added" in caplog.text


def test_a_row_without_a_title_filled_in_is_not_told(modules, declare, caplog):
    declare("stock.item.changes", {"rows": [CHANGES["rows"][1]]})
    modules(module("stock", notices=[notice(title=["New item · {name}"])]))

    with caplog.at_level(logging.WARNING, logger="base.home"):
        assert notice_list(ctx()) == []
    assert "stock.added" in caplog.text


BOOKING = {
    "id": 9,
    "at": "2026-10-23T08:00:00Z",
    "offset": "2026-10-23T09:44:00+02:00",
    "wall": "2026-10-23T10:15:00",
    "day": "2026-10-23",
    "opens": "09:30:00",
    "code": "2026",
}


def test_a_template_formats_the_rows_dates_and_hours_on_the_businesss_clock(modules, declare):
    """The rows reach base as JSON, so a date is text: ``{at:%H:%M}`` reads it as the date, hour or instant it says,
    an instant on the business's clock (Django's zone) and one without an offset as it says; ``{at:.10}`` still
    slices the text, also beside a date format on the same field."""
    declare("stock.item.changes", {"rows": [BOOKING]})
    modules(
        module(
            "stock",
            notices=[
                notice(
                    title=["Appointment at {at:%H:%M}"],
                    body=["{offset:%H:%M}", "{wall:%H:%M}", "{day:%d/%m/%Y}", "opens {opens:%H:%M}"],
                    route="/agenda?date={at:.10}&hour={at:%H}",
                )
            ],
        )
    )

    with timezone.override("Europe/Madrid"):
        [told] = notice_list(ctx())
    assert (told["title"], told["body"], told["route"]) == (
        "Appointment at 10:00",
        "09:44 · 10:15 · 23/10/2026 · opens 09:30",
        "/agenda?date=2026-10-23&hour=10",
    )
    assert told["at"] == "2026-10-23T08:00:00Z"
    with timezone.override("Atlantic/Canary"):
        [told] = notice_list(ctx())
    assert (told["title"], told["body"]) == ("Appointment at 09:00", "08:44 · 10:15 · 23/10/2026 · opens 09:30")


def test_a_date_format_on_a_field_that_is_no_iso_date_is_logged_and_that_text_left_out(modules, declare, caplog):
    """``{code:%Y}`` on ``"2026"`` (a year as text, not an ISO date) is a module's mistake: never read as some hour."""
    declare("stock.item.changes", {"rows": [BOOKING]})
    modules(module("stock", notices=[notice(title=["Year {code:%Y}", "New item"], body=["{code:%H}", "{day:%d/%m}"])]))

    with caplog.at_level(logging.WARNING, logger="base.home"), timezone.override("Europe/Madrid"):
        [told] = notice_list(ctx())
    assert (told["title"], told["body"]) == ("New item", "23/10")
    assert "Year {code:%Y}" in caplog.text


def test_a_percent_format_on_a_number_of_the_row_formats_as_before(modules, declare):
    """``%`` is also a number's percent (``{share:.0%}``): only a text is read as a date, a number formats as it did."""
    declare("stock.item.changes", {"rows": [{**BOOKING, "share": 0.5}]})
    modules(module("stock", notices=[notice(title=["{share:.0%} booked"])]))

    [told] = notice_list(ctx())
    assert told["title"] == "50% booked"


def test_the_notices_of_a_module_off_or_out_of_the_store(modules, declare, settings):
    declare("stock.item.changes", CHANGES)
    modules(module("stock", notices=[notice()]), on=[])
    assert notice_list(ctx()) == []

    modules(module("stock", notices=[notice()], listed=False))
    settings.SHOW_UNLISTED_MODULES = False
    assert notice_list(ctx()) == []


def test_it_says_which_notices_the_person_hears_even_with_nothing_to_tell(modules, declare):
    """So the shell asks the device's permission only where there is something to be told."""
    declare("stock.item.changes", {"rows": []})
    modules(
        module("stock", permissions=["stock.view"], notices=[notice(), notice("secret", permission="stock.view")]),
        module("sale", notices=[notice(operation="stock.item.changes")]),
        on=["stock"],
    )

    answer = get("base.notice.list")(ctx(), NoticeListIn()).model_dump(mode="json")

    assert answer == {"notices": [], "sources": ["stock.added"]}
    assert get("base.notice.list")(ctx("stock.view"), NoticeListIn()).model_dump(mode="json")["sources"] == [
        "stock.added",
        "stock.secret",
    ]
