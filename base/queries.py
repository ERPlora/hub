"""Read operations of base: the session's ``me``, the registry's row of a hub (``base.hub.get``), a demo's status
(``base.demo.get``) and the Home's three live queries (``base.setup.status``, ``base.widget.list``,
``base.bell.counters``; their rules are ``base.home``'s)."""

from typing import Any
from uuid import UUID

from django.contrib.auth.hashers import check_password
from django.http import HttpRequest
from django.db.models import Max
from django.utils import timezone, translation
from django.utils.translation import gettext, gettext_lazy
from live.context import OperationContext
from live.errors import NotFound, Unauthorized
from live.operations import operation

from base import access, home
from base.auth import saas_url
from base.models import (
    AccessSettings,
    Credential,
    EventDelivery,
    Hub,
    Membership,
    Profile,
    SessionOwner,
    TrustedDevice,
)
from base.operations import hub_id
from base.permissions import ADMINISTER_HUB, VIEW_HOME
from base.registry import hub_answer, internal_only
from base.relay import active_apps
from base.storage import media_url
from base.throttle import client_key
from base.schemas import (
    AccessDoorIn,
    AccessDoorOut,
    AccessSettingsIn,
    AccessSettingsOut,
    DeviceCurrentIn,
    DeviceCurrentOut,
    DeviceListIn,
    DeviceListOut,
    ProfileIn,
    ProfileOut,
    BellCountersIn,
    BellCountersOut,
    DemoSlugIn,
    DemoStatusOut,
    HubGetIn,
    HubOut,
    HubsBySlugIn,
    HubsBySlugOut,
    NoticeListIn,
    NoticeListOut,
    SessionMeIn,
    SessionMeOut,
    SetupStatusIn,
    SetupStatusOut,
    WidgetListIn,
    WidgetListOut,
)


@operation("base.session.me", kind="query", permission=None, input=SessionMeIn, output=SessionMeOut)
def session_me(ctx: OperationContext, data: SessionMeIn) -> dict[str, Any]:
    """The user, its permissions, and the menu and apps it may see on this scope, already translated.

    Menu and apps list modules only (``home.shown_modules``: the reference app only in development, the tests
    or a demo's hub): a platform app such as ``base`` is always on and never shows. ``demo`` says when the demo
    ends, on a demo's hub only. No permission: an anonymous visitor gets ``user: None`` and nothing else, which
    tells the SPA to send it to the login.
    """
    # Labels are lazy translations; a live re-run happens outside the request that activated the
    # language, so it is set here.
    demo = _demo_hub(ctx)
    with translation.override(ctx.language):
        visible = [config for config in home.shown_modules(demo_hub=demo is not None) if _can_see(ctx, config)]
        return {
            "user": _user(ctx.actor),
            "scope": {"kind": ctx.scope.kind, "key": ctx.scope.key},
            "permissions": sorted(ctx.permissions),
            "menu": [
                {
                    "id": config.label,
                    "label": str(config.verbose_name),
                    "items": [
                        {"path": nav.path, "label": str(nav.label), "icon": nav.icon} for nav in config.navigation
                    ],
                }
                for config in visible
                if config.navigation
            ],
            "apps": [{"label": config.label, "state": "on"} for config in visible],
            "language": ctx.language,
            "demo": None if demo is None else {"expires_at": demo.expires_at},
        }


def _demo_hub(ctx: OperationContext) -> Hub | None:
    """The demo's hub of this scope (its end, plan 2026-10-17, §1.6, and the reference app it shows), or ``None``
    on a business's hub."""
    if ctx.scope.kind != "host":
        return None
    return Hub.objects.filter(slug=ctx.scope.key, is_demo=True).first()


def _can_see(ctx: OperationContext, config: Any) -> bool:
    return ctx.has(f"{config.label}.view") or any(ctx.has(permission) for permission in config.permissions)


