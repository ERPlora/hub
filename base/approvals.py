"""A manager's PIN lets one refused command through (APP-BASE-5; BASE-G136, the old hub's HUB_SHELL-F51): without the ORM.

An app names the commands of its own a manager may approve on the spot, with what is approved in words:
``approvals = {"sale.sale.void": _("Void a sale")}`` in its ``LiveAppConfig`` (a module cannot name another's, a query
is never approved). :func:`install` puts the approval's door (:class:`ApprovalDoor`) in front of the session's on every
route of a command that needs a caller. For a person who may run the command, or a command nobody names, it changes
nothing. For a person who may not, it answers ``requires_elevation`` (:class:`ApprovalRequired`, 403) with what is
approved and the fingerprint of that very request (:func:`fingerprint`: this business, the method, the path and the
body); somebody of the business who holds the permission approves it (``base.approval.approve``, their PIN or badge,
the PIN pad's hash and brakes) and the hub hands back a pass (``X-Elevation-Token``) of one use, for two minutes
(:data:`PASS_SECONDS`). The command repeated with it goes through once, with that one permission more: the door marks
the request with the pass (:class:`Approved`), ``base.operations`` adds the permission to that call's context, and the
pass is spent (``base.approval.spend``, its row locked) in the command's own transaction (``base.approval_spend``,
from ``LIVE["operation_database"]``): a command that fails leaves it unspent, one that went through cannot be repeated,
and of two at once only one runs. A pass that is spent, late, forged, another person's, another command's or another
request's is the same question again, never a way in. Whoever is not of the business gets the refusal of always.
What the approved command asks of another app on the way (``base.operations.call``) goes with it, while it runs: a
command of another app gets its permission too (:func:`consequence_context`); a read, never.
"""

import dataclasses
import functools
import hashlib
import json
import re
import secrets
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

import pydantic
from babel.numbers import format_decimal, format_percent
from django.apps import apps
from django.conf import settings
from django.core import checks
from django.http import HttpRequest
from django.utils import translation
from django.utils.functional import Promise
from django.utils.translation import gettext
from live.context import OperationContext, Scope
from live.errors import OperationError
from live.meta import all_live_app_configs
from live.operations import Operation, current_operation, get
from ninja import NinjaAPI
from ninja.security import django_auth

from base.api_keys import KeyDoor
from base.business import money_text

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


#: A hole of a sentence of ``approval_figures``: ``{field}`` or ``{field, format}``.
HOLE = re.compile(r"\{\s*([a-z_][a-z0-9_]*)\s*(?:,\s*([a-z]+)\s*)?\}")
#: The formats a hole knows besides a bare text or number: a percentage and an amount of money.
FORMATS = ("percent", "money")


def label_of(
    op: Operation | None, figures: dict | None = None, scope: Scope | None = None, *, currency: str | None = None
) -> str | None:
    """What approving ``op`` approves, in words, when its own app names it and it is a command with a permission that
    opens its transaction: the pass is spent in it (``base.approval_spend``), so a ``database=False`` one never is.
    With the ``figures`` of a request (:func:`figures_of`), the first of its app's sentences that they fill, in the
    active language, in ``currency`` (else ``scope``'s business's, asked only for an amount)."""
    if op is None or op.kind != "command" or not op.permission or not op.database:
        return None
    try:
        config = apps.get_app_config(op.app_label)
    except LookupError:
        return None
    named = getattr(config, "approvals", None)
    label = named.get(op.name) if isinstance(named, dict) else None
    if not label:
        return None
    if figures:
        money = functools.cache(lambda: currency if currency is not None else currency_of(scope))
        for sentence in sentences_of(op):
            said = _filled(op, str(sentence), figures, money)
            if said:
                return said
    return str(label)


def currency_of(scope: Scope | None) -> str | None:
    """The currency ``scope``'s business charges in (BASE-F50); ``None`` when it has none known: no amount is said."""
    if scope is None:
        return None
    from base.operations import business_currency

    try:
        return business_currency(scope)
    except OperationError:
        return None


def sentences_of(op: Operation) -> list:
    """The sentences ``op``'s own app declares to say it with its figures (``approval_figures``); none, ``[]``."""
    try:
        config = apps.get_app_config(op.app_label)
    except LookupError:
        return []
    named = getattr(config, "approval_figures", None)
    sentences = named.get(op.name) if isinstance(named, dict) else None
    if isinstance(sentences, str | Promise):
        return [sentences]
    return list(sentences) if isinstance(sentences, list | tuple) else []


def holes(sentence: str) -> list[tuple[str, str | None]] | None:
    """The holes of ``sentence``, in order, as ``(field, format)``; ``None`` when a brace opens or closes none."""
    rest = HOLE.sub("", sentence)
    if "{" in rest or "}" in rest:
        return None
    return [(found.group(1), found.group(2)) for found in HOLE.finditer(sentence)]


