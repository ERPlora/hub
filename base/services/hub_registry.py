"""The registry of hubs (``base.Hub``, the operations ``base.hub.*`` the SaaS calls), and the cut's last step.

The registry's operations are what the SaaS's signed ``/internal/hubs/{id}`` calls run
(``base.internal``), as the platform only (``base.internal_only`` for anyone else), on the registry's scope. A sign-up
is ``ready`` once the worker made its database, and the SaaS hears it after that COMMIT
(:func:`base.services.provisioning.report_ready`); if that call fails, the SaaS asks ``GET /internal/hubs/{id}`` two
minutes later.
"""

from collections.abc import Callable
from functools import partial
from uuid import UUID, uuid7

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext
from live.context import OperationContext, Scope
from live.errors import Conflict, InvalidPayload, NotFound
from live.models import OutboxEvent
from live.operations import INTERNAL, on_commit, on_commit as after_commit, operation
from live.outbox import notify, record_event
from live.slugs import validate_hub_slug

from base import activation, custom_domains, events, registry
from base.models import AppActivation, Hub
from base.registry import hub_answer, internal_only
from base.schemas.hub_registry import (
    HubCancelIn,
    HubCutFinishIn,
    HubCutFinishOut,
    HubOut,
    HubRegisterOut,
    HubRegistryIn,
    HubRestoreIn,
    HubSeedLocalIn,
    HubSeedLocalOut,
    HubStateIn,
    HubStateOut,
)
from base.services.photo import _sync_verifactu, _sync_whatsapp
from base.services.provisioning import holds_hub_lease, offboarding_due
from base.services.sessions import _apply_members, _sync_hub_users, _wake_open_apps
from base.tenancy import names as database_names
from base.tenancy.connections import control_name
from control.models import HubDue


# ── The registry of hubs: what the SaaS's /internal/hubs/{id} runs ──────────────────────────────────────────────


#: The statuses a hub never comes back from (``dropping``: its database is going): the SaaS reads ``hub_purged``
#: literally (``_restore``).
PURGED_STATUSES = frozenset({Hub.Status.PURGED, Hub.Status.EXPIRED, Hub.Status.DROPPING})
#: A business that left and may still come back: ``archiving`` is its final copy being made, after its 90 days.
LEFT_STATUSES = (Hub.Status.CANCELLED, Hub.Status.ARCHIVING)


def _locked_hub(hub_id: UUID) -> Hub:
    hub = Hub.objects.select_for_update().filter(pk=hub_id).first()
    if hub is None:
        raise NotFound(gettext("No hub has this id."))
    return hub


def _refuse_purged(hub: Hub) -> None:
    if hub.status in PURGED_STATUSES:
        raise Conflict(gettext("This hub was purged: it cannot come back."), code="hub_purged")


def _slug_taken() -> Conflict:
    return Conflict(gettext("Another hub has this address."), code="base.slug_taken")


