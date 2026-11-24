"""Apps turned on and off by the business, with the plan's limit (``base.app.enable``, ``disable`` and ``retry``).

The rules are base.activation's; here, their rows (base.AppActivation) under a lock of the business's rows, so two
people at once never both pass the limit, and the events. Turning an app off never drops its tables.

In a hub with its own database an app whose tables its database
does not have yet (``Hub.schema_apps``, what the migrator confirmed) is ``creating``: the answer says so (the route's
202), the event ``base.app.activation_requested`` is recorded and the hub's ``hub_due`` rung after the COMMIT; the
worker makes its tables (``ensure_schema``) and turns it on (``base.app.activation_settle``: ``base.app.enabled``, its
live notice), or ``failed`` with why, tried again at 1, 5 and 15 minutes and then every hour, or by hand
(``base.app.retry``). What it needs goes in the same plan. One whose tables it has is on at once. A
business without its own database turns every app on at once: none is
served, only the suite's tests written before the tenancy still have one (``base/tenancy/tests/legacy.py``).
"""

from collections.abc import Iterable
from functools import cache as _cache
from functools import partial
from typing import Any

from django.utils import timezone, translation
from django.utils.translation import gettext, ngettext, pgettext_lazy
from live.context import OperationContext
from live.errors import Conflict, NotFound, OperationError
from live.meta import module_configs
from live.operations import on_commit as after_commit
from live.operations import operation
from live.outbox import record_event

from base import activation, app_switch, blueprint, entitlement, events, home, listing, queries
from base.activation import CREATING, FAILED
from base.models.activation import AppActivation
from base.models import Hub
from base.permissions import ADMINISTER_HUB
from base.schemas.apps import AppChangeIn, AppChangeOut
from base.services.blueprints import _load_what_waited, _stop_waiting, _waiting_loads
from base.services.photo import _sync_photo_blocks
from base.services.provisioning import ring
from base.tenancy import migrator

#: What the card of turning on an app the business's country requires calls its reason for never going off.
ONCE_ON = pgettext_lazy("base", "Once on")


class AppLimitReached(OperationError):
    """Turning on one more app the business chooses, at its plan's limit (``plan.max_apps``): 402, with the limit and
    the chosen apps on, for the screen's notice and its «Upgrade plan»."""

    status = 402
    code = "base.app_limit_reached"

    def __init__(self, message: str, *, max_apps: int, enabled: int) -> None:
        super().__init__(message)
        self.max_apps, self.enabled = max_apps, enabled

    def envelope(self) -> dict:
        envelope = super().envelope()
        envelope["error"].update(max_apps=self.max_apps, enabled=self.enabled)
        return envelope


class AppRequired(Conflict):
    """Turning off an app another app on needs: 409, with those apps (they go off first)."""

    def __init__(self, message: str, *, required_by: list[str]) -> None:
        super().__init__(message, code="base.app_required")
        self.required_by = list(required_by)

    def envelope(self) -> dict:
        envelope = super().envelope()
        envelope["error"]["required_by"] = list(self.required_by)
        return envelope


class AppVetoed(Conflict):
    """An app refused to go off or on (its ``can_disable``, ``can_enable``): 409, with its reason as the message and
    its id."""

    def __init__(self, message: str, *, app: str) -> None:
        super().__init__(message, code="base.app_vetoed")
        self.app = app

    def envelope(self) -> dict:
        envelope = super().envelope()
        envelope["error"]["app"] = self.app
        return envelope


def _business_hub(ctx: OperationContext) -> Hub | None:
    return Hub.objects.filter(slug=ctx.scope.key).first()


def _business_module(ctx: OperationContext, said: str, hub: Hub | None) -> Any:
    """The module ``said`` names (its id, or its name as the person says it: ``queries.apps.find_app``) as this business
    shows it; 404 for any other (the platform, or one it never shows), 409 ``base.app_ambiguous`` for a name of several."""
    return queries.apps.find_app(said, demo=bool(hub and hub.is_demo), language=ctx.language)