def _user(actor: Any) -> dict[str, str] | None:
    if actor is None:
        return None
    if not hasattr(actor, "get_username"):  # the platform itself (live.context.system_context)
        return {"id": str(actor), "label": str(actor)}
    # Named as in this hub: its «My profile» name, else its account's (APP-BASE-3).
    return {"id": str(actor.pk), "label": person_label(actor)}


@operation("base.hub.get", kind="query", permission=None, input=HubGetIn, output=HubOut)
def hub_get(ctx: OperationContext, data: HubGetIn) -> dict[str, Any]:
    """The registry's row of ``data.id`` (``GET /internal/hubs/{id}``), for the platform only: the SaaS asks it about
    a sign-up whose ``ready`` it never heard, and marks it ready when ``status`` is ``ready``."""
    internal_only(ctx)
    hub = Hub.objects.filter(pk=data.id).first()
    if hub is None:
        raise NotFound(gettext("No hub has this id."))
    return hub_answer(hub)


@operation("base.hub.by_slugs", kind="query", permission=None, input=HubsBySlugIn, output=HubsBySlugOut)
def hubs_by_slugs(ctx: OperationContext, data: HubsBySlugIn) -> dict[str, Any]:
    """The registry's status of each of ``data.slugs`` (``None`` without a row), in their order, for the platform
    only: ``seed_local_hubs --check`` asks it about ``a`` and ``b``."""
    internal_only(ctx)
    found = dict(Hub.objects.filter(slug__in=data.slugs).values_list("slug", "status"))
    return {"hubs": [{"slug": slug, "status": found.get(slug)} for slug in data.slugs]}


@operation("base.demo.get", kind="query", permission=None, input=DemoSlugIn, output=DemoStatusOut)
def demo_get(ctx: OperationContext, data: DemoSlugIn) -> dict[str, Any]:
    """The status of the demo ``data.slug``, for the platform only: ``manage.py demo_expire`` says it once done."""
    internal_only(ctx)
    hub = Hub.objects.filter(slug=data.slug, is_demo=True).first()
    if hub is None:
        raise NotFound(gettext("No demo has this address."))
    return {"slug": hub.slug, "status": hub.status, "expires_at": hub.expires_at}


# --- The Home (PLAN-HUB round 2026-10-21) -----------------------------------------------------------------------


@operation(
    "base.setup.status",
    kind="query",
    permission=VIEW_HOME,
    input=SetupStatusIn,
    output=SetupStatusOut,
    ai={
        "description": "Reads the checklist «Finish setting up your business» of this hub, as this person may see "
        "it: each step with its state (done, pending, or not available — ours, never something to ask the person "
        "to do), its level (needed to invoice, important, recommended), whether the person can set it up "
        "(otherwise an administrator must) and the screen that completes it; with how many are pending."
    },
)
def setup_status(ctx: OperationContext, data: SetupStatusIn) -> dict:
    """The old hub's ``hub.setup.status``: the platform's steps (``base.apps``, ``base.team``) and the modules'."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        on = active_apps(ctx.scope)
        modules = home.home_modules(on, demo_hub=bool(hub and hub.is_demo))
        items = _platform_steps(ctx, on) + home.module_steps(ctx, modules, hub.country if hub else "")
        return home.document(items)


def _platform_steps(ctx: OperationContext, on: frozenset[str]) -> list[dict]:
    """«Your apps» (some business app on) and «Your team» (more than one active person), for who runs the hub."""
    if not ctx.has(ADMINISTER_HUB):
        return []
    business_apps = home.business_apps()
    if any(label in on for label in business_apps):
        apps_state = home.STATE_DONE
    else:
        apps_state = home.STATE_PENDING if business_apps else home.STATE_UNAVAILABLE
    people = Membership.objects.filter(host=ctx.scope.key, user__is_active=True).count()
    return [
        home.item(
            "base.apps",
            "base",
            state=apps_state,
            required=True,
            level=home.level_of("base.apps", True),
            actionable=True,
            title=gettext_lazy("Your apps"),
            description=gettext_lazy("Turn on at least one business app so your till has something to sell."),
            icon="ion:grid-outline",
            route="/apps",
            order=10,
        ),
        home.item(
            "base.team",
            "base",
            state=home.STATE_DONE if people > 1 else home.STATE_PENDING,
            required=False,
            level=home.level_of("base.team", False),
            actionable=True,
            title=gettext_lazy("Your team"),
            description=gettext_lazy("Add the people who will use the till, each with their own way in."),
            icon="ion:people-outline",
            route="/employees",
            order=80,
        ),
    ]


@operation("base.widget.list", kind="query", permission=VIEW_HOME, input=WidgetListIn, output=WidgetListOut)
def widget_list(ctx: OperationContext, data: WidgetListIn) -> dict:
    """The panels of the apps on that this person may see, of the hub's vertical; the SPA follows each one's data."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        configs = home.home_modules(active_apps(ctx.scope), demo_hub=bool(hub and hub.is_demo))
        return {"widgets": home.widgets(ctx, configs, hub.vertical if hub else "")}


