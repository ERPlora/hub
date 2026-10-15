"""Write operations of the payment app: the methods (create, edit, deactivate, activate) and the
payments (record with their reference of the day, approve, send, complete, cancel).

The cases come from the old module's WORKFLOW and tests, with its silent no-ops turned into refusals:
a step from the wrong state, or a payment from a method that does not exist or is deactivated, says
why, changes nothing, spends no number and records no event (PAYMENTS-F02 to F05 «parcial»).
"""

import datetime as dt
import json
import uuid

import psycopg
import pytest
from django.utils import timezone, translation
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.payment.models import Payment, PaymentCounter, PaymentMethod

from .conftest import A, B, ctx_for, make_method, make_payment

pytestmark = pytest.mark.django_db

TODAY = dt.date(2026, 10, 14)
WAIT = 1.0
QUIET = 0.3


def run(name, data: dict, role="hub_admin", **ctx):
    op = get(name)
    return op(ctx_for(role, **ctx), op.input.model_validate(data))


def events() -> list[str]:
    return list(OutboxEvent.objects.order_by("id").values_list("name", flat=True))


def payload(name: str) -> dict:
    return OutboxEvent.objects.filter(name=name).latest("id").payload


@pytest.fixture(autouse=True)
def business_today(monkeypatch):
    """The business's day the references are numbered on."""
    monkeypatch.setattr(timezone, "localdate", lambda *args, **kwargs: TODAY)


@pytest.fixture
def bank():
    return make_method("BBVA account")


def record(method, actor: str = "tester", **fields):
    data = {
        "method_id": str(method.id),
        "payment_date": "2026-10-10",
        "amount": 12_50,
        "beneficiary_name": "Proveedor Norte SL",
    } | fields
    return run("payment.payment.create", data, actor=actor)


@pytest.mark.parametrize(
    ("name", "permission"),
    [
        ("payment.method.create", "payment.add_payment"),
        ("payment.method.update", "payment.add_payment"),
        ("payment.method.deactivate", "payment.add_payment"),
        ("payment.method.activate", "payment.add_payment"),
        ("payment.payment.create", "payment.add_payment"),
        ("payment.payment.approve", "payment.approve_payment"),
        ("payment.payment.mark_sent", "payment.add_payment"),
        ("payment.payment.mark_completed", "payment.add_payment"),
        ("payment.payment.cancel", "payment.approve_payment"),
    ],
)
def test_declarations(name, permission):
    op = get(name)
    assert (op.kind, op.permission, op.expose_api) == ("command", permission, True)


# ── Methods (PAYMENT-F01, F08) ────────────────────────────────────────────────────────────────


def test_creating_a_method(bank):
    method = run(
        "payment.method.create",
        {"name": "Cash  drawer", "method_type": "cash", "bank_account_ref": ""},
        actor="Ana",
    )
    assert (method.name, method.method_type, method.is_active) == (
        "Cash drawer",
        "cash",
        True,
    )
    stored = PaymentMethod.objects.get(pk=method.id)
    assert (stored.created_by, stored.updated_by) == ("Ana", "Ana")
    assert events() == ["payment.method.created"]
    assert payload("payment.method.created") == {
        "id": str(method.id),
        "name": "Cash drawer",
    }


def test_a_method_name_is_unique_whatever_the_case(bank):
    with pytest.raises(Conflict) as caught:
        run("payment.method.create", {"name": "bbva ACCOUNT"})
    assert caught.value.code == "payment.method_exists"
    assert caught.value.fields == {
        "name": "There is already a payment method with that name. Pick another name."
    }
    assert events() == []


def test_editing_a_method_changes_only_what_is_sent(bank):
    method = run(
        "payment.method.update",
        {"method": "bbva", "bank_account_ref": "ES91…1332"},
        actor="Bea",
    )
    assert (method.name, method.method_type, method.bank_account_ref) == (
        "BBVA account",
        "transfer",
        "*****1332",
    )
    assert PaymentMethod.objects.get(pk=bank.pk).bank_account_ref == "ES91…1332"
    assert PaymentMethod.objects.get(pk=bank.pk).updated_by == "Bea"
    assert events() == ["payment.method.updated"]
    assert payload("payment.method.updated") == {
        "id": str(bank.id),
        "name": "BBVA account",
        "changed": ["bank_account_ref"],
    }


def test_editing_a_method_with_nothing_new_records_nothing(bank):
    run("payment.method.update", {"id": str(bank.id), "name": "BBVA account"})
    assert events() == []