def _locked_states(ctx: OperationContext, graph: dict) -> dict[str, activation.Activation]:
    """Every module's state in the business, its rows locked until the COMMIT: a business on its baseline writes it
    down first (another doing it at the same time leaves its rows: ON CONFLICT DO NOTHING). The rows are read again
    once locked, a new statement, which sees what another committed meanwhile."""
    host = ctx.scope.key
    rows = AppActivation.objects.filter(host=host)
    if not rows.exists():
        AppActivation.objects.bulk_create(
            [
                AppActivation(host=host, app=label, state=row.state, chosen=row.chosen)
                for label, row in activation.baseline(graph).items()
            ],
            ignore_conflicts=True,
        )
    list(rows.select_for_update().order_by("app").values_list("id", flat=True))
    return activation.effective(queries.apps.app_activations(host), graph)


def _write_states(host: str, changes: dict[str, activation.Activation]) -> None:
    """Write ``changes`` and, after the COMMIT of the running change, forget what the cache kept of the business. A row
    that goes ``creating`` waits for no time (the worker takes it now) and keeps its failed attempts; one that goes on or
    off has none left."""
    after_commit(partial(activation.forget, host))
    now = timezone.now()
    existing = set(AppActivation.objects.filter(host=host, app__in=list(changes)).values_list("app", flat=True))
    for label, row in changes.items():
        if label in existing:
            settled = {"target": _code_leaf(label)} if row.state == CREATING else {"attempts": 0, "last_error": ""}
            AppActivation.objects.filter(host=host, app=label).update(
                state=row.state, chosen=row.chosen, changed_at=now, next_attempt_at=None, **settled
            )
    AppActivation.objects.bulk_create(
        AppActivation(
            host=host,
            app=label,
            state=row.state,
            chosen=row.chosen,
            target=_code_leaf(label) if row.state == CREATING else "",
        )
        for label, row in changes.items()
        if label not in existing
    )


@_cache
def _code_leaves() -> dict[str, str]:
    """This code's last migration of each app (its migrations never change while the process runs)."""
    return dict(migrator.code_migrations().leaves)


def _code_leaf(label: str) -> str:
    """The last migration of ``label`` in this code, which its tables are made to; ``""`` for an app without any."""
    return _code_leaves().get(label, "")


def _apps_without_migrations() -> frozenset[str]:
    """The modules with no migration: created in every hub by definition (they have no tables)."""
    return frozenset(activation.module_graph()) - set(_code_leaves())


def apps_created(hub: Hub) -> frozenset[str]:
    """The modules whose tables ``hub``'s own database has: what the migrator confirmed (``Hub.schema_apps``; the
    worker's ``ensure_schema`` makes what it lacks and is a no-op for what it has) and those without migrations."""
    return frozenset(hub.schema_apps or ()) | _apps_without_migrations()


def _tables_first(
    changes: dict[str, activation.Activation],
    current: dict[str, activation.Activation],
    created: frozenset[str],
) -> dict[str, activation.Activation]:
    """``changes`` as they are written: when an app they turn on lacks its tables, every app they turn on is
    ``creating`` (one plan); an app already on stays on."""
    turning_on = [label for label, row in changes.items() if row.on and not current[label].on]
    if all(label in created for label in turning_on):
        return changes
    return {
        label: activation.Activation(CREATING, row.chosen) if label in turning_on else row
        for label, row in changes.items()
    }


def _ring(hub: Hub) -> None:
    """The hub has tables to make: due in ``hub_due`` now and the worker told, so it takes it at its next tick (after the
    COMMIT of the change that asked for them; on control)."""
    ring(hub, told=events.APP_ACTIVATION_REQUESTED)


def _named(ctx: OperationContext, labels: Iterable[str]) -> list[dict[str, str]]:
    names = {config.label: config.verbose_name for config in module_configs()}
    with translation.override(ctx.language):
        return [{"id": label, "name": str(names.get(label, label))} for label in labels]


def _names_said(ctx: OperationContext, labels: list[str]) -> str:
    """«A», «A and B», «A, B, and C», in the language of who asks, as the screens order and join them."""
    return listing.joined(listing.ordered(item["name"] for item in _named(ctx, labels)), ctx.language)


def _app_answer(label: str, row: activation.Activation, along: list[dict[str, str]], *, already: bool) -> dict:
    """``already``: it was in that state before (on, or off), and nothing went on or off: the assistant says so."""
    return {"app": label, "state": row.state, "chosen": row.wanted and row.chosen, "along": along, "already": already}


