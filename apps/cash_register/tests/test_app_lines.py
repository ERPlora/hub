"""The lines another app records in a session (CASH_REGISTER-F18): Tips records the tips taken and paid out with
``cash_register.movement.add`` under its own name, and the session's summary and its X/Z report show them apart from
the cash brought in and taken out by hand. What came in shows by payment method and what went out of the drawer as
paid out; the expected cash is the one it always was (only cash counts). The cash register knows no such app by name.
"""

from live.models import OutboxEvent

from apps.cash_register.models import Movement
from apps.cash_register.tests.conftest import B, HUB_DB, ctx_for, open_session, run
from apps.printing.models import PrintJob
from base.tenancy.context import use_hub

pytestmark = HUB_DB

#: An installed app other than the cash register, as Tips is: the lines are named after the app that records them.
APP = "demo"


def add(type_: str, amount: int, method: str = "cash", *, app: str | None = APP, ctx=None):
    data = {"type": type_, "amount": amount, "method_type": method}
    if app is not None:
        data["app"] = app
    return run("cash_register.movement.add", data, ctx)


def summary(session, ctx=None):
    return run("cash_register.session.get", {"session_id": str(session.id)}, ctx).summary


def app_lines(session, ctx=None) -> list[tuple[str, str, int]] | None:
    lines = summary(session, ctx).app_lines
    return None if lines is None else [(line.app, line.label, line.amount) for line in lines]


def test_another_app_records_a_movement_as_its_own():
    open_session(10000)
    marked, by_hand = add("in", 500), add("in", 300, app=None)
    assert (marked.app, by_hand.app) == (APP, "")
    assert dict(Movement.objects.values_list("amount", "app")) == {500: APP, 300: ""}
    listed = run("cash_register.movement.list", {"session": run("cash_register.session.current").session.number})
    assert {row.amount: row.app for row in listed.rows} == {500: APP, 300: ""}


def test_the_movement_added_event_names_the_app_that_recorded_it():
    open_session(10000)
    add("in", 500)
    add("out", 100, app=None)
    payloads = OutboxEvent.objects.filter(name="cash_register.movement.added").order_by("created_at", "id")
    assert [(event.payload["amount"], event.payload["app"]) for event in payloads] == [(500, APP), (100, "")]


def test_its_lines_are_apart_from_cash_in_and_out_and_the_expected_cash_is_as_always():
    session = open_session(10000)
    add("in", 300, app=None)
    add("out", 100, app=None)
    add("in", 500)
    add("in", 700, "card")
    add("out", 200)
    figures = summary(session)
    assert (figures.total_cash_in, figures.total_cash_out) == (300, 100)
    assert app_lines(session) == [
        (APP, "Demo in cash", 500),
        (APP, "Demo by card", 700),
        (APP, "Demo paid out", -200),
    ]
    # Cash brought in and taken out by hand, the tip in cash and the one paid out: the card is not in the drawer.
    assert figures.expected_cash == 10000 + 300 - 100 + 500 - 200
    assert run("cash_register.session.current").session.expected_balance == figures.expected_cash


def test_other_payment_methods_are_a_line_only_when_there_were_some():
    session = open_session(10000)
    add("in", 500, "card")
    assert [label for _, label, _ in app_lines(session)] == ["Demo in cash", "Demo by card", "Demo paid out"]
    add("in", 400, "transfer")
    add("in", 100, "other")
    assert app_lines(session) == [
        (APP, "Demo in cash", 0),
        (APP, "Demo by card", 500),
        (APP, "Demo with other payment methods", 500),
        (APP, "Demo paid out", 0),
    ]
    assert summary(session).expected_cash == 10000


def test_what_goes_out_by_card_or_another_method_nets_into_its_line():
    session = open_session(10000)
    add("in", 700, "card")
    add("out", 200, "card")
    add("in", 400, "transfer")
    add("out", 100, "transfer")
    assert app_lines(session) == [
        (APP, "Demo in cash", 0),
        (APP, "Demo by card", 500),
        (APP, "Demo with other payment methods", 300),
        (APP, "Demo paid out", 0),
    ]