@operation("base.bell.counters", kind="query", permission=VIEW_HOME, input=BellCountersIn, output=BellCountersOut)
def bell_counters(ctx: OperationContext, data: BellCountersIn) -> dict:
    """The bell: the counters above zero of the apps on, and for who runs the hub the events the relay gave up on."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        modules = home.home_modules(active_apps(ctx.scope), demo_hub=bool(hub and hub.is_demo))
        counters = home.bell_counters(ctx, modules)
        if ctx.has(ADMINISTER_HUB):
            failed = EventDelivery.objects.filter(
                status=EventDelivery.Status.DEAD,
                event__scope_kind=ctx.scope.kind,
                event__scope_key=ctx.scope.key,
            ).count()
            if failed:
                counters.insert(
                    0,
                    {
                        "key": "base.failed_events",
                        "app": "base",
                        "count": failed,
                        "route": "/system#events",
                        "label": gettext("Failed events"),
                        "icon": "ion:warning-outline",
                    },
                )
        return {"counters": counters}


@operation("base.notice.list", kind="query", permission=VIEW_HOME, input=NoticeListIn, output=NoticeListOut)
def notice_list(ctx: OperationContext, data: NoticeListIn) -> dict:
    """The device's notices (PLAN-HUB round 2026-10-23): the rows the modules on tell, with their texts filled in."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        modules = home.home_modules(active_apps(ctx.scope), demo_hub=bool(hub and hub.is_demo))
        return {"notices": home.device_notices(ctx, modules), "sources": home.notice_sources(ctx, modules)}


# ── The way in: devices, PIN, badge, the business's dial and the person's profile (APP-BASE-3) ───────────────────


def access_settings() -> AccessSettings:
    """How the business asks who is at the till: its row, or the factory values (an unsaved row) without one. A
    stored value this build does not understand reads as the factory one, never as «not asking» (``base.access``)."""
    row = AccessSettings.objects.first() or AccessSettings()
    row.pin_policy = access.policy_or_default(row.pin_policy)
    row.pin_inactivity_minutes = access.inactivity_or_default(row.pin_inactivity_minutes)
    row.pin_length = access.pin_length_or_default(row.pin_length)
    return row


def person_label(user) -> str:
    """How ``user`` is named in this hub: its «My profile» name, else its erplora.com account's, else its username."""
    profile = Profile.objects.filter(username=user.get_username()).only("first_name", "last_name").first()
    if profile is not None and (name := f"{profile.first_name} {profile.last_name}".strip()):
        return name
    return user.get_full_name() or user.get_username()


def face_name(user) -> str:
    """How ``user`` shows on the grid of a till (BASE-G55, G60), seen by anyone at it: their name, never an email (the
    SaaS names an account without a name by its address: then the part before the «@»; gh:hub#2536)."""
    label = person_label(user)
    return label.split("@", 1)[0] if "@" in label else label