def _card_app(ctx: OperationContext, arguments: dict) -> tuple[Hub | None, Any]:
    """The business's hub and the app a card names; no app for a name of none, or of several: the card's check
    (``base.app.get``) refuses it before anyone sees it, and the card is drawn as it is."""
    hub = _business_hub(ctx)
    try:
        return hub, _business_module(ctx, arguments["app"], hub)
    except (NotFound, Conflict):
        return hub, None


def _enable_card(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """The card of turning an app on: the apps it needs that are off, which come along (``app_switch``), and, for one
    the business's country requires, the reason the Apps screen gives why it never goes off: the person reads both
    before the yes, not after it."""
    hub, config = _card_app(ctx, arguments)
    if config is None:
        return fields
    others = app_switch.along(config.label, activation.states_of(ctx.scope), activation.module_graph(), on=True)
    shown = [*fields, *app_switch.card_datum(app_switch.said(config.label, others, on=True, language=ctx.language))]
    country = hub.country if hub else ""
    if not home.mandatory_in(config, country):
        return shown
    reason = activation.mandatory_off(config, country)
    return [*shown, {"name": "mandatory", "label": str(ONCE_ON), "kind": "text", "value": reason}]


def _disable_card(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """The card of turning an app off: what came along only with it goes off too (``app_switch``, never one the
    business's country requires on). One another app on needs is only named: its yes is refused, saying which apps go
    off first."""
    hub, config = _card_app(ctx, arguments)
    if config is None:
        return fields
    current = activation.states_of(ctx.scope)
    kept = activation.mandatory_on(current, hub.country if hub else "")
    others = app_switch.along(config.label, current, activation.module_graph(), kept, on=False)
    return [*fields, *app_switch.card_datum(app_switch.said(config.label, others, on=False, language=ctx.language))]


@operation(
    "base.app.enable",
    kind="command",
    permission=ADMINISTER_HUB,
    input=AppChangeIn,
    output=AppChangeOut,
    # A dict, not AI(...): AI has no ``check`` (base.assistant.cards.check_of), the read run before the card (hub#542).
    ai={
        "description": "Turns on one of this business's apps (by its name as the person says it, or its id), with the "
        "apps it needs, which come along: it shows in the menu and can be used, with the data it had. Refused when the "
        "plan's limit of apps is reached (turn one off, or upgrade the plan on erplora.com), a paid app is not "
        "subscribed, the app itself says why not or the name fits several apps (ask which one). state=creating: it is "
        "being set up and is on in a moment. already=true: it was on (or being set up) already, nothing changed. One "
        "base.app.get says is mandatory can't be turned off once on: say so before turning it on. Use this when an app "
        "should be available again, not another app's settings operation.",
        "risk": "normal",
        "check": "base.app.get",
        "summary": _enable_card,
        "asks": {
            "en": (
                "turn on the customers app",
                "activate the bookings app",
                "can you turn on the kitchen module?",
                "bring back the time clock app I took off the menu",
            ),
            "es": (
                "activa la app de clientes",
                "ponme la app de cocina",
                "activa el módulo de citas",
                "recupera la app de fichajes que quité del menú",
                "vuelve a dejar disponible la app de tareas",
            ),
        },
    },
)
def app_enable(ctx: OperationContext, data: AppChangeIn) -> dict:
    """BASE-F18/F24: the app on and chosen, and what it needs on along with it (not chosen: it does not count). A
    paid one without its right (or needing one) is 402 ``app_entitlement_blocked``; one more chosen app at the plan's
    limit, 402 ``base.app_limit_reached`` (a lower limit than the chosen ones turns nothing off: it only refuses this);
    409 ``base.app_vetoed`` when it, or what would come along, refuses (``can_enable``, hub#694).
    While the hub's tables for it (or for what it needs) are not made yet, ``creating`` (202): the worker makes them
    and turns it on; one that failed is tried again."""
    with activation.changing(ctx.scope.key):
        return _enable(ctx, data)


def _enable(ctx: OperationContext, data: AppChangeIn) -> dict:  # noqa: C901
    hub = _business_hub(ctx)
    app = _business_module(ctx, data.app, hub).label
    graph = activation.module_graph()
    blocked = entitlement.blocked_apps(ctx.scope)
    for label in [app, *sorted(activation.needs([app], graph))]:
        if label in blocked:
            raise entitlement.refused(label, ctx.language)
    current = activation.states_of(ctx.scope)
    if not activation.enabling(app, current, graph):
        return _unchanged(hub, app, current[app])
    current = _locked_states(ctx, graph)
    changes = activation.enabling(app, current, graph)
    if not changes:
        return _unchanged(hub, app, current[app])
    vetoed = activation.veto(
        [label for label in changes if not current[label].on], ctx=ctx, hook=activation.CAN_ENABLE
    )
    if vetoed is not None:
        raise AppVetoed(vetoed[1], app=vetoed[0])
    if changes.get(app, current[app]).chosen and not (current[app].wanted and current[app].chosen):
        limit = queries.apps.app_limit(hub)
        shown = {config.label for config in home.shown_modules(demo_hub=bool(hub and hub.is_demo))}
        enabled = activation.chosen_on(current, among=shown)
        if limit is not None and enabled >= limit:
            with translation.override(ctx.language):
                message = ngettext(
                    "You have reached the %(count)s-app limit of your plan. Upgrade your plan or turn one off.",
                    "You have reached the %(count)s-app limit of your plan. Upgrade your plan or turn one off.",
                    limit,
                ) % {"count": limit}
            raise AppLimitReached(message, max_apps=limit, enabled=enabled)
    changes = _tables_first(changes, current, apps_created(hub))
    _write_states(ctx.scope.key, changes)
    on_now = [label for label, row in changes.items() if row.on]
    if hub is not None and not hub.is_demo and on_now:
        _sync_photo_blocks(hub, on_now)
    along = [label for label in changes if label != app]
    answer = changes.get(app, current[app])
    if any(row.state == CREATING for row in changes.values()):
        after_commit(partial(_ring, hub))
    name = events.APP_ACTIVATION_REQUESTED if answer.state == CREATING else events.APP_ENABLED
    record_event(ctx, name, {"app": app, "along": along})
    if on_now:
        _load_what_waited(ctx, on_now)
    return _app_answer(app, answer, _named(ctx, along), already=current[app].on)


def _unchanged(hub: Hub | None, label: str, row: activation.Activation) -> dict:
    """Turning on an app on and chosen already, or being created (its hub rung again: a ring lost is found again):
    ``already``, nothing went on."""
    if row.state == CREATING:
        after_commit(partial(_ring, hub))
    return _app_answer(label, row, [], already=True)


@operation(
    "base.app.disable",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=AppChangeIn,
    output=AppChangeOut,
    # A dict, not AI(...): AI has no ``check`` (base.assistant.cards.check_of), the read run before the card (hub#542).
    ai={
        "description": "Turns off one of this business's apps (by its name as the person says it, or its id): it "
        "leaves everyone's menu and its screens stop opening; the apps that came along only with it go off too. Nothing "
        "is deleted: turned on again, it has its data; an app the business's country requires (mandatory in "
        "base.app.get) stays on. Refused while another app on needs it, when the business's country requires the app "
        "on, when the app itself says why not yet or when the name fits several apps (ask which one). already=true: it "
        "was off already.",
        "risk": "high",
        "check": "base.app.get",
        "summary": _disable_card,
        "asks": {
            "en": (
                "turn off the reservations app",
                "we don't use tables anymore, switch that app off",
                "deactivate the loyalty module",
            ),
            "es": (
                "desactiva la app de reservas",
                "apaga la app de mesas, ya no la usamos",
                "quita el módulo de fidelización, no lo necesitamos",
            ),
        },
    },
)
def app_disable(ctx: OperationContext, data: AppChangeIn) -> dict:
    """BASE-F23/F25: the app off, and what came along only with it but what the business's country requires on, which
    stays on (hub#997). 409 ``base.app_required`` while an app on needs it (naming the ones to turn off first); 409
    ``base.app_vetoed`` when it, one that would go off with it or one of those that need it refuses (``can_disable``, or
    base's reason for one the country requires on: hub#619, hub#997; nobody can turn off
    first one that refuses). Its tables are never dropped."""
    with activation.changing(ctx.scope.key):
        return _disable(ctx, data)


def _disable(ctx: OperationContext, data: AppChangeIn) -> dict:
    hub = _business_hub(ctx)
    app = _business_module(ctx, data.app, hub).label
    graph = activation.module_graph()
    if not activation.states_of(ctx.scope)[app].wanted:
        return _app_answer(app, activation.OFF_ROW, [], already=True)
    current = _locked_states(ctx, graph)
    if not current[app].wanted:
        return _app_answer(app, activation.OFF_ROW, [], already=True)
    # What the business's country requires on never goes off, by itself nor along with this one (hub#997).
    country = hub.country if hub else ""
    kept = activation.mandatory_on(current, country)
    keeping = activation.keeping_on(app, current, graph, kept)
    said = activation.refusals(keeping, ctx=ctx, kept=kept, country=country)
    refused = queries.apps.app_off_refusal(ctx, app, current, graph, said, kept)
    if refused is not None:
        raise AppVetoed(refused[1], app=refused[0])
    needed = activation.required_by(app, current, graph)
    if needed:
        # The ones to turn off: those chosen (what came along goes off with them).
        first = [label for label in needed if current[label].chosen] or needed
        with translation.override(ctx.language):
            message = gettext("Turn off %(apps)s first.") % {"apps": _names_said(ctx, first)}
        raise AppRequired(message, required_by=needed)
    changes = activation.disabling(app, current, graph, kept)
    _write_states(ctx.scope.key, changes)
    along = [label for label in changes if label != app]
    record_event(ctx, events.APP_DISABLED, {"app": app, "along": along})
    _stop_waiting(ctx, _waiting_loads(), changes, blueprint.loads.STOPPED_TURNED_OFF)
    return _app_answer(app, activation.OFF_ROW, _named(ctx, along), already=False)


@operation(
    "base.app.retry",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=AppChangeIn,
    output=AppChangeOut,
    # A dict, not AI(...): AI has no ``check`` (base.assistant.cards.check_of), the read run before the card (hub#542, hub#539).
    ai={
        "description": "Tries again to set up one of this business's apps that could not be turned on (its state "
        "«failed» in base.app.list; by its name as the person says it, or its id), with what it needs that failed too: "
        "it is set up in a moment and then shows in the menu. Refused for an app that is not waiting for it, or when the "
        "name fits several apps (ask which one).",
        "risk": "normal",
        "check": "base.app.get",
        "asks": {
            "en": (
                "the bookings app could not be turned on, try again",
                "retry setting up the kitchen app",
                "try turning on the website app again",
            ),
            "es": (
                "la app de reservas no se pudo activar, inténtalo otra vez",
                "reintenta preparar la app de cocina",
                "vuelve a intentar activar la web",
            ),
        },
    },
)
def app_retry(ctx: OperationContext, data: AppChangeIn) -> dict:
    """An app whose tables could not be made (``failed``) is ``creating`` again now, with what it needs
    that failed too, and its hub rung (the worker also tries again by itself). 409 ``base.app_not_failed`` for any
    other app; 409 ``base.app_vetoed`` when it refuses to go on (``can_enable``, as «Turn on»). The app by its name or
    its id, as ``base.app.enable`` takes it (hub#539)."""
    with activation.changing(ctx.scope.key):
        hub = _business_hub(ctx)
        app = _business_module(ctx, data.app, hub).label
        current = _locked_states(ctx, activation.module_graph())
        if current[app].state != FAILED:
            raise Conflict(gettext("This app is not waiting to be set up again."), code="base.app_not_failed")
        graph = activation.module_graph()
        closure = {app, *activation.needs([app], graph)}
        changes = {
            label: activation.Activation(CREATING, row.chosen)
            for label, row in current.items()
            if label in closure and row.state == FAILED
        }
        vetoed = activation.veto(changes, ctx=ctx, hook=activation.CAN_ENABLE)
        if vetoed is not None:
            raise AppVetoed(vetoed[1], app=vetoed[0])
        _write_states(ctx.scope.key, changes)
        after_commit(partial(_ring, hub))
        along = [label for label in changes if label != app]
        record_event(ctx, events.APP_ACTIVATION_REQUESTED, {"app": app, "along": along})
        return _app_answer(app, changes[app], _named(ctx, along), already=False)