def test_renaming_a_method_to_another_ones_name_is_refused(bank):
    make_method("Cash drawer", method_type="cash")
    with pytest.raises(Conflict) as caught:
        run("payment.method.update", {"id": str(bank.id), "name": "CASH drawer"})
    assert caught.value.code == "payment.method_exists"
    assert "name" in caught.value.fields
    # Its own name in another case is not «another one's».
    assert (
        run("payment.method.update", {"id": str(bank.id), "name": "Bbva Account"}).name
        == "Bbva Account"
    )


def test_a_method_that_does_not_exist(bank):
    with pytest.raises(NotFound) as caught:
        run("payment.method.update", {"id": str(uuid.uuid7()), "name": "X"})
    assert caught.value.code == "payment.method_not_found"


def test_deactivating_and_activating_a_method(bank):
    assert run("payment.method.deactivate", {"id": str(bank.id)}).is_active is False
    with pytest.raises(Conflict) as again:
        run("payment.method.deactivate", {"id": str(bank.id)})
    assert again.value.code == "payment.method_already_inactive"
    assert run("payment.method.activate", {"method": "BBVA account"}).is_active is True
    with pytest.raises(Conflict) as active:
        run("payment.method.activate", {"id": str(bank.id)})
    assert active.value.code == "payment.method_already_active"
    assert events() == ["payment.method.deactivated", "payment.method.activated"]


def test_only_who_records_payments_manages_the_methods(bank):
    for name, data in [
        ("payment.method.create", {"name": "Card"}),
        ("payment.method.update", {"id": str(bank.id), "name": "Y"}),
        ("payment.method.deactivate", {"id": str(bank.id)}),
    ]:
        with pytest.raises(PermissionDenied):
            run(name, data, role="hub_employee")


# ── Recording a payment (PAYMENT-F02) ─────────────────────────────────────────────────────────


def test_recording_a_payment_gives_it_a_draft_and_the_reference_of_the_day(bank):
    payment = run(
        "payment.payment.create",
        {
            "method_id": str(bank.id),
            "payment_date": "2026-10-10",
            "amount": 12_50,
            "beneficiary_name": "  Proveedor Norte SL ",
            "concept": "Tintes",
            "supplier_invoice_ref": "F-118",
            "beneficiary_iban": "es91 2100 0418 4502 0005 1332",
        },
        actor="Ana",
    )
    assert payment.reference == "PAY-20261014-0001"
    assert (payment.status, payment.amount, payment.currency) == ("draft", 12_50, "EUR")
    assert payment.payment_date == dt.date(2026, 10, 10)
    assert (payment.method_name, payment.beneficiary_name) == (
        "BBVA account",
        "Proveedor Norte SL",
    )
    # Kept whole (compact, uppercase); the reply, like any row, shows it masked (whole: the get).
    assert Payment.objects.get(pk=payment.id).beneficiary_iban == "ES9121000418450200051332"
    assert payment.beneficiary_iban == "ES** **** **** **** **** 1332"
    assert (payment.created_by, payment.updated_by) == ("Ana", "Ana")
    assert payment.created_at is not None
    assert events() == ["payment.payment.created"]
    assert payload("payment.payment.created") == {
        "id": str(payment.id),
        "reference": "PAY-20261014-0001",
        "method_id": str(bank.id),
        "amount": 12_50,
        "currency": "EUR",
        "beneficiary_name": "Proveedor Norte SL",
        "payment_date": "2026-10-10",
        "status": "draft",
    }


def test_the_number_counts_by_day_and_the_day_is_the_recording_one(bank, monkeypatch):
    assert [record(bank).reference for _ in range(3)] == [
        "PAY-20261014-0001",
        "PAY-20261014-0002",
        "PAY-20261014-0003",
    ]
    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: dt.date(2026, 10, 15))
    # A payment dated a month ago still takes the day it is recorded on.
    assert record(bank, payment_date="2026-09-01").reference == "PAY-20261015-0001"


def test_past_9999_the_number_is_written_whole(bank):
    PaymentCounter.objects.create(day=TODAY, last=9999)
    assert record(bank).reference == "PAY-20261014-10000"


def test_the_method_can_be_said_by_its_name(bank):
    payment = run(
        "payment.payment.create",
        {
            "method": "bbva",
            "payment_date": "2026-10-10",
            "amount": 100,
            "beneficiary_name": "Ana",
        },
    )
    assert payment.method_id == bank.id


@pytest.mark.parametrize("field", ["method_id", "method"])
def test_a_method_that_does_not_exist_is_refused_under_its_field(bank, field):
    said = str(uuid.uuid7()) if field == "method_id" else "Santander"
    data = {
        "payment_date": "2026-10-10",
        "amount": 100,
        "beneficiary_name": "Ana",
        field: said,
    }
    with pytest.raises(InvalidPayload) as caught:
        run("payment.payment.create", data)
    assert caught.value.code == "payment.method_not_found"
    assert caught.value.fields == {
        field: "That payment method does not exist in this business."
    }
    # Nothing written, no number spent, nobody told (the old module did all three).
    assert Payment.objects.count() == 0
    assert not PaymentCounter.objects.filter(last__gt=0).exists()
    assert events() == []