# Not an assistant tool: the platform's door (/internal, the SaaS), no person.
@operation(
    "base.hub.register",
    kind="command",
    permission=None,
    input=HubRegistryIn,
    output=HubRegisterOut,
    ai=INTERNAL,
)
def hub_register(ctx: OperationContext, data: HubRegistryIn) -> dict:  # noqa: C901
    """Register the SaaS's business ``data.id`` (or update its name, slug, country…): ``requested``, with a database of
    its own to make (never control's), due in the worker's ``hub_due``.

    A customer's slug never takes a demo's ``demo-…`` nor a reserved name (``base.slug_invalid``); one that is
    another hub's is ``base.slug_taken``. A cancelled hub is restored first (``base.hub_cancelled``); a purged one
    never comes back (``hub_purged``). The worker clones its database (``base.tenancy.provision``) and the SaaS hears
    ``ready`` from it; an update of a hub still being prepared keeps it due (a failed one is tried again now), and
    one of a ready hub, idempotent, says nothing.
    """
    internal_only(ctx)
    try:
        slug = validate_hub_slug(data.slug)
    except ValueError as invalid:
        raise InvalidPayload(
            gettext("This address cannot name a business (%(reason)s).") % {"reason": invalid},
            code="base.slug_invalid",
        ) from None
    if Hub.objects.filter(slug=slug).exclude(pk=data.id).exists():
        raise _slug_taken()
    now = timezone.now()
    fields = {
        "slug": slug,
        "name": data.name,
        "country": data.country,
        "timezone": data.timezone,
        "language": data.language,
        "vertical": data.vertical or "",
    }
    hub = Hub.objects.select_for_update().filter(pk=data.id).first()
    created = hub is None
    if created:
        try:
            with transaction.atomic():
                hub = Hub.objects.create(
                    id=data.id,
                    status=Hub.Status.REQUESTED,
                    db_name=database_names.hub_db_name(control_name(), data.id),
                    **fields,
                )
        except IntegrityError:
            # A concurrent call took the slug, or registered this same id first (then it is an update).
            hub = Hub.objects.select_for_update().filter(pk=data.id).first()
            if hub is None:
                raise _slug_taken() from None
            created = False
    if not created:
        _refuse_purged(hub)
        if hub.status in LEFT_STATUSES:
            raise Conflict(gettext("This hub was cancelled: restore it first."), code="base.hub_cancelled")
        for field, value in fields.items():
            setattr(hub, field, value)
        if hub.status in registry.PREPARING_STATUSES and not hub.db_name:
            # A hub registered before hubs got their own database: it has no data in control's, and gets its own.
            hub.db_name = database_names.hub_db_name(control_name(), hub.id)
        if hub.status == Hub.Status.FAILED:
            # The SaaS asks again: the next attempt is now, not at the end of its wait.
            hub.next_attempt_at = now
        try:
            with transaction.atomic():
                hub.save()
        except IntegrityError:
            raise _slug_taken() from None
    if hub.status in registry.PREPARING_STATUSES:
        HubDue.mark_due(hub, now)
    record_event(ctx, events.HUB_REGISTERED, {"id": str(hub.id), "slug": hub.slug, "created": created})
    # Registered as the platform (/internal): Settings › Business listens on the business's channel, so a
    # name, zone or language changed on erplora.com shows without reloading, after the COMMIT as the photo's.
    transaction.on_commit(partial(notify, Scope("host", hub.slug), [events.HUB_REGISTERED]), robust=True)
    return {**hub_answer(hub), "created": created}


# Not an assistant tool: the platform's door (/internal, the SaaS), no person.
@operation("base.hub.state_apply", kind="command", permission=None, input=HubStateIn, output=HubStateOut, ai=INTERNAL)
def hub_state_apply(ctx: OperationContext, data: HubStateIn) -> dict:
    """Keep the SaaS's photo of ``data.id`` if it is newer than the one kept; an equal or older one changes nothing.

    It applies what the apps use: the VeriFactu block and the business's status, through
    ``verifactu.config.sync`` on the hub's slug, and the number's state of WhatsApp (``whatsapp``), through
    ``whatsapp_inbox.channel.sync`` with the photo's version when the app is on in that business (off, the photo
    applies and the block waits for the next one); both in this same transaction, so their notices go out after its
    COMMIT (a block out of contract keeps nothing). Its ``members`` apply on the business's memberships
    (:func:`_apply_members`) and on its people in its own database (``base.hub_user.sync``), in this transaction
    too; a business whose database is still being made has its people there when its seeding applies the photo
    (:func:`apply_kept_photo`: the SaaS sends it right after the registration). Its modules and plan are read where they are kept: the right
    to a paid app (``base.entitlement``) and «Usage and plan» (``base.plan.usage``) follow this photo. Its
    ``custom_domain`` is kept on the row whether it names one or not, as the photo is whole (HUBS-F17).
    """
    internal_only(ctx)
    hub = _locked_hub(data.id)
    if hub.status in registry.DROPPED_STATUSES or data.version <= hub.state_version:
        # A late photo of a business whose database went: a tombstone keeps nothing of it (no error: the SaaS sent it
        # before it heard).
        return {"applied": False, "version": hub.state_version}
    was_open = not registry.is_suspended(hub)
    domain = data.custom_domain or ""
    if hub.custom_domain != domain:
        transaction.on_commit(custom_domains.forget, robust=True)
    hub.state, hub.state_version, hub.custom_domain = data.photo, data.version, domain
    hub.save(update_fields=["state", "state_version", "custom_domain", "updated_at"])
    # A hub whose database is not made yet (being made, or cancelled or failed before it ever was) keeps the photo on
    # its row: its seeding applies it (:func:`apply_kept_photo`), as turning an app on does for that app's block.
    reachable = registry.database_is_made(hub)
    if reachable and (data.verifactu is not None or data.status is not None):
        _sync_verifactu(hub, data)
    if reachable and data.whatsapp is not None:
        _sync_whatsapp(hub, data)
    if data.members is not None:
        left = _apply_members(hub, data.members)
        if reachable:
            _sync_hub_users(hub, data.members, left)
    record_event(ctx, events.HUB_STATE_APPLIED, {"id": str(hub.id), "version": data.version})
    # Applied as the platform (/internal): its own notice goes to the platform's channel. The live queries that
    # follow the photo (base/live.py) listen on the business's, which hears it after the COMMIT too.
    transaction.on_commit(partial(notify, Scope("host", hub.slug), [events.HUB_STATE_APPLIED]), robust=True)
    if was_open and registry.is_suspended(hub):
        transaction.on_commit(partial(_wake_open_apps, hub.slug), robust=True)
    return {"applied": True, "version": data.version}