def figures_of(op: Operation, data: pydantic.BaseModel | None) -> dict:
    """The figures of ``data``, ``op``'s input as its schema validated it, that ``op``'s sentences name: only those
    fields, as JSON (a decimal as its text); none named, ``{}``."""
    if data is None:
        return {}
    named = {name for sentence in sentences_of(op) for name, _ in holes(str(sentence)) or ()}
    named &= set(type(data).model_fields)
    if not named:
        return {}
    dumped = data.model_dump(mode="json", include=named)
    return {name: dumped.get(name) for name in sorted(named)}


def figures_from(op: Operation, raw: bytes | str | None) -> dict:
    """The figures of a request's body or a tool's arguments (JSON), validated as the command validates them (a route
    and the assistant parse it, then ``op.input``); an input the command does not take has none."""
    if not sentences_of(op):
        return {}
    try:
        data = json.loads(raw or b"{}")
        validated = op.input.model_validate(data) if isinstance(data, dict) else None
    except ValueError:
        # Not JSON, or refused by the command's schema (pydantic's ValidationError is a ValueError): the command says it.
        return {}
    return figures_of(op, validated)


def _filled(op: Operation, sentence: str, figures: dict, money: Callable[[], str | None]) -> str:
    """``sentence`` with its holes filled from ``figures``, or ``""`` when one does not fill: never half a sentence."""
    parts = holes(sentence)
    if not parts:
        return ""
    said: dict[tuple[str, str | None], str] = {}
    for name, how in parts:
        text = _figure(op, name, how, figures.get(name), money)
        if not text:
            return ""
        said[(name, how)] = text
    return HOLE.sub(lambda found: said[(found.group(1), found.group(2))], sentence).strip()


def _figure(op: Operation, name: str, how: str | None, value: Any, money: Callable[[], str | None]) -> str:
    """One figure as the Hub writes it in the active language; ``""`` when empty, zero or not what the hole asks."""
    if how is None and not _numeric(op, name):
        return value.strip() if isinstance(value, str) else ""
    number = _number(value)
    if number is None or number == 0:
        return ""
    locale = translation.to_locale(translation.get_language() or settings.LANGUAGE_CODE)
    if how == "percent":
        return format_percent(number.normalize() / 100, locale=locale, decimal_quantization=False)
    if how == "money":
        return _money(number, money(), locale)
    return format_decimal(number.normalize(), locale=locale) if how is None else ""


def _money(cents: Decimal, currency: str | None, locale: str) -> str:
    """Minor units of ``currency``, as every screen writes them («1.234,56 €», «€1,234.56», «PLN 1.00»)."""
    if currency is None or cents != cents.to_integral_value():
        return ""
    return money_text(cents, currency, language=locale)


