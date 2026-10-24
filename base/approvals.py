"""A manager's PIN lets one refused command through (APP-BASE-5; BASE-G136, the old hub's HUB_SHELL-F51): without the ORM.

An app names the commands of its own a manager may approve on the spot, with what is approved in words:
``approvals = {"sale.sale.void": _("Void a sale")}`` in its ``LiveAppConfig`` (a module cannot name another's, a query
is never approved). :func:`install` puts the approval's door (:class:`ApprovalDoor`) in front of the session's on every
route of a command that needs a caller. For a person who may run the command, or a command nobody names, it changes
nothing. For a person who may not, it answers ``requires_elevation`` (:class:`ApprovalRequired`, 403) with what is
approved and the fingerprint of that very request (:func:`fingerprint`: this business, the method, the path and the
body); somebody of the business who holds the permission approves it (``base.approval.approve``, their PIN or badge,
the PIN pad's hash and brakes) and the hub hands back a pass (``X-Elevation-Token``) of one use, for two minutes
(:data:`PASS_SECONDS`). The command repeated with it goes through once, with that one permission more: the door spends
the pass (``base.approval.spend``) and marks the request (:class:`Approved`), and ``base.operations`` adds the
permission to that call's context. A pass that is spent, late, forged, another person's, another command's or another
request's is the same question again, never a way in.
"""

import hashlib
import json
import secrets
from dataclasses import dataclass

from django.apps import apps
from django.http import HttpRequest
from django.utils.translation import gettext
from live.errors import OperationError
from live.operations import Operation, get
from ninja import NinjaAPI
from ninja.security import django_auth

from base.api_keys import KeyDoor

TOKEN_PREFIX = "elev_"
#: The header a pass travels in (the SDK's ``ELEVATION_TOKEN_HEADER``).
HEADER = "X-Elevation-Token"
#: How long a pass lasts: two minutes, as the old hub's.
PASS_SECONDS = 120
#: The code of the question, the old hub's, which its SDK knows.
REQUIRES_ELEVATION = "requires_elevation"


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def label_of(op: Operation | None) -> str | None:
    """What approving ``op`` approves, in words, when its own app names it and it is a command with a permission."""
    if op is None or op.kind != "command" or not op.permission:
        return None
    try:
        config = apps.get_app_config(op.app_label)
    except LookupError:
        return None
    named = getattr(config, "approvals", None)
    label = named.get(op.name) if isinstance(named, dict) else None
    return str(label) if label else None


def approvable(name: str) -> tuple[Operation, str] | None:
    """The operation called ``name`` and what approving it approves; ``None`` when no app names it."""
    try:
        op = get(name)
    except Exception:
        return None
    label = label_of(op)
    return None if label is None else (op, label)


def fingerprint(request: HttpRequest, business: str) -> str:
    """The SHA-256 of one request of ``business``: its method, path and body (JSON in a canonical order)."""
    raw = request.body or b""
    try:
        body = json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except ValueError:
        body = raw.hex()
    return hashlib.sha256("\n".join([business, request.method or "", request.path, body]).encode()).hexdigest()


class ApprovalRequired(OperationError):
    """The refusal a manager can lift: the envelope also says what is approved and the request's fingerprint."""

    status = 403
    code = REQUIRES_ELEVATION

    def __init__(self, message: str, *, operation: str, label: str, fingerprint: str) -> None:
        super().__init__(message)
        self.approval = {"operation": operation, "label": label, "fingerprint": fingerprint}

    def envelope(self) -> dict:
        envelope = super().envelope()
        envelope["error"]["approval"] = dict(self.approval)
        return envelope


@dataclass(frozen=True)
class Approved:
    """The mark of a request a manager approved: its one permission more, and who approved it."""

    approval_id: str
    permission: str
    approver: str


class ApprovalDoor:
    """The approval's door of one command's route, in front of the session's: it answers the session's caller."""

    def __init__(self, op_name: str) -> None:
        self.op_name = op_name

    def __call__(self, request: HttpRequest):
        user = django_auth(request)
        if not user:
            return None
        found = approvable(self.op_name)
        if found is None:
            return user
        op, label = found
        from base.operations import HubContextBuilder

        ctx = HubContextBuilder().from_request(request)
        if ctx.has(op.permission):
            return user
        asked = fingerprint(request, ctx.scope.key)
        token = request.headers.get(HEADER, "")
        if token.startswith(TOKEN_PREFIX):
            from base.schemas import ApprovalSpendIn

            spent = get("base.approval.spend")(ctx, ApprovalSpendIn(token=token, operation=op.name, fingerprint=asked))
            if spent.spent:
                request.approved = Approved(approval_id=spent.id, permission=op.permission, approver=spent.approver)
                return user
        raise ApprovalRequired(
            gettext("This needs a manager's approval."), operation=op.name, label=label, fingerprint=asked
        )


def install(api: NinjaAPI) -> list[str]:
    """Put the approval's door in front of the session's on every command's route the session opens (after a key's
    door, which answers first); returns their operations. Whether a command is approvable is asked per request."""
    installed = []
    for bound_router in api._get_bound_routers():
        for path_view in bound_router.path_operations.values():
            for route in path_view.operations:
                if not route.operation_id or django_auth not in route.auth_callbacks:
                    continue
                try:
                    op = get(route.operation_id)
                except Exception:
                    continue
                if op.kind != "command":
                    continue
                keys = [callback for callback in route.auth_callbacks if isinstance(callback, KeyDoor)]
                rest = [callback for callback in route.auth_callbacks if not isinstance(callback, KeyDoor)]
                route.auth_callbacks = [*keys, ApprovalDoor(op.name), *rest]
                installed.append(op.name)
    return installed