# Not an assistant tool: the platform's door (/internal, the SaaS), no person.
@operation("base.hub.cancel", kind="command", permission=None, input=HubCancelIn, output=HubOut, ai=INTERNAL)
def hub_cancel(ctx: OperationContext, data: HubCancelIn) -> dict:
    """The SaaS deleted the business: its host answers 410 from now on; its members and data stay, for a restore. A
    business with a finished database of its own is due for its copy (``offboarding``, the worker's). One that already
    left stays as it is: its 90 days count from when it left."""
    internal_only(ctx)
    hub = _locked_hub(data.id)
    _refuse_purged(hub)
    if hub.status not in LEFT_STATUSES:
        hub.status, hub.cancelled_at = Hub.Status.CANCELLED, timezone.now()
        hub.save(update_fields=["status", "cancelled_at", "updated_at"])
        if offboarding_due(hub):
            # Its copy, by the worker: the SaaS's mail and panel link to it.
            HubDue.mark_due(hub, hub.cancelled_at)
        record_event(ctx, events.HUB_CANCELLED, {"id": str(hub.id)})
        transaction.on_commit(partial(_wake_open_apps, hub.slug), robust=True)
    return hub_answer(hub)


# Not an assistant tool: the platform's door (/internal, the SaaS), no person.
@operation("base.hub.restore", kind="command", permission=None, input=HubRestoreIn, output=HubOut, ai=INTERNAL)
def hub_restore(ctx: OperationContext, data: HubRestoreIn) -> dict:
    """Bring a cancelled hub back (``ready``, or ``requested`` again if its database was never finished, or never
    made: a business that shared a database and left before its cut is made one from nothing, as a sign-up), also while its
    final copy is being made (``archiving``: the worker sees it and leaves its database); a hub that never ended stays
    as it is; a purged one, or one whose database is going (``dropping``), is ``hub_purged``."""
    internal_only(ctx)
    hub = _locked_hub(data.id)
    _refuse_purged(hub)
    if hub.status in LEFT_STATUSES:
        if not hub.db_name:
            hub.db_name, hub.ready_at = database_names.hub_db_name(control_name(), hub.id), None
            hub.save(update_fields=["db_name", "ready_at", "updated_at"])
        # Its own database never finished (cancelled while it was being made): it is made again, not opened.
        unfinished = hub.ready_at is None
        hub.status = Hub.Status.REQUESTED if unfinished else Hub.Status.READY
        hub.cancelled_at = None
        # A copy of its leaving that failed is no longer owed: a second leaving starts from the first wait.
        hub.attempts, hub.last_error, hub.next_attempt_at = 0, "", None
        hub.save(update_fields=["status", "cancelled_at", "attempts", "last_error", "next_attempt_at", "updated_at"])
        if hub.status == Hub.Status.REQUESTED:
            HubDue.mark_due(hub)
        record_event(ctx, events.HUB_RESTORED, {"id": str(hub.id)})
    return hub_answer(hub)