def test_a_deactivated_method_is_refused(bank):
    bank.is_active = False
    bank.save()
    with pytest.raises(InvalidPayload) as caught:
        record(bank)
    assert caught.value.code == "payment.method_inactive"
    assert caught.value.fields == {
        "method_id": "That payment method is deactivated: pick an active one."
    }
    assert Payment.objects.count() == 0
    assert events() == []


def test_a_name_that_matches_several_methods_says_which(bank):
    make_method("Cash drawer", method_type="cash")
    make_method("Cash box", method_type="cash")
    with pytest.raises(Conflict) as caught:
        run(
            "payment.payment.create",
            {
                "method": "cash",
                "payment_date": "2026-10-10",
                "amount": 100,
                "beneficiary_name": "Ana",
            },
        )
    assert caught.value.code == "payment.method_ambiguous"


def test_without_a_currency_the_payment_is_in_the_business_currency(bank):
    # The old payments#38: the assistant or an API integration may leave it out.
    assert record(bank).currency == "EUR"
    assert record(bank, currency=None).currency == "EUR"
    assert record(bank, currency="  ").currency == "EUR"


def test_an_explicit_currency_wins(bank):
    assert record(bank, currency="usd").currency == "USD"
    assert record(bank, currency="JPY", amount=1999).amount == 1999


def test_an_employee_cannot_record_a_payment(bank):
    with pytest.raises(PermissionDenied):
        run(
            "payment.payment.create",
            {
                "method_id": str(bank.id),
                "payment_date": "2026-10-10",
                "amount": 1,
                "beneficiary_name": "A",
            },
            role="hub_employee",
        )


# ── The ladder (PAYMENT-F03, F04) ─────────────────────────────────────────────────────────────


def step(name, payment, role="hub_admin", **ctx):
    return run(name, {"reference": payment.reference}, role=role, **ctx)


def test_the_whole_ladder(bank):
    payment = record(bank)
    assert (
        payment.approved_by,
        payment.approved_at,
        payment.sent_at,
        payment.completed_at,
    ) == (
        "",
        None,
        None,
        None,
    )
    approved = step("payment.payment.approve", payment, actor="Boss")
    assert approved.status == "approved"
    assert Payment.objects.get(pk=payment.id).updated_by == "Boss"
    sent = step("payment.payment.mark_sent", payment, actor="Carla")
    assert sent.status == "sent"
    done = step("payment.payment.mark_completed", payment, actor="Carla")
    assert done.status == "completed"
    # Who approved stays, whoever moves it later (updated_by is only the last one).
    assert (done.created_by, done.approved_by, done.updated_by) == (
        "tester",
        "Boss",
        "Carla",
    )
    assert approved.approved_at <= done.sent_at <= done.completed_at
    assert (done.approved_at, done.sent_at) == (approved.approved_at, sent.sent_at)
    assert (done.cancelled_by, done.cancelled_at) == ("", None)
    assert events() == [
        "payment.payment.created",
        "payment.payment.approved",
        "payment.payment.sent",
        "payment.payment.completed",
    ]
    assert payload("payment.payment.completed") == {
        "id": str(payment.id),
        "reference": payment.reference,
        "status": "completed",
        "amount": 12_50,
        "currency": "EUR",
    }


@pytest.mark.parametrize(
    ("name", "status", "message"),
    [
        (
            "payment.payment.approve",
            "approved",
            "Only a draft payment can be approved; this one is Approved.",
        ),
        (
            "payment.payment.mark_sent",
            "draft",
            "Only an approved payment can be marked as sent; this one is Draft.",
        ),
        (
            "payment.payment.mark_completed",
            "approved",
            "Only a sent payment can be marked as completed; this one is Approved.",
        ),
        (
            "payment.payment.mark_completed",
            "cancelled",
            "Only a sent payment can be marked as completed; this one is Cancelled.",
        ),
    ],
)
def test_a_step_from_the_wrong_state_is_refused_and_changes_nothing(
    bank, name, status, message
):
    payment = make_payment(bank, status=status)
    with pytest.raises(Conflict) as caught:
        step(name, payment)
    assert caught.value.code == "payment.invalid_transition"
    assert caught.value.message == message
    assert Payment.objects.get(pk=payment.pk).status == status
    # The old module emitted the event anyway, and «completed» fired automations.
    assert events() == []


