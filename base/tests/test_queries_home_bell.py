"""The bell of the Home, ``base.bell.counters``: each module's counters above zero that the person may see, with how
grave each one is, its heading, its sentence, its button and its deadline in the person's language, and for who runs
the hub the events the relay gave up on.

The stand-in modules name real operations registered for the test (``declare``), as in ``test_queries_home.py``.
"""

import logging

from django.utils import timezone
from live.meta import BellCounter
from live.models import OutboxEvent
from live.operations import get

from base.models.relay import EventDelivery
from base.models import Hub
from base.schemas.bell import BellCountersIn
from base.tenancy.tests.business import HUB_DB, A, B, in_business_a
from base.tests.test_queries_home import ADMIN, ctx, declare, in_b, module, modules

__all__ = ["declare", "in_business_a", "modules"]
pytestmark = HUB_DB


def bell(context):
    return get("base.bell.counters")(context, BellCountersIn()).model_dump(mode="json")["counters"]


def counter(key="to_confirm", operation="stock.item.count", **fields):
    return BellCounter(key=key, operation=operation, route="/stock", label=fields.pop("label", "To confirm"), **fields)


def said(**fields):
    """A counter's row with the words of one that declares none of them."""
    defaults = {"icon": "ion:notifications-outline", "severity": "warning", "body": None, "action_label": "Open", "due": None}
    return {**defaults, **fields}


def test_the_counters_above_zero(modules, declare):
    declare("stock.item.count", {"count": 2})
    declare("stock.low.count", {"rows": [{"count": 0}]})
    modules(module("stock", bell=[counter(icon="ion:alert"), counter("low", "stock.low.count")]))

    assert bell(ctx()) == [
        said(key="stock.to_confirm", app="stock", count=2, route="/stock", label="To confirm", icon="ion:alert",
             title="To confirm (2)")
    ]


def test_a_counter_says_what_it_declares_in_the_persons_language(modules, declare):
    """How grave it is, its heading with the number, its sentence, its button and its deadline: the soonest start of
    the counted ones, as the query answers it."""
    declare("stock.item.count", {"count": 3, "earliest": "2026-12-01T10:30:00+01:00"})
    declared = counter(
        severity="danger",
        title="%(count)d %(label)s",
        body="They start soon.",
        action_label="Confirm the %(count)d",
        due="earliest",
    )
    modules(module("stock", bell=[declared]))

    [row] = bell(ctx())
    assert row == {
        "key": "stock.to_confirm",
        "app": "stock",
        "count": 3,
        "route": "/stock",
        "label": "To confirm",
        "icon": "ion:notifications-outline",
        "severity": "danger",
        "title": "3 To confirm",
        "body": "They start soon.",
        "action_label": "Confirm the 3",
        "due": "2026-12-01T10:30:00+01:00",
    }


def test_a_counter_that_declares_no_button_says_open_in_the_persons_language(modules, declare):
    declare("stock.item.count", {"count": 1})
    modules(module("stock", bell=[counter()]))

    assert [row["action_label"] for row in bell(ctx(language="es"))] == ["Abrir"]


def test_a_counter_whose_deadline_is_not_a_date_time_is_left_out(modules, declare, caplog):
    declare("stock.item.count", {"count": 1, "earliest": "tomorrow"})
    modules(module("stock", bell=[counter(due="earliest")]))

    with caplog.at_level(logging.WARNING, logger="base.home"):
        assert bell(ctx()) == []
    assert "stock.to_confirm" in caplog.text


def test_a_counter_the_person_may_not_see_or_whose_query_fails(modules, declare, caplog):
    def broken(c, data):
        raise RuntimeError("boom")

    declare("stock.item.count", {"count": 2})
    declare("stock.broken.count", broken)
    declare("stock.text.count", {"count": "many"})
    modules(
        module(
            "stock",
            permissions=["stock.view"],
            bell=[
                counter(permission="stock.view"),
                counter("broken", "stock.broken.count"),
                counter("text", "stock.text.count"),
            ],
        )
    )

    with caplog.at_level(logging.WARNING, logger="base.home"):
        assert bell(ctx()) == []
    assert "stock.broken" in caplog.text
    assert "stock.text" in caplog.text
    assert [c["key"] for c in bell(ctx("stock.view"))] == ["stock.to_confirm"]


