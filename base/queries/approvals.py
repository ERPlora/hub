"""A manager's approvals: the list, its export and who may approve (``base.approval.*``)."""

import csv
import io

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext, pgettext
from live.context import OperationContext
from live.meta import all_live_app_configs
from live.operations import AI, operation

from base import access, approvals as approval_rules, blueprint, business
from base.models import Approval
from base.permissions import ADMINISTER_HUB, VIEW_HOME, permissions_for
from base.schemas.approvals import ApprovalExportIn, ApprovalExportOut, ApprovalListIn, ApprovalListOut, ApproversIn, ApproversOut

from .access import access_settings, pin_people
from .people import face_name


# ── People and permissions: a manager's approval ───────────────────────────────────────────────────────────────────

#: Employees › Approvals shows the newest 500.
APPROVALS_SHOWN = 500


def holds(user, scope, permission: str) -> bool:
    """Whether ``user`` holds ``permission`` on ``scope``, as ``@operation`` asks it (wildcards included)."""
    return OperationContext(scope=scope, actor=user, permissions=permissions_for(user, scope)).has(permission)


def approval_action(operation: str, figures: dict | None = None, currency: str | None = None) -> str:
    """What an approval approved, in words: the app's own (with the ``figures`` of what it let through, in the active
    language and in ``currency``, when its app says it with them), else «An action of <app>», else that nobody names
    it now."""
    found = approval_rules.approvable(operation)
    if found is not None:
        return approval_rules.label_of(found[0], figures, currency=currency) or found[1]
    config = next((c for c in all_live_app_configs() if c.label == operation.split(".", 1)[0]), None)
    if config is not None:
        return gettext("An action of %(app)s") % {"app": config.verbose_name}
    return gettext("An action no app names now")


@operation(
    "base.approval.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=ApprovalListIn,
    output=ApprovalListOut,
    ai=AI(
        description=(
            "Lists the actions a manager approved with their PIN or badge, the newest first: when, what in words, who "
            "asked, who approved, how, and whether the approval was used."
        ),
        asks={
            "en": (
                "who approved that discount?",
                "show me today's approvals",
                "what did the manager authorise with their PIN?",
            ),
            "es": (
                "¿quién aprobó la anulación de ayer?",
                "enséñame las aprobaciones de hoy",
                "¿qué ha autorizado el encargado con su PIN?",
            ),
        },
    ),
)
def approval_list(ctx: OperationContext, data: ApprovalListIn) -> dict:
    """Employees › Approvals: the record of approvals, read only."""
    rows = list(Approval.objects.order_by("-created_at", "-id")[:APPROVALS_SHOWN])
    currency = approval_rules.currency_of(ctx.scope) if any(row.figures for row in rows) else None
    return {
        "approvals": [
            {
                "id": row.id,
                "at": row.created_at,
                "action": approval_action(row.operation, row.figures, currency),
                "operation_label": approval_action(row.operation),
                "operation": row.operation,
                "requested_by": row.requested_by_name,
                "approved_by": row.approved_by_name,
                "way": row.way,
                "used": row.used_at is not None,
                "used_at": row.used_at,
            }
            for row in rows
        ]
    }


def _approvals_kept(data: ApprovalExportIn, currency: str | None):
    """The record with the list's search and filters: the days in the business's time zone, the search on what the list
    shows (the action in words, with its figures, and the two names), in any case."""
    rows = Approval.objects.order_by("-created_at", "-id")
    if data.at_from:
        rows = rows.filter(created_at__date__gte=data.at_from)
    if data.at_to:
        rows = rows.filter(created_at__date__lte=data.at_to)
    if data.operation:
        rows = rows.filter(operation=data.operation)
    if data.way:
        rows = rows.filter(way=data.way)
    if data.used is not None:
        rows = rows.filter(used_at__isnull=not data.used)
    needle = data.search.strip()
    if needle:
        named = [
            name
            for name in rows.order_by().values_list("operation", flat=True).distinct()
            if needle.lower() in approval_action(name).lower()
        ]
        figured = [
            pk
            for pk, name, figures in rows.filter(figures__isnull=False).values_list("id", "operation", "figures")
            if needle.lower() in approval_action(name, figures, currency).lower()
        ]
        rows = rows.filter(
            Q(requested_by_name__icontains=needle)
            | Q(approved_by_name__icontains=needle)
            | Q(operation__in=named)
            | Q(id__in=figured)
        )
    return rows


def _approval_cell(text: str) -> str:
    """A cell a spreadsheet must not run: an apostrophe in front of what it would read as a formula."""
    return f"'{text}" if text.startswith(blueprint.datasets.FORMULA_STARTS) else text


@operation(
    "base.approval.export",
    kind="query",
    permission=ADMINISTER_HUB,
    input=ApprovalExportIn,
    output=ApprovalExportOut,
    ai=AI(
        description=(
            "Exports the record of approvals as a CSV file, the newest first, with the search and the filters of "
            "Employees › Approvals (days, action, PIN or badge, used or not): when, what in words, who approved, who "
            "asked, how and whether it was used. It names people of the business."
        ),
        asks={
            "en": ("show me last month's manager approvals", "list the approvals made with a badge this week"),
            "es": ("enséñame las autorizaciones del mes pasado", "¿qué se aprobó con placa esta semana?"),
        },
    ),
)
def approval_export(ctx: OperationContext, data: ApprovalExportIn) -> dict:
    """Employees › Approvals › «Export CSV» (BASE-F85): every approval the list's search and filters keep, not only the
    newest it shows, in words and in the person's language."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(
        [
            pgettext("approvals export", "When"),
            pgettext("approvals export", "Action"),
            pgettext("approvals export", "Approved by"),
            pgettext("approvals export", "Asked by"),
            pgettext("approvals export", "With"),
            pgettext("approvals export", "State"),
        ]
    )
    count = 0
    currency = approval_rules.currency_of(ctx.scope) if Approval.objects.filter(figures__isnull=False).exists() else None
    for row in _approvals_kept(data, currency):
        writer.writerow(
            [
                timezone.localtime(row.created_at, business.business_zone()).strftime("%Y-%m-%d %H:%M"),
                _approval_cell(approval_action(row.operation, row.figures, currency)),
                _approval_cell(row.approved_by_name),
                _approval_cell(row.requested_by_name),
                str(Approval.Way(row.way).label),
                pgettext("approvals export", "Used") if row.used_at else pgettext("approvals export", "Not used"),
            ]
        )
        count += 1
    return {"filename": "approvals.csv", "content_type": "text/csv", "rows": count, "csv": buffer.getvalue()}


@operation(
    "base.approval.approvers",
    kind="query",
    permission=VIEW_HOME,
    input=ApproversIn,
    output=ApproversOut,
    ai={
        "description": "Not an assistant tool: names who of the business can approve one refused action with their "
        "PIN (they hold its permission and have a PIN), for the approval dialog."
    },
)
def approval_approvers(ctx: OperationContext, data: ApproversIn) -> dict:
    """«Who approves it?»: the people of the business with a PIN who may do the action themselves, by name;
    nobody for an action no app names."""
    found = approval_rules.approvable(data.operation)
    pin_length = access.pin_length_or_default(access_settings().pin_length)
    if found is None:
        return {"people": [], "pin_length": pin_length}
    op = found[0]
    people = [
        {"id": str(credential.pk), "name": face_name(user), "initials": access.initials(face_name(user))}
        for credential, user in pin_people(ctx.scope.key)
        if holds(user, ctx.scope, op.permission)
    ]
    return {"people": sorted(people, key=lambda person: person["name"].casefold()), "pin_length": pin_length}