def device_of(request: HttpRequest | None, *, for_update: bool = False) -> TrustedDevice | None:
    """The hub's device this browser's cookie names, or ``None`` (no request or cookie, or a device the hub does not
    know: never one in which nobody entered with an account, nor one that was removed)."""
    token = request.COOKIES.get(access.DEVICE_COOKIE, "") if request is not None else ""
    if not token:
        return None
    devices = TrustedDevice.objects.select_for_update() if for_update else TrustedDevice.objects
    return devices.filter(token_digest=access.token_digest(token)).first()


def pin_people(slug: str, *, exclude: str = "") -> list[tuple[Credential, Any]]:
    """The active people of ``slug`` with a PIN, with their user (but ``exclude``, a username); in no order.

    Two reads, never a join: who is a member is control's (``Membership``) and the PINs are the hub's."""
    users = {
        membership.user.get_username(): membership.user
        for membership in Membership.objects.filter(host=slug, user__is_active=True).select_related("user")
    }
    users.pop(exclude, None)
    credentials = Credential.objects.filter(username__in=list(users)).exclude(pin_hash="")
    return [(credential, users[credential.username]) for credential in credentials]


def pin_owner(slug: str, person: str, pin: str) -> Any | None:
    """The active person of ``slug`` whose way in is ``person`` and whose PIN is ``pin``; else ``None``, whatever
    failed (an unknown id, another hub's person, a deactivated one, no PIN, a wrong one: the door says the same)."""
    try:
        person_id = UUID(person)
    except (TypeError, ValueError):
        return None
    credential = Credential.objects.filter(pk=person_id).exclude(pin_hash="").first()
    if credential is None:
        return None
    membership = (
        Membership.objects.filter(host=slug, user__username=credential.username, user__is_active=True)
        .select_related("user")
        .first()
    )
    if membership is None or not check_password(pin, credential.pin_hash):
        return None
    return membership.user


def pin_door_open(request: HttpRequest, slug: str) -> bool:
    """Whether this browser enters ``slug`` by the PIN pad: a shared device of the hub, a business that asks, and
    somebody of it with a PIN to choose."""
    device = device_of(request)
    if device is None or not access.pin_offered(device.mode, access_settings().pin_policy):
        return False
    return bool(pin_people(slug))


@operation("base.access.door", kind="query", permission=None, input=AccessDoorIn, output=AccessDoorOut)
def access_door(ctx: OperationContext, data: AccessDoorIn) -> dict[str, Any]:
    """The way in of the browser that asks (BASE-G55): on a shared device of the hub of a business that asks, the
    people of this hub with a PIN, by name and initials (never their email nor account) and the PIN's length.

    The grid reaches only whom the PIN would let in (the old Hub's HUB-F133): anyone else, and an address that tried
    too many wrong PINs (with how long it still waits), hears the same answer with nobody in it."""
    return _door(ctx)


@operation("base.access.faces", kind="query", permission=VIEW_HOME, input=AccessDoorIn, output=AccessDoorOut)
def access_faces(ctx: OperationContext, data: AccessDoorIn) -> dict[str, Any]:
    """The door's grid for a session: «Switch user» (BASE-G60), live, so a new PIN shows up and a person removed
    leaves without reloading the till."""
    return _door(ctx)


def _door(ctx: OperationContext) -> dict[str, Any]:
    settings = access_settings()
    device = device_of(ctx.request)
    offered = device is not None and access.pin_offered(device.mode, settings.pin_policy)
    wait = access.PIN_ADDRESS_LIMIT.wait(ctx.scope.key, client_key(ctx.request)) if offered else 0
    people = [] if not offered or wait else pin_people(ctx.scope.key)
    faces = sorted(
        ({"id": str(credential.pk), "name": (name := face_name(user)), "initials": access.initials(name)}
         for credential, user in people),
        key=lambda face: face["name"].casefold(),
    )
    return {
        "pin": offered and (bool(faces) or wait > 0),
        "pin_length": settings.pin_length,
        "people": faces,
        "wait": wait,
        # BASE-G57's «Upgrade plan» to a browser nobody is signed in on: erplora.com's plans, never this hub's id.
        "plan_url": saas_url("/store/plans"),
    }


