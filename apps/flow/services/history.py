"""What the History of the runs keeps: an erased customer is forgotten in every run that names her
(``flow.customer.erase``), and the finished runs go after 90 days (``flow.run.prune``)."""

import datetime as dt
import logging

from django.db.models import Q, TextField
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.operations import operation

from apps.flow.models import Flow, FlowRun, Question
from apps.flow.queries.reads import SYSTEM
from apps.flow.queries.reasons import say
from apps.flow.queries.runs import RESUME_DAYS, resume_problem
from apps.flow.schemas import ChangedOut, CustomerErasedIn, DueIn, DueOut

from .engine import _finish, _own, _remember_read

logger = logging.getLogger(__name__)

#: How long the history keeps a finished run (the old Hub's 90 days, fixed, for every hub).
HISTORY_DAYS = 90
#: At most this many runs go per pass: bounded, never one mass delete at the busiest hour.
PRUNE_BATCH = 500
#: The runs that can no longer go on: what the history may forget (waiting and running ones never).
FINISHED = (
    FlowRun.Status.SUCCEEDED,
    FlowRun.Status.STOPPED,
    FlowRun.Status.FAILED,
    FlowRun.Status.CANCELLED,
)

#: The runs that may still go on with what they keep (FLOW-F23, F27, F28); one stopped by an error goes on only if
#: it is resumed (FLOW-F24, ``resume_problem``).
GOING_ON = (FlowRun.Status.WAITING, FlowRun.Status.CALLING, FlowRun.Status.ASKING)


def _naming(card: str):
    """The runs whose kept data name the card ``card``: its id in what started them (the notice of Customers or of
    another app, ``customer_id``), in what their steps read (the card itself, a sale, an appointment…) or among the
    ids of what they read and have forgotten (``read_ids``: one that ended, started by hand or by a schedule)."""
    return FlowRun.objects.annotate(
        input_text=Cast("input", TextField()), outputs_text=Cast("outputs", TextField())
    ).filter(Q(input_text__contains=card) | Q(outputs_text__contains=card) | Q(read_ids__contains=[card]))


#: What a free text of a run's History says once a customer it named is erased (CUSTOMER-F16), in the automation's
#: language like the rest of what it keeps.
ERASED_TEXT = _("[erased with the customer's personal data]")


def _forgotten_step(entry: dict, erased: str) -> dict:
    """A step of a run's History without its free texts: an answer's note, what the assistant answered and, of a step
    that failed, what another app answered (also of each field) and its technical text (a failure of the engine's own
    is said again from its reason, which names no person); what happened stays."""
    forgotten = {name: erased if name in ("note", "text") and value else value for name, value in entry.items()}
    error = entry.get("error")
    if isinstance(error, dict):
        error = {name: value for name, value in error.items() if name != "technical"}
        if not error.get("reason") and error.get("message"):
            error["message"] = erased
        if isinstance(error.get("fields"), dict):
            # Which field was refused stays; what was said of it may quote what the step sent (her name).
            error["fields"] = {field: erased if said else said for field, said in error["fields"].items()}
        forgotten["error"] = error
    return forgotten


def _forget_texts(run: FlowRun) -> bool:
    """Forgets, in the automation's language, the free texts of ``run``'s History that may name a person (its steps,
    the title of the question in a «no» or a silence, what another app answered) and those of its questions;
    ``True`` when something changed. Called with the run locked."""
    erased = str(ERASED_TEXT)
    kept = (run.log, run.error_reason, run.error_message)
    run.log = [_forgotten_step(entry, erased) for entry in run.log]
    values = run.error_reason.get("values") or {}
    if values.get("title"):
        run.error_reason = {**run.error_reason, "values": {**values, "title": erased}}
        run.error_message = say(run.error_reason, run.error_message)
    elif not run.error_reason and run.error_message:
        run.error_message = erased
    # Filled in from what the steps read (``{{steps.s1.name}}``) or written by whoever answered: she may be in them.
    texts = Question.objects.filter(run=run).exclude(title="", details="", note="")
    return bool(texts.update(title="", details="", note="")) or kept != (run.log, run.error_reason, run.error_message)