def test_the_counters_of_a_module_out_of_the_store_only_where_the_setting_says(modules, declare, settings):
    declare("demo.item.open_count", {"count": 1})
    modules(module("demo", bell=[counter("open", "demo.item.open_count")], listed=False))
    assert [c["key"] for c in bell(ctx())] == ["demo.open"]

    settings.SHOW_UNLISTED_MODULES = False
    assert bell(ctx()) == []

    Hub.objects.filter(slug=A.key).update(is_demo=True)
    assert [c["key"] for c in bell(ctx())] == ["demo.open"]


def refresh_every(context):
    return get("base.bell.counters")(context, BellCountersIn()).model_dump(mode="json")["refresh_every"]


def test_a_counter_that_changes_with_time_asks_the_bell_to_read_it_again(modules, declare):
    """A counter whose figure moves as time passes (a job waiting for a minute with no device alive) names how often
    the bell reads it again, besides its events. The bell is told the shortest period among the counters the person
    may see of the apps on, also while they are at zero: it is the time that raises them."""
    declare("printing.device.coverage", {"count": 0})
    declare("stock.item.count", {"count": 2})
    stalled = counter("stalled", "printing.device.coverage", permission="printing.view_settings")
    late = counter("late", "printing.device.coverage")
    printing = module(
        "printing",
        permissions=["printing.view_settings"],
        bell=[stalled, late],
        bell_refresh_every={"stalled": 30, "late": 60},
    )
    modules(printing, module("stock", bell=[counter()]))

    assert refresh_every(ctx("printing.view_settings")) == 30
    assert refresh_every(ctx()) == 60, "only the counters this person may see"
    assert bell(ctx()) == [
        said(key="stock.to_confirm", app="stock", count=2, route="/stock", label="To confirm", title="To confirm (2)")
    ]

    modules(printing, module("stock", bell=[counter()]), on=["stock"])
    assert refresh_every(ctx("printing.view_settings")) is None, "printing is off"
    modules(module("stock", bell=[counter()]))
    assert refresh_every(ctx()) is None, "no counter asks: the bell follows its events only, as before"


def dead_event(scope, status=EventDelivery.Status.DEAD):
    event = OutboxEvent.objects.create(scope_kind=scope.kind, scope_key=scope.key, name="sale.sale.completed")
    return EventDelivery.objects.create(event=event, app_label="invoice", status=status, next_attempt_at=timezone.now())


def test_the_failed_events_of_this_hub_for_an_administrator(modules, hub_b):
    """The bell says how many events between apps the relay gave up on, in this hub only, as an urgent notice."""
    modules(module("sale"))
    dead_event(A)
    dead_event(A)
    dead_event(A, EventDelivery.Status.PENDING)
    dead_event(B)  # another scope's row in A's database: not A's to count
    in_b(dead_event, B)

    assert bell(ctx(ADMIN)) == [
        {
            "key": "base.failed_events",
            "app": "base",
            "count": 2,
            "route": "/system#events",
            "label": "Failed events",
            "icon": "ion:warning-outline",
            "severity": "danger",
            "title": "2 failed events",
            "body": "An app did not receive what another one sent it: what it had to do stays undone until you send it "
            "again.",
            "action_label": "Review the events",
            "due": None,
        }
    ]
    spanish = bell(ctx(ADMIN, language="es"))[0]
    assert (spanish["label"], spanish["title"], spanish["action_label"]) == (
        "Eventos caídos",
        "2 eventos caídos",
        "Revisar los eventos",
    )
    assert spanish["body"].startswith("Una app no recibió lo que otra le mandó")
    assert bell(ctx()) == []  # not an administrator
    assert [c["count"] for c in in_b(bell, ctx(ADMIN, scope=B))] == [1]