def language_of(user, slug: str) -> str:
    """The language a person works in on ``slug``: their «My profile» choice, else the business's."""
    chosen = Profile.objects.filter(username=user.get_username()).values_list("language", flat=True).first()
    if chosen:
        return chosen
    return Hub.objects.filter(slug=slug).values_list("language", flat=True).first() or ""


def device_of_entry(request: HttpRequest) -> TrustedDevice | None:
    """The device an entry of this request was made on: the token it just left (a new device's) or the cookie's."""
    token = getattr(request, access.DEVICE_TOKEN_ATTR, None)
    if token:
        return TrustedDevice.objects.filter(token_digest=access.token_digest(token)).first()
    return device_of(request)


def has_pin(user) -> bool:
    return Credential.objects.filter(username=user.get_username()).exclude(pin_hash="").exists()


@operation(
    "base.device.current",
    kind="query",
    permission=VIEW_HOME,
    input=DeviceCurrentIn,
    output=DeviceCurrentOut,
    ai={"description": "Says whether the device the person is using is shared (a till: PIN, a shift) or personal."},
)
def device_current(ctx: OperationContext, data: DeviceCurrentIn) -> dict[str, Any]:
    """«This device» of Settings › General (BASE-G72): the mode of the browser that asks, and whether the hub knows it
    (someone entered with an account from it). An unknown one reads as shared, the strict mode."""
    device = device_of(ctx.request)
    if device is None:
        return {"known": False, "mode": access.SHARED, "mode_set_by": "", "mode_set_at": None}
    return {"known": True, "mode": device.mode, "mode_set_by": device.mode_set_by, "mode_set_at": device.mode_set_at}


@operation(
    "base.device.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=DeviceListIn,
    output=DeviceListOut,
    ai={
        "description": "Lists the devices someone entered this hub from: name, browser, shared or personal, whether "
        "it has a session open now and until when, who entered last and when, and which ones nobody used in 30 days."
    },
)
def device_list(ctx: OperationContext, data: DeviceListIn) -> dict[str, Any]:
    """«Devices» of Settings › General (BASE-G63): never a device's token, which is its proof. Phase 1 lists the rows
    of the shared table (every scope's), as every hub model does until each hub has its database."""
    now = timezone.now()
    here = device_of(ctx.request)
    devices = list(TrustedDevice.objects.order_by("-last_entry_at"))
    until = dict(
        SessionOwner.objects.filter(host=ctx.scope.key, device_id__in=[d.pk for d in devices], session__expire_date__gt=now)
        .values("device_id")
        .annotate(until=Max("session__expire_date"))
        .values_list("device_id", "until")
    )
    rows = [
        {
            "id": device.pk,
            "name": device.name,
            "agent": device.agent,
            "mode": device.mode,
            "current": here is not None and device.pk == here.pk,
            "in_use": device.pk in until,
            "session_until": until.get(device.pk),
            "last_entry_at": device.last_entry_at,
            "last_user": device.last_user_label,
            "created_at": device.created_at,
            "unused": _unused(device, here, now),
        }
        for device in devices
    ]
    return {"devices": rows, "unused": sum(row["unused"] for row in rows)}


def _unused(device: TrustedDevice, here: TrustedDevice | None, now) -> bool:
    return (here is None or device.pk != here.pk) and device.last_entry_at < now - access.UNUSED_AFTER


def unused_devices(here: TrustedDevice | None):
    """The devices «Remove the unused» removes (BASE-G66): nobody entered on them in 30 days, never the one in hand."""
    old = TrustedDevice.objects.filter(last_entry_at__lt=timezone.now() - access.UNUSED_AFTER)
    return old.exclude(pk=here.pk) if here is not None else old