def test_each_app_has_lines_of_its_own_and_a_session_without_any_has_none():
    session = open_session(10000)
    assert app_lines(session) == []
    add("in", 300, app=None)
    assert app_lines(session) == []
    add("in", 200)
    add("in", 500, app="printing")
    assert [(app, amount) for app, _, amount in app_lines(session)] == [
        ("demo", 200), ("demo", 0), ("demo", 0), ("printing", 500), ("printing", 0), ("printing", 0),
    ]


def test_they_speak_the_readers_language():
    session = open_session(10000)
    add("in", 500)
    add("in", 700, "card")
    add("in", 100, "other")
    add("out", 200)
    spanish = ctx_for(language="es")
    assert [label for _, label, _ in app_lines(session, spanish)] == [
        "Demo en efectivo",
        "Demo con tarjeta",
        "Demo con otras formas de pago",
        "Demo pagadas",
    ]
    assert [label for _, label, _ in app_lines(session)][0] == "Demo in cash"


def test_a_blind_count_hides_them_from_the_cashier_as_every_total():
    run("cash_register.settings.update", {"require_blind_count": True})
    session = open_session(10000)
    add("in", 500)
    assert app_lines(session, ctx_for("hub_employee")) is None
    assert app_lines(session, ctx_for("hub_manager")) == [
        (APP, "Demo in cash", 500),
        (APP, "Demo by card", 0),
        (APP, "Demo paid out", 0),
    ]


def test_they_are_never_sales_and_stay_in_their_closed_session():
    session = open_session(10000)
    add("in", 500)
    add("out", 200)
    run("cash_register.session.close", {"session_id": str(session.id), "closing_balance": 10300})
    figures = summary(session)
    assert (figures.total_sales, figures.expected_cash, figures.difference) == (0, 10300, 0)
    assert app_lines(session) == [
        (APP, "Demo in cash", 500),
        (APP, "Demo by card", 0),
        (APP, "Demo paid out", -200),
    ]


def test_the_x_report_prints_them_apart_just_before_the_expected_cash(till):
    session = open_session(10000)
    add("in", 300, app=None)
    add("in", 500)
    add("in", 700, "card")
    add("out", 200)
    printed = run("cash_register.session.print", {"session_id": str(session.id)})
    job = PrintJob.objects.get(pk=printed.job_id)
    assert [(line["label"], line["amount"]) for line in job.document["transactions"]] == [
        ("Sales", 0.0),
        ("Cash sales", 0.0),
        ("Card sales", 0.0),
        ("Refunds", 0.0),
        ("Cash in", 3.0),
        ("Cash out", 0.0),
        ("Comps", 0.0),
        ("Demo in cash", 5.0),
        ("Demo by card", 7.0),
        ("Demo paid out", -2.0),
        ("Expected", 106.0),
    ]
    assert job.document["closing_balance"] == 106.0


def test_the_z_report_prints_them_in_the_language_of_who_prints(till):
    session = open_session(10000)
    add("in", 500)
    run("cash_register.session.close", {"session_id": str(session.id), "closing_balance": 10500})
    printed = run("cash_register.session.print", {"session_id": str(session.id)}, ctx_for(language="es"))
    labels = [line["label"] for line in PrintJob.objects.get(pk=printed.job_id).document["transactions"]]
    assert labels[labels.index("Invitaciones") + 1 : labels.index("Esperado")] == [
        "Demo en efectivo",
        "Demo con tarjeta",
        "Demo pagadas",
    ]


def test_the_lines_of_hub_b_are_nobody_in_hub_a(hub_a, hub_b):
    in_b = ctx_for(scope=B)
    with use_hub(hub_b):
        session_b = run("cash_register.session.open", {"opening_balance": 0}, in_b)
        add("in", 500, ctx=in_b)
        in_hub_b = app_lines(session_b, in_b)
    with use_hub(hub_a):
        session_a = open_session(10000)
        assert app_lines(session_a) == []
        assert summary(session_a).expected_cash == 10000
        assert not Movement.objects.filter(app=APP).exists()
    # Positive control: in hub B the line is there.
    assert in_hub_b == [(APP, "Demo in cash", 500), (APP, "Demo by card", 0), (APP, "Demo paid out", 0)]