@operation(
    "flow.customer.erase",
    kind="command",
    permission=SYSTEM,
    input=CustomerErasedIn,
    output=ChangedOut,
    ai={
        "description": "System only: the platform's reaction to customer.customer.erased (Customers): every run that "
        "could still go on with that customer's data (waiting, calling another system, asking someone, or stopped "
        "by an error and resumable) is cancelled, saying why; every run naming the customer, also one that has "
        "ended, forgets what its steps read and the free texts of its history and of its questions (an answer's "
        "note, what the assistant or another app answered, the title of a question).",
        "risk": "normal",
    },
)
def erase_customer(ctx: OperationContext, data: CustomerErasedIn) -> dict:
    now = timezone.now()
    # Every run that names the card, however it is: also one that has ended keeps its History 90 days (FLOW-F16).
    naming = _naming(str(data.id))
    found = list(naming.values_list("pk", "flow_id"))
    if not found:
        return {"changed": 0}
    # The order of every write: the automations, then their runs, then their questions.
    list(
        Flow.objects.select_for_update()
        .filter(pk__in={flow_id for _pk, flow_id in found})
        .order_by("id")
        .values_list("pk", flat=True)
    )
    changed = 0
    for run in (
        naming.filter(pk__in=[pk for pk, _flow_id in found])
        .select_related("flow")
        .select_for_update(of=("self",))
        .order_by("id")
    ):
        goes_on = run.status in GOING_ON or (
            run.status == FlowRun.Status.FAILED and resume_problem(run, now) is None
        )
        with translation.override(run.flow.language):
            if goes_on:
                Question.objects.filter(run=run, status=Question.Status.PENDING).update(
                    status=Question.Status.CANCELLED, decided_at=now
                )
                _forget_texts(run)
                _finish(ctx, run, FlowRun.Status.CANCELLED, now, _own("flow.customer_erased"))
                changed += 1
                continue
            # It can no longer go on: what its steps read and its free texts go, its history stays as it ended.
            read = bool(run.outputs)
            run.outputs = {}
            if _forget_texts(run) or read:
                run.save(update_fields=["outputs", "log", "error_reason", "error_message"])
                changed += 1
    return {"changed": changed}


@operation(
    "flow.run.prune",
    kind="command",
    permission=SYSTEM,
    input=DueIn,
    output=DueOut,
    ai={
        "description": "System only, a scheduled task, every hour: deletes the finished runs older than 90 days "
        "(the history keeps 90 days); a run that is waiting or running is never touched.",
        "risk": "normal",
    },
)
def prune_runs(ctx: OperationContext, data: DueIn) -> dict:
    cutoff = timezone.now() - dt.timedelta(days=HISTORY_DAYS)
    doomed = list(
        FlowRun.objects.filter(status__in=FINISHED)
        .annotate(ended=Coalesce("finished_at", "started_at"))
        .filter(ended__lt=cutoff)
        .order_by("ended", "id")
        .values_list("pk", flat=True)[:PRUNE_BATCH]
    )
    # A failure older than RESUME_DAYS can no longer be resumed: what its steps read goes (FLOW-F24), its ids stay.
    expired = FlowRun.objects.filter(
        status=FlowRun.Status.FAILED,
        finished_at__lt=timezone.now() - dt.timedelta(days=RESUME_DAYS),
    ).exclude(outputs={})
    for failed in expired.select_for_update(skip_locked=True).order_by("id")[:PRUNE_BATCH]:
        _remember_read(failed)
        failed.outputs = {}
        failed.save(update_fields=["outputs", "read_ids"])
    if doomed:
        FlowRun.objects.filter(pk__in=doomed).delete()
        # Counted: a silent prune cannot be told from lost data the day somebody looks for an old run.
        logger.info(
            "flow: deleted %d finished runs older than %d days", len(doomed), HISTORY_DAYS
        )
    return {"count": len(doomed)}
