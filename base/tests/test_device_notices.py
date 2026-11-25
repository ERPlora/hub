"""The device's notices: each row of a notice's query that passes its ``when``, told with its texts filled in."""

from types import SimpleNamespace

from live.context import OperationContext, Scope
from live.meta import DeviceNotice, SetupCheck

from base import home

BOOKED = DeviceNotice(
    key="booked",
    operation="things.booking.list",
    title=("{customer} booked", "A booking"),
    route="/things/{id}",
    body=("{service}", "{at:%H:%M}"),
    when=(SetupCheck(field="state", equals="booked"),),
)


def person(*permissions):
    return OperationContext(scope=Scope("host", "a"), actor="ana", permissions=frozenset(permissions), language="en")


def booking(number, at, customer="Ana", state="booked"):
    return {"id": number, "at": at, "customer": customer, "service": "", "state": state}


def test_a_row_is_told_with_its_texts_filled_in_and_its_empty_parts_left_out():
    assert home.device_notices.told("things.booked", "things", BOOKED, booking(7, "2026-10-23T08:00:00")) == {
        "key": "things.booked",
        "app": "things",
        "id": "7",
        "at": "2026-10-23T08:00:00",
        "title": "Ana booked",
        "body": "08:00",
        "route": "/things/7",
    }


def test_the_title_is_the_first_whose_fields_are_all_filled():
    told = home.device_notices.told("things.booked", "things", BOOKED, booking(7, "2026-10-23T08:00:00", customer=" "))

    assert told["title"] == "A booking"


def test_the_rows_that_pass_the_notice_s_when_are_told_the_newest_first(monkeypatch):
    rows = [
        booking(1, "2026-10-23T08:00:00"),
        booking(2, "2026-10-23T09:00:00"),
        booking(3, "2026-10-23T10:00:00", state="cancelled"),
    ]
    monkeypatch.setattr(home.device_notices, "rows_of", lambda ctx, operation, params: rows)

    notices = home.device_notices.device_notices(person(), [SimpleNamespace(label="things", notices=[BOOKED])])

    assert [notice["id"] for notice in notices] == ["2", "1"]


def test_whoever_lacks_a_notice_s_permission_neither_hears_it_nor_is_told_its_rows(monkeypatch):
    paid = DeviceNotice(key="paid", operation="things.payment.list", title=("Paid",), route="/", permission="things.view")
    module = SimpleNamespace(label="things", notices=[BOOKED, paid])
    monkeypatch.setattr(home.device_notices, "rows_of", lambda ctx, operation, params: [{"id": 1, "at": "2026-10-23T08:00:00"}])

    assert home.device_notices.notice_sources(person(), [module]) == ["things.booked"]
    assert home.device_notices.notice_sources(person("things.view"), [module]) == ["things.booked", "things.paid"]
    assert home.device_notices.device_notices(person(), [module]) == []
    assert [notice["key"] for notice in home.device_notices.device_notices(person("things.view"), [module])] == ["things.paid"]