# Not an assistant tool: the platform's door (/internal, the SaaS), no person.
@operation(
    "base.hub.seed_local",
    kind="command",
    permission=None,
    input=HubSeedLocalIn,
    output=HubSeedLocalOut,
    ai=INTERNAL,
)
def hub_seed_local(ctx: OperationContext, data: HubSeedLocalIn) -> dict:
    """Leave the local hubs ``data.slugs`` in the registry, with an id of their own (``seed_local_hubs``), each with a
    database of its own, and every app on, its roots chosen, as every hub made before businesses were born with every app
    off.

    A new one is born ``requested`` with its database's name (``<control>_<hex>``) and due, and the command makes it
    (``base.tenancy.provision``, every app's tables and every app on: :func:`turn_every_app_on`); a local hub
    left on control's database (``db_name=""``) gets its own the same way: nothing is served from control's.
    Local development only (the command checks ``DEBUG``): they are no business of the SaaS's, so the SaaS hears
    nothing. Idempotent: a hub already ready stays as it is, on its database; one left cancelled is ready again (or
    made again, if its own database was never finished); the apps of one that already turned some on or off stay as
    they are, and one left with no app at all has every app on again.
    """
    from base.tenancy.context import use_hub

    internal_only(ctx)
    now = timezone.now()
    hubs = []
    for slug in data.slugs:
        new_id = uuid7()
        hub, created = Hub.objects.select_for_update().get_or_create(
            slug=slug,
            defaults={
                "id": new_id,
                "status": Hub.Status.REQUESTED,
                "db_name": database_names.hub_db_name(control_name(), new_id),
            },
        )
        outcome = "created" if created else "already_ready"
        if not hub.db_name:
            hub.db_name = database_names.hub_db_name(control_name(), hub.id)
            hub.status, hub.ready_at, hub.cancelled_at = Hub.Status.REQUESTED, None, None
            hub.save(update_fields=["db_name", "status", "ready_at", "cancelled_at", "updated_at"])
            outcome = "requested"
        elif hub.status != Hub.Status.READY:
            if hub.status == Hub.Status.CANCELLED:
                made = hub.ready_at is not None
                hub.status = Hub.Status.READY if made else Hub.Status.REQUESTED
                hub.cancelled_at = None
                hub.save(update_fields=["status", "cancelled_at", "updated_at"])
                outcome = "ready_again" if made else "requested"
            elif not created:
                outcome = "requested"
        if hub.status != Hub.Status.READY:
            HubDue.mark_due(hub, now)
        else:
            # Made already, in its own database: every app on again there if it has none (its seeding turned them on
            # the first time: turn_every_app_on).
            with use_hub(hub):
                _every_app_on(slug)
        if outcome != "already_ready":
            record_event(ctx, events.HUB_REGISTERED, {"id": str(hub.id), "slug": slug, "created": created})
        hubs.append({"slug": slug, "outcome": outcome})
    return {"hubs": hubs}


def turn_every_app_on(hub: Hub) -> None:
    """Inside ``use_hub(hub)``: every app on in the local hub ``hub`` (the seeding of ``seed_local_hubs``'s
    databases). Outside any operation, before the hub serves anything: its activations' cache is forgotten at once,
    after the write."""
    _every_app_on(hub.slug, then=lambda forget: forget())


def turn_on_born_apps(hub: Hub) -> list[str]:
    """Inside ``use_hub(hub)``, at its seeding (``base.tenancy.provision``), before the SaaS's photo kept is applied:
    write down every module of the business ``hub`` just born, those its country requires that the platform turns on by
    itself and what they need (``activation.born_apps``: Taxes, hub#997) on and not chosen (they take nothing of the
    plan's limit), every other off; unless it has rows already (its seeding wrote them: the local hubs, born with
    every app on; or a preparation run again). Outside any operation, before the hub serves anything: what was kept of
    its apps is forgotten at once. What went on."""
    host = hub.slug
    if AppActivation.objects.filter(host=host).exists():
        return []
    states = activation.born(activation.born_apps(hub.country), activation.module_graph())
    AppActivation.objects.bulk_create(
        AppActivation(host=host, app=label, state=row.state, chosen=row.chosen) for label, row in states.items()
    )
    activation.forget(host)
    return sorted(label for label, row in states.items() if row.on)