@operation(
    "base.access.settings",
    kind="query",
    permission=VIEW_HOME,
    input=AccessSettingsIn,
    output=AccessSettingsOut,
    ai={
        "description": "Reads how the business asks who is at the till: whether the PIN pad shows, when it asks "
        "again (after some minutes without use, or once per shift) and how many digits a PIN has."
    },
)
def access_settings_get(ctx: OperationContext, data: AccessSettingsIn) -> dict[str, Any]:
    """The «PIN pad» card of Settings › General (BASE-G62, G151): what the Hub confirmed, for everyone of the hub."""
    row = access_settings()
    return {
        "pin_policy": row.pin_policy,
        "pin_inactivity_minutes": row.pin_inactivity_minutes,
        "pin_length": row.pin_length,
        "can_change": ctx.has(ADMINISTER_HUB),
    }


@operation(
    "base.profile.get",
    kind="query",
    permission=VIEW_HOME,
    input=ProfileIn,
    output=ProfileOut,
    ai={"description": "Reads the person's own profile in this hub: name, contact email, language and appearance."},
)
def profile_get(ctx: OperationContext, data: ProfileIn) -> dict[str, Any]:
    """«My profile» (BASE-G125): always the profile of whoever asks; without a row, the account's name."""
    user = signed_in(ctx)
    profile = Profile.objects.filter(username=user.get_username()).first()
    role = Membership.objects.filter(user=user, host=ctx.scope.key).values_list("role", flat=True).first() or ""
    return {
        "first_name": profile.first_name if profile else user.first_name,
        "last_name": profile.last_name if profile else user.last_name,
        "contact_email": profile.contact_email if profile else "",
        "avatar_url": avatar_url(ctx, profile.avatar) if profile and profile.avatar else "",
        "language": profile.language if profile else "",
        "theme_mode": profile.theme_mode if profile else "",
        "palette": profile.palette if profile else "",
        "role": role,
        "has_pin": has_pin(user),
        "pin_length": access_settings().pin_length,
    }


def signed_in(ctx: OperationContext):
    """The person of the session, or 401: «My profile» and one's own PIN are nobody's without one."""
    if ctx.actor is None or not hasattr(ctx.actor, "get_username"):
        raise Unauthorized(gettext("Sign in to see your profile."), code="base.sign_in_required")
    return ctx.actor


def avatar_url(ctx: OperationContext, name: str) -> str:
    return media_url(hub_id(ctx.scope), name)


def appearance_of(user) -> dict[str, str]:
    """The mode and palette a person chose in «My profile» (BASE-G125), for the shell to paint on any device they enter;
    empty, the business's."""
    chosen = Profile.objects.filter(username=user.get_username()).values("theme_mode", "palette").first()
    return {"theme_mode": chosen["theme_mode"], "palette": chosen["palette"]} if chosen else {"theme_mode": "", "palette": ""}


def shell_access(request: HttpRequest, slug: str) -> dict[str, Any]:
    """What the shell needs of this session's way in (``hub-home``'s ``access``, ``base.spa``): how it was opened,
    whether «Switch user» is offered (BASE-G60: a shared device of the hub of a business that asks, with somebody on
    its grid) and, when the business always asks on such a device, after how many idle minutes it locks (BASE-G59)."""
    credential = (
        SessionOwner.objects.filter(session_id=request.session.session_key).values_list("credential", flat=True).first()
        or SessionOwner.Credential.ACCOUNT
    )
    device = device_of(request)
    settings = access_settings()
    offered = device is not None and access.pin_offered(device.mode, settings.pin_policy)
    return {
        "credential": credential,
        "switch_user": offered and bool(pin_people(slug)),
        "idle_minutes": settings.pin_inactivity_minutes if offered and settings.pin_policy == access.ALWAYS else None,
    }
