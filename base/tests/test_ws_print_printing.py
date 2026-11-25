"""What ``/ws/print`` calls of printing: its operations by name, a frame read as their own input, and the answers
that only mean «this job is not this device's»."""

import uuid

import pytest
from live.errors import Conflict, NotFound, PermissionDenied

from base.ws_print.printing import JOB_CLAIM, NOT_YOURS, _not_taken, _operation, _validated
from base.ws_print.refusals import Refusal


def test_an_operation_printing_does_not_register_means_printing_is_not_on():
    with pytest.raises(Refusal) as refused:
        _operation("printing.job.vanish")

    assert (refused.value.code, refused.value.status, refused.value.fatal) == ("app_inactive", 404, True)


def test_a_frame_is_read_as_the_operations_own_input():
    printer = str(uuid.uuid4())

    data = _validated(JOB_CLAIM, {"printers": [printer], "device": "till-1"})

    assert isinstance(data, _operation(JOB_CLAIM).input)
    assert ([str(p) for p in data.printers], data.device) == ([printer], "till-1")


def test_a_frame_its_input_refuses_answers_invalid_payload_naming_the_field_and_the_socket_stays():
    with pytest.raises(Refusal) as refused:
        _validated(JOB_CLAIM, {"printers": [], "device": "till-1"})

    refusal = refused.value
    assert (refusal.code, refusal.status, refusal.fatal) == ("invalid_payload", 422, False)
    assert list(refusal.fields) == ["printers"]


@pytest.mark.parametrize(
    ("error", "not_taken"),
    [
        (NotFound("That job is gone."), True),
        (Conflict("Another device has it.", code=NOT_YOURS), True),
        (Conflict("It was printed already.", code="printing.job_done"), False),
        (PermissionDenied("You may not print here."), False),
    ],
)
def test_only_a_job_that_is_gone_or_another_devices_is_not_taken(error, not_taken):
    assert _not_taken(error) is not_taken