def test_the_refusal_reads_in_spanish(bank):
    payment = make_payment(bank, status="approved")
    with translation.override("es"), pytest.raises(Conflict) as caught:
        step("payment.payment.approve", payment)
    assert (
        caught.value.message
        == "Solo se puede aprobar un pago en borrador; este está Aprobado."
    )


def test_an_unknown_payment(bank):
    with pytest.raises(NotFound) as caught:
        run("payment.payment.approve", {"id": str(uuid.uuid7())})
    assert caught.value.code == "payment.payment_not_found"


def test_who_records_cannot_approve(bank):
    payment = record(bank)
    recorder = {"payment.view_payment", "payment.add_payment"}
    with pytest.raises(PermissionDenied):
        step("payment.payment.approve", payment, permissions=recorder)
    # Sending and completing are the recorder's (as in the old module).
    make_payment(bank, reference="PAY-X", status="approved")
    assert (
        run(
            "payment.payment.mark_sent", {"reference": "PAY-X"}, permissions=recorder
        ).status
        == "sent"
    )


def test_an_approver_may_approve_what_they_recorded_and_both_stay_written(bank):
    # The separation is by permission (the market's, e.g. QuickBooks: a bill its approver created is
    # approved): a business of one person must still be able to pay. Who recorded and who approved
    # stay on the payment either way (WORKBOOK «Quién puede qué»).
    payment = record(bank, actor="Ana")
    approved = step("payment.payment.approve", payment, actor="Ana")
    assert (approved.status, approved.created_by, approved.approved_by) == (
        "approved",
        "Ana",
        "Ana",
    )


# ── Cancelling (PAYMENT-F05) ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["draft", "approved", "sent"])
def test_cancelling_keeps_the_reason_apart_from_the_concept(bank, status):
    payment = make_payment(bank, status=status, concept="Tintes")
    cancelled = run(
        "payment.payment.cancel",
        {"id": str(payment.id), "reason": " Duplicated "},
        actor="Boss",
    )
    assert (cancelled.status, cancelled.cancel_reason, cancelled.concept) == (
        "cancelled",
        "Duplicated",
        "Tintes",
    )
    assert Payment.objects.get(pk=payment.pk).updated_by == "Boss"
    assert cancelled.cancelled_by == "Boss"
    assert cancelled.cancelled_at is not None
    assert events() == ["payment.payment.cancelled"]
    assert payload("payment.payment.cancelled") == {
        "id": str(payment.id),
        "reference": payment.reference,
        "status": "cancelled",
        "amount": payment.amount,
        "currency": "EUR",
    }


@pytest.mark.parametrize("status", ["completed", "cancelled"])
def test_a_finished_payment_cannot_be_cancelled(bank, status):
    payment = make_payment(bank, status=status)
    with pytest.raises(Conflict) as caught:
        run("payment.payment.cancel", {"id": str(payment.id), "reason": "late"})
    assert caught.value.code == "payment.not_cancellable"
    assert caught.value.message == "This payment can no longer be cancelled."
    assert Payment.objects.get(pk=payment.pk).cancel_reason == ""
    assert events() == []


def test_cancelling_needs_the_approve_permission(bank):
    payment = record(bank)
    with pytest.raises(PermissionDenied):
        run(
            "payment.payment.cancel",
            {"id": str(payment.id), "reason": "x"},
            permissions={"payment.view_payment", "payment.add_payment"},
        )


# ── Notifications: after the COMMIT, on the channel of the command's scope only ───────────────


@pytest.fixture
def listen(db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=WAIT, stop_after=None):
    return [
        (note.channel, json.loads(note.payload))
        for note in session.notifies(timeout=timeout, stop_after=stop_after)
    ]


@pytest.mark.django_db(transaction=True)
def test_a_payment_recorded_in_b_notifies_the_channel_of_b_only(listen):
    method = make_method()
    on_a, on_b = listen(A), listen(B)

    run(
        "payment.payment.create",
        {
            "method_id": str(method.id),
            "payment_date": "2026-10-10",
            "amount": 100,
            "beneficiary_name": "Proveedor",
        },
        scope=B,
    )

    assert received(on_b, stop_after=1) == [
        (channel_for(B), {"events": ["payment.payment.created"]})
    ]
    assert received(on_a, timeout=QUIET) == []


@pytest.mark.django_db(transaction=True)
def test_a_refused_step_notifies_nobody(listen):
    payment = make_payment(make_method(), status="completed")
    on_a, on_b = listen(A), listen(B)
    with pytest.raises(Conflict):
        run("payment.payment.approve", {"id": str(payment.id)}, scope=B)
    assert received(on_b, timeout=QUIET) == []
    assert received(on_a, timeout=QUIET) == []
