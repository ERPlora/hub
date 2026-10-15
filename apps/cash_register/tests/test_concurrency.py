"""Two devices at once (CASH_REGISTER-F03, F05, F09): real sessions in threads, real row locks.

Two opens at once open one session (the other is told one is open) and burn one number; two closes at
once close it once (the other is told it is closed); a cash-out racing the close either lands before it
(and is in the frozen expected) or is refused, never written into a closed shift.
"""

import threading

import pytest
from django.db import connection
from live.errors import OperationError

from apps.cash_register.models import Movement, Session, SessionCounter
from apps.cash_register.tests.conftest import run

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def factory_data(transactional_db):
    """A transactional test starts from a flushed database: sale's factory payment methods are planted
    again, as its migration does (idempotent)."""
    from importlib import import_module

    from django.apps import apps as registry

    with connection.schema_editor() as editor:
        import_module("apps.sale.migrations.0002_factory_payment_methods").plant(
            registry, editor
        )


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except OperationError as error:
            results[index] = error
        except Exception as error:  # an unexpected failure is reported by the test
            results[index] = error
        finally:
            connection.close()

    threads = [
        threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def codes(results) -> list:
    return sorted(getattr(result, "code", "ok") for result in results)


def opening(balance: int):
    return lambda: run("cash_register.session.open", {"opening_balance": balance})


def closing(session, counted: int):
    """The close as the screen sends it: naming the session of its row."""
    return lambda: run(
        "cash_register.session.close", {"session_id": str(session.id), "closing_balance": counted}
    )


def test_two_opens_at_once_open_one_session_and_burn_one_number():
    results = at_once(opening(10000), opening(20000))
    assert codes(results) == ["cash_register.session_already_open", "ok"]
    assert Session.objects.count() == 1
    assert SessionCounter.objects.get().last == 1


def test_two_closes_at_once_close_the_session_once():
    session = run("cash_register.session.open", {"opening_balance": 10000})
    results = at_once(closing(session, 10000), closing(session, 9000))
    assert codes(results) == ["cash_register.session_not_open", "ok"]
    session = Session.objects.get()
    winner = next(result for result in results if not isinstance(result, Exception))
    assert (session.status, session.closing_balance) == (
        "closed",
        winner.closing_balance,
    )


def test_a_cash_out_racing_the_close_never_lands_in_a_closed_shift():
    opened = run("cash_register.session.open", {"opening_balance": 10000})
    results = at_once(
        lambda: run(
            "cash_register.movement.add",
            {"session_id": str(opened.id), "type": "out", "amount": 1000},
        ),
        closing(opened, 9000),
    )
    session = Session.objects.get()
    moved = Movement.objects.filter(type="out").exists()
    if moved:
        # The movement went first: the close froze it.
        assert session.expected_balance == 9000
    else:
        assert getattr(results[0], "code", None) == "cash_register.session_not_open"
        assert session.expected_balance == 10000
