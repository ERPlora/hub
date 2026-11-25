"""The refusals of ``/ws/print``: the ``error`` frame each one sends, and the refusal an operation's failure becomes,
fatal only when no retry fixes it."""

import pytest
from live.errors import AppInactive, Conflict, OperationError, PermissionDenied, Unauthorized

from base.operations import HostClosed
from base.ws_print.refusals import Refusal, _refusal_of


def test_a_refusal_is_an_error_frame_that_names_its_fields_only_when_it_has_any():
    plain = Refusal("print.not_ready", "Say hello first.", status=400)
    detailed = Refusal("invalid_payload", "Invalid frame.", status=422, fatal=False, fields={"device": "Too long."})

    assert plain.frame() == {"type": "error", "code": "print.not_ready", "message": "Say hello first."}
    assert detailed.frame() == {
        "type": "error",
        "code": "invalid_payload",
        "message": "Invalid frame.",
        "fields": {"device": "Too long."},
    }


def test_an_operation_refused_with_a_401_is_unauthenticated_as_in_the_old_hub():
    refusal = _refusal_of(Unauthorized("Sign in again."))

    assert (refusal.code, refusal.message, refusal.status, refusal.fatal) == ("unauthenticated", "Sign in again.", 401, True)


@pytest.mark.parametrize(
    "error",
    [
        PermissionDenied("You may not print here."),
        AppInactive("Printing is off."),
        OperationError("Printing needs a plan.", code="app_entitlement_blocked", status=402),
        HostClosed("The business is suspended.", code="base.hub_suspended", status=402),
    ],
)
def test_a_refusal_no_retry_fixes_closes_the_socket_with_the_code_it_carries(error):
    refusal = _refusal_of(error)

    assert (refusal.code, refusal.status, refusal.fatal) == (error.code, error.status, True)


def test_any_other_refusal_is_answered_with_its_fields_and_the_socket_stays():
    error = Conflict("Another device has it.", code="printing.job_not_yours", fields={"job_id": "Not yours."})

    refusal = _refusal_of(error)

    assert (refusal.code, refusal.status, refusal.fatal, refusal.fields) == (
        "printing.job_not_yours",
        409,
        False,
        {"job_id": "Not yours."},
    )
