"""printing's operations, the only ones the print channel runs: called by name with the device's context, each
frame read as the operation's own input."""

import pydantic
from django.core.exceptions import NON_FIELD_ERRORS
from django.utils.translation import gettext
from live.errors import NotFound, OperationError
from live.operations import UnknownOperation, get

from base.ws_print.refusals import Refusal

DEVICE_GET = "printing.device.get"
PRINTER_GET = "printing.printer.get"
JOB_CLAIM = "printing.job.claim"
JOB_COMPLETE = "printing.job.complete"
JOB_FAIL = "printing.job.fail"
JOB_LIST = "printing.job.list"
#: The queue's answer when the job is another device's now: a plain no, never an error (as a job it no longer has).
NOT_YOURS = "printing.job_not_yours"
#: Whoever sets up the printers pairs a device by printing from it: its claim sets up a device new here, or adds the
#: printer it names, instead of refusing it (printing's WORKBOOK, PRINTING-F18).
PAIRS = "printing.manage_settings"


def _operation(name: str):
    try:
        return get(name)
    except UnknownOperation:
        raise Refusal("app_inactive", gettext("Printing is not on in this hub."), status=404) from None


def _validated(name: str, data: dict):
    op = _operation(name)
    try:
        return op.input.model_validate(data)
    except pydantic.ValidationError as exc:
        fields = {}
        for error in exc.errors():
            fields.setdefault(".".join(str(part) for part in error["loc"]) or NON_FIELD_ERRORS, error["msg"])
        raise Refusal("invalid_payload", gettext("Invalid frame."), status=422, fatal=False, fields=fields) from None


def _not_taken(exc: OperationError) -> bool:
    """Whether the queue did not take the answer because the job is not this device's (any more)."""
    return isinstance(exc, NotFound) or exc.code == NOT_YOURS
