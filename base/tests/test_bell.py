"""What each counter of the bell says (``base.bell``): how grave it is, its heading, its sentence, its button and its
deadline, in the person's language, and the defaults of a counter that declares none of them. Every module's counter
declares its words, in English and in Spanish."""

import datetime as dt
from pathlib import Path

import pytest
from django.utils.translation import override
from live.meta import BELL_SEVERITIES, BellCounter, module_configs

from base import bell
from base.schemas.bell import BellCounterOut, BellCountersOut
from base.tests.typed_operations import ts_fields

OPERATIONS_TS = Path(__file__).resolve().parents[1] / "frontend" / "operations-bell.d.ts"


def counter(**fields):
    return BellCounter(key="to_confirm", operation="stock.item.count", route="/stock", label=fields.pop("label", "To confirm"), **fields)


def test_a_counter_that_declares_nothing_says_its_label_and_number_with_open():
    with override("en"):
        notice = bell.notice("stock.to_confirm", counter(), {"count": 3})

    assert notice == {
        "key": "stock.to_confirm",
        "app": "stock",
        "count": 3,
        "route": "/stock",
        "label": "To confirm",
        "icon": "ion:notifications-outline",
        "severity": "warning",
        "title": "To confirm (3)",
        "body": None,
        "action_label": "Open",
        "due": None,
    }


def test_its_button_says_open_in_the_persons_language():
    with override("es"):
        assert bell.notice("stock.to_confirm", counter(), {"count": 1})["action_label"] == "Abrir"


def test_what_a_counter_declares_wins_filled_in_with_its_number_and_label():
    declared = counter(
        icon="ion:alert-outline",
        severity="danger",
        title="%(count)d %(label)s",
        body="%(count)d of them start today.",
        action_label="See the %(count)d",
    )

    notice = bell.notice("stock.to_confirm", declared, {"count": 2})

    assert {name: notice[name] for name in ("icon", "severity", "title", "body", "action_label")} == {
        "icon": "ion:alert-outline",
        "severity": "danger",
        "title": "2 To confirm",
        "body": "2 of them start today.",
        "action_label": "See the 2",
    }


def test_a_plural_heading_follows_the_number_in_each_language():
    titles = {}
    for language in ("en", "es"):
        with override(language):
            for count in (1, 2):
                titles[language, count] = bell.notice("base.failed_events", bell.FAILED_EVENTS, {"count": count})["title"]

    assert titles == {
        ("en", 1): "1 failed event",
        ("en", 2): "2 failed events",
        ("es", 1): "1 evento caído",
        ("es", 2): "2 eventos caídos",
    }


def test_the_deadline_is_the_date_time_of_the_field_it_names():
    timed = counter(due="earliest")

    assert bell.notice("stock.to_confirm", timed, {"count": 1, "earliest": "2026-12-01T10:30:00+01:00"})["due"] == (
        dt.datetime(2026, 12, 1, 10, 30, tzinfo=dt.timezone(dt.timedelta(hours=1)))
    )
    assert bell.notice("stock.to_confirm", timed, {"count": 1, "earliest": None})["due"] is None
    assert bell.notice("stock.to_confirm", timed, {"count": 1})["due"] is None
    assert bell.notice("stock.to_confirm", counter(), {"count": 1, "earliest": "2026-12-01T10:30:00+01:00"})["due"] is None


@pytest.mark.parametrize(("row", "error"), [({"count": 1, "earliest": 20261201}, TypeError), ({"count": 1, "earliest": "soon"}, ValueError)])
def test_a_deadline_that_is_not_a_date_time_fails(row, error):
    with pytest.raises(error):
        bell.notice("stock.to_confirm", counter(due="earliest"), row)


@pytest.mark.parametrize("count", ["many", True, 1.5, None])
def test_a_number_that_is_not_a_whole_number_fails(count):
    with pytest.raises(TypeError, match="whole number"):
        bell.notice("stock.to_confirm", counter(), {"count": count})


def test_no_row_counts_zero():
    assert bell.notice("stock.to_confirm", counter(), None)["count"] == 0


@pytest.mark.parametrize(
    ("platform", "count", "english", "spanish"),
    [
        (
            bell.FAILED_EVENTS,
            2,
            ("danger", "2 failed events", "Review the events"),
            ("danger", "2 eventos caídos", "Revisar los eventos"),
        ),
        (
            bell.PLAN_LIMITS,
            1,
            ("warning", "1 plan limit to review", "See the plan’s usage"),
            ("warning", "1 límite del plan por revisar", "Ver el uso del plan"),
        ),
    ],
)
def test_the_platforms_own_counters_say_their_words_in_english_and_spanish(platform, count, english, spanish):
    said = {}
    for language in ("en", "es"):
        with override(language):
            notice = bell.notice(f"base.{platform.key}", platform, {"count": count})
        said[language] = (notice["severity"], notice["title"], notice["action_label"])
        assert notice["body"], f"base.{platform.key} says its consequence in {language}"

    assert (said["en"], said["es"]) == (english, spanish)


def module_counters():
    return [(config.label, counter) for config in module_configs() for counter in config.bell]


def test_there_are_module_counters_to_check():
    assert {label for label, _counter in module_counters()} >= {"appointment", "demo", "printing", "whatsapp_inbox"}


@pytest.mark.parametrize(("label", "declared"), module_counters(), ids=lambda value: getattr(value, "key", value))
def test_every_modules_counter_says_how_grave_it_is_and_its_words_in_english_and_spanish(label, declared):
    """A counter tells the problem in its heading, the consequence in its sentence and the action on its button."""
    assert declared.severity in BELL_SEVERITIES
    words = {}
    for language in ("en", "es"):
        with override(language):
            notice = bell.notice(f"{label}.{declared.key}", declared, {"count": 2})
        words[language] = (notice["title"], notice["body"], notice["action_label"])
        assert all(words[language]), f"{label}.{declared.key} leaves a word out in {language}"

    assert all(english != spanish for english, spanish in zip(*words.values(), strict=True)), words


def test_the_typed_bell_of_the_pages_says_what_the_server_sends():
    assert ts_fields("BellCounter", OPERATIONS_TS) == set(BellCounterOut.model_fields)
    assert ts_fields("BellCounters", OPERATIONS_TS) == set(BellCountersOut.model_fields)