def _number(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _numeric(op: Operation, name: str) -> bool:
    """Whether ``op``'s input takes ``name`` as a number (an integer, a decimal or a choice of numbers)."""
    found = op.input.model_fields.get(name)
    return found is not None and _is_number(found.annotation)


def _is_number(annotation: Any, kinds: tuple[type, ...] = (int, float, Decimal)) -> bool:
    """Whether ``annotation`` (optional or not) only takes numbers of ``kinds``: an integer, a decimal, a choice of them."""
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        some = [arg for arg in typing.get_args(annotation) if arg is not type(None)]
        return bool(some) and all(_is_number(arg, kinds) for arg in some)
    if origin is typing.Literal:
        return all(isinstance(arg, kinds) and not isinstance(arg, bool) for arg in typing.get_args(annotation))
    if origin is typing.Annotated:
        return _is_number(typing.get_args(annotation)[0], kinds)
    return isinstance(annotation, type) and issubclass(annotation, kinds) and annotation is not bool


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
    """The mark of a request that came with a manager's pass: the command it is for, its one permission more, and the
    pass with the request's fingerprint, spent in the command's transaction (``base.approval_spend``)."""

    operation: str
    permission: str
    token: str
    fingerprint: str
    #: The figures of that request its app's sentences name (:func:`figures_of`): the record keeps them.
    figures: dict = field(default_factory=dict, compare=False)


def approval_of(ctx: OperationContext) -> Approved | None:
    """The manager's approval the request of ``ctx`` came with (the door's or the assistant's mark); ``None`` without
    one."""
    marked = getattr(getattr(ctx, "request", None), "approved", None)
    return marked if isinstance(marked, Approved) else None


def consequence_context(ctx: OperationContext, op: Operation) -> OperationContext:
    """The context ``op``, an operation of another app, runs with as part of the caller's (``base.operations.call``).
    While the command a manager approved for this very request runs (live's ``current_operation``: its pass is spent
    in its transaction before its body runs), a command of another app it calls goes with it, as when the manager does
    it themselves: the rectifying invoice of a void, the voucher's sessions a refund gives back. A read never, a command
    of the approved command's own app never, nor anything outside the approved command (the next request, another tool
    of the assistant's turn): the caller's own context, as it is also for who already may (a command without a
    permission, anybody)."""
    approval = approval_of(ctx)
    running = current_operation.get()
    if (
        approval is None
        or running is None
        or running.name != approval.operation
        or op.kind != "command"
        or op.app_label == running.app_label
        or ctx.has(op.permission)
    ):
        return ctx
    return dataclasses.replace(ctx, permissions=frozenset(ctx.permissions) | {op.permission})


def refusal(operation: str, fingerprint_: str, figures: dict | None = None, scope: Scope | None = None) -> ApprovalRequired:
    """The approval's question for ``operation`` on the request of ``fingerprint_``, said with its ``figures``."""
    found = approvable(operation)
    label = (label_of(found[0], figures, scope) or found[1]) if found is not None else operation
    return ApprovalRequired(gettext("This needs a manager's approval."), operation=operation, label=label, fingerprint=fingerprint_)


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

        from base.permissions import VIEW_HOME

        ctx = HubContextBuilder().from_request(request)
        if ctx.has(op.permission) or not ctx.has(VIEW_HOME):
            # Somebody who may, or somebody who is not of the business: the command's own refusal of always.
            return user
        asked = fingerprint(request, ctx.scope.key)
        figures = figures_from(op, request.body)
        token = request.headers.get(HEADER, "")
        if token.startswith(TOKEN_PREFIX):
            request.approved = Approved(
                operation=op.name, permission=op.permission, token=token, fingerprint=asked, figures=figures
            )
            return user
        raise ApprovalRequired(
            gettext("This needs a manager's approval."),
            operation=op.name,
            label=label_of(op, figures, ctx.scope) or label,
            fingerprint=asked,
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


@checks.register("base")
def check_approvals(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """``base.E004``: a command an app names as approvable opens its transaction, where the manager's pass is spent
    (``base.approval_spend``); one declared ``database=False`` (live#10) has none, and is said at start."""
    errors: list[checks.CheckMessage] = []
    for config in all_live_app_configs():
        named = getattr(config, "approvals", None)
        for name in named if isinstance(named, dict) else ():
            try:
                op = get(name)
            except Exception:
                continue
            if op.kind == "command" and not op.database:
                errors.append(
                    checks.Error(
                        f"{config.label} names {name} as approvable, but it touches no database (database=False).",
                        hint="A manager's pass is spent in the transaction of the command it lets through: approve a "
                        "command that opens one, or do not name it in approvals.",
                        obj=config,
                        id="base.E004",
                    )
                )
    return errors


@checks.register("base")
def check_approval_figures(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """``base.E008``: an app says with figures only a command of its own that its ``approvals`` name, in sentences whose
    holes are fields of that command's input, with a format the Hub knows (``percent`` and ``money`` of a number,
    ``money`` of whole minor units), and the same holes in every language of the Hub."""
    errors: list[checks.CheckMessage] = []
    for config in all_live_app_configs():
        named = getattr(config, "approval_figures", None)
        if named is None:
            continue
        if not isinstance(named, dict):
            errors.append(_figures_error(config, f"{config.label}.approval_figures is not a dict of command → sentences."))
            continue
        for name, sentences in named.items():
            errors += [_figures_error(config, problem) for problem in _figures_problems(config, name, sentences)]
    return errors


def _figures_error(config, message: str) -> checks.Error:
    return checks.Error(
        message,
        hint="approval_figures says a command of the app's own approvals with the figures of its input: "
        '{"<command>": [_("… {field} …"), …]}, holes {field}, {field, percent} or {field, money}.',
        obj=config,
        id="base.E008",
    )


def _figures_problems(config, name: str, sentences: Any) -> list[str]:
    own = getattr(config, "approvals", None)
    if not isinstance(own, dict) or name not in own:
        return [f"{config.label} says {name} with figures, but its approvals do not name it."]
    try:
        op = get(name)
    except Exception:
        return [f"{config.label} says {name} with figures, but no command is called so."]
    if op.app_label != config.label:
        return [f"{config.label} says {name} with figures, but it is a command of {op.app_label}."]
    if not isinstance(sentences, str | Promise | list | tuple):
        return [f"{config.label} says {name} with {type(sentences).__name__}, not a list of sentences."]
    problems: list[str] = []
    for sentence in [sentences] if isinstance(sentences, str | Promise) else sentences:
        with translation.override(None):
            source = str(sentence)
        found = holes(source)
        if found is None:
            problems.append(f"{config.label}: a sentence of {name} has a brace that opens or closes no hole: {source!r}.")
            continue
        for field_name, how in found:
            problems += _hole_problems(config, op, field_name, how)
        for language, _ in settings.LANGUAGES:
            with translation.override(language):
                translated = holes(str(sentence))
            if translated is None or set(translated) != set(found):
                problems.append(f"{config.label}: the {language} of {source!r} ({name}) does not have the same holes.")
    return problems


def _hole_problems(config, op: Operation, field_name: str, how: str | None) -> list[str]:
    declared = op.input.model_fields.get(field_name)
    if declared is None:
        return [f"{config.label}: {op.name}'s input has no field {field_name}."]
    if how is not None and how not in FORMATS:
        return [f"{config.label}: {{{field_name}, {how}}} of {op.name} is no format the Hub knows ({', '.join(FORMATS)})."]
    if how is not None and not _is_number(declared.annotation, (int,) if how == "money" else (int, float, Decimal)):
        kind = "whole minor units" if how == "money" else "a number"
        return [f"{config.label}: {{{field_name}, {how}}} of {op.name} is not {kind}."]
    return []