def _every_app_on(host: str, *, then: Callable[[Callable[[], None]], object] | None = None) -> None:
    """Write down every app on in ``host``'s business, its roots chosen (``base.activation.every_on``), unless it has
    rows already: what the migration ``base.0017`` left every hub made before hubs were born with every app off
    (``seed_local_hubs``).

    Its activations' cache is forgotten after the operation's COMMIT, or by ``then`` outside one (a hub's seeding)."""
    if AppActivation.objects.filter(host=host).exists():
        return
    AppActivation.objects.bulk_create(
        AppActivation(host=host, app=label, state=row.state, chosen=row.chosen)
        for label, row in activation.every_on(activation.module_graph()).items()
    )
    (then or after_commit)(partial(activation.forget, host))


# ── The cut: the businesses that shared a database get their own (``base.tenancy.cut``) ──────────────────────────


def hubs_on_control() -> list[Hub]:
    """The businesses that still keep their data in control's shared database (``db_name`` empty), by slug: what the cut gives a
    database of its own, a demo aside (it ends on its own). None that was purged."""
    return list(
        Hub.objects.filter(db_name="", is_demo=False)
        .exclude(status__in=PURGED_STATUSES)
        .select_related("cluster")
        .order_by("slug")
    )


def copy_all_went_to() -> str:
    """The business control's rows were copied into by a cut (``copy_all``), or ``""``: they go to one business,
    once."""
    found = (
        OutboxEvent.objects.filter(name=events.HUB_CUT, payload__mode="copy_all")
        .order_by("created_at")
        .values_list("payload__slug", flat=True)
        .first()
    )
    return found or ""


# Not an assistant tool: the cut's last step (manage.py cut_shared_hubs), no person.
@operation(
    "base.hub.cut_finish",
    kind="command",
    permission=None,
    input=HubCutFinishIn,
    output=HubCutFinishOut,
    ai=INTERNAL,
)
def hub_cut_finish(ctx: OperationContext, data: HubCutFinishIn) -> dict:
    """The business ``data.id``, which shared control's database, works on its own from now on (its cut): ``db_name``, the
    schema its database has, and ``base.hub.cut`` in control's outbox with how it was made (``mode``), the rows copied
    into it and control's copy taken before (``dump``), in one transaction.

    Only the platform runs it, refused before anything is read. Refused (409 ``base.hub_already_cut``) when the business
    got a database meanwhile (another cut of it finished first) or is no longer ready, (409 ``base.hub_cut_lease_lost``)
    when its lease is no longer this process's (it ran out and another cut took it: the database may be that one's),
    and (409
    ``base.hub_copy_all_taken``) a copy of control's rows when another business got them already (two runs that
    raced: they go to one business, once); ``done: false`` when a newer
    photo of the SaaS's came after ``seeded_version`` was applied: the cut applies it and asks again."""
    internal_only(ctx)
    if data.mode == "copy_all":
        # Every business still on control's, in one order: two copies at once wait for each other, and the second one
        # reads the first one's event.
        list(Hub.objects.select_for_update().filter(Q(db_name="") | Q(pk=data.id)).order_by("pk").values_list("pk"))
    hub = _locked_hub(data.id)
    if hub.db_name or hub.status != Hub.Status.READY:
        raise Conflict(
            gettext("This business already works on its own database, or is not ready."),
            code="base.hub_already_cut",
        )
    if not holds_hub_lease(hub.id):
        raise Conflict(
            gettext("Another process is cutting this business now: this cut stops."),
            code="base.hub_cut_lease_lost",
        )
    went_to = copy_all_went_to()
    if data.mode == "copy_all" and went_to and went_to != hub.slug:
        raise Conflict(
            gettext("Control's rows already went to another business: they are copied once."),
            code="base.hub_copy_all_taken",
        )
    if data.seeded_version is not None and hub.state_version != data.seeded_version:
        return {"done": False}
    hub.db_name = data.database
    hub.schema_apps, hub.schema_state = data.schema_apps, Hub.SchemaState.CURRENT
    hub.save(update_fields=["db_name", "schema_apps", "schema_state", "updated_at"])
    record_event(
        ctx,
        events.HUB_CUT,
        {
            "id": str(hub.id),
            "slug": hub.slug,
            "mode": data.mode,
            "database": data.database,
            "copied": {table: rows for table, rows in data.copied.items() if rows},
            "dump": data.dump,
        },
    )
    # What any process kept of its apps came from control's rows: from now on they are its database's.
    on_commit(partial(activation.forget, hub.slug))
    return {"done": True}
