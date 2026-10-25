"""Django admin of base: only on the platform host (``hubs.erplora.com``, locally ``hubs.localhost:8000``), for the staff.

Every other host answers 404 to ``/admin/`` (``base.middleware``, round 13, PLAN §18.1).

The deep link ``/admin/hub/<slug>/`` (round 13, PLAN §18.1), where «Open in the Hub admin» of the
SaaS admin lands, chooses the hub the admin works on: it is kept in the session and every admin
page shows it in a banner (``templates/admin/base_site.html`` through :func:`admin_hub_context`).
"""

from django.contrib import admin, messages
from django.http import Http404, HttpRequest, HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext, gettext_lazy, ngettext
from live.context import OperationContext
from live.errors import OperationError
from live.slugs import validate_hub_slug

from base.models import AppActivation, Hub, Location, Membership, TaskSchedule
from base.registry import REGISTRY_SCOPE
from base.schemas import DemoSlugIn
from base.services import demo_expire

#: The hub chosen for the admin (its slug), set by the deep link.
ADMIN_HUB_SESSION_KEY = "admin_hub"


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "host", "role")
    list_filter = ("role", "host")
    search_fields = ("user__username", "user__email", "host")
    list_select_related = ("user",)


@admin.register(Hub)
class HubAdmin(admin.ModelAdmin):
    """The registry of hubs (plan 2026-10-17, §1.1), read only: the SaaS writes it (``PUT /internal/hubs/{id}``)
    and the worker purges the demos; nothing here adds, changes or deletes a row by hand. «Expire now» ends the
    chosen demos at once through ``base.demo.expire``, for the platform's admins (superusers) only."""

    list_display = ("slug", "name", "status", "is_demo", "expires_at", "vertical", "created_at")
    list_filter = ("status", "is_demo")
    search_fields = ("slug", "name", "=id")
    ordering = ("slug",)
    actions = ["expire_now"]

    @admin.action(description=gettext_lazy("Expire now"), permissions=["expire"])
    def expire_now(self, request: HttpRequest, queryset) -> None:
        """End each chosen demo now: its host answers 410 at once and the worker purges it on its next pass."""
        ctx = OperationContext(
            scope=REGISTRY_SCOPE,
            actor=request.user,
            permissions=frozenset(),
            language=getattr(request, "LANGUAGE_CODE", "en"),
            request=request,
        )
        ended = 0
        for hub in queryset:
            if not hub.is_demo:
                self.message_user(
                    request,
                    gettext("%(slug)s is no demo: only a demo ends here.") % {"slug": hub.slug},
                    messages.WARNING,
                )
                continue
            try:
                demo_expire(ctx, DemoSlugIn(slug=hub.slug))
            except OperationError as refused:
                self.message_user(request, f"{hub.slug}: {refused.message}", messages.ERROR)
                continue
            ended += 1
        if ended:
            self.message_user(
                request,
                ngettext(
                    "%(count)d demo ended: its address answers 410 now and it is purged within a minute.",
                    "%(count)d demos ended: their addresses answer 410 now and they are purged within a minute.",
                    ended,
                )
                % {"count": ended},
                messages.SUCCESS,
            )

    def has_expire_permission(self, request: HttpRequest) -> bool:
        """Only the platform's admins (``platform_admin``: staff and superuser) end a demo; support only reads."""
        return request.user.is_staff and request.user.is_superuser

    def get_readonly_fields(self, request: HttpRequest, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


@admin.register(TaskSchedule)
class TaskScheduleAdmin(admin.ModelAdmin):
    """The apps' scheduled tasks (``base.scheduler``): the apps declare them and the worker writes them when it
    starts, so none is added here and the declaration is read-only; ``next_run`` can be brought forward (the
    task runs on the worker's next tick once it has come)."""

    list_display = ("app_label", "name", "operation", "cron", "next_run", "last_run")
    list_filter = ("app_label",)
    search_fields = ("app_label", "name", "operation")
    fields = ("app_label", "name", "operation", "cron", "next_run", "last_run")
    readonly_fields = ("app_label", "name", "operation", "cron", "last_run")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    """The business's locations (round 2026-10-24b): no screen of the Hub shows them yet. Which one is the default is
    read only (every hub's database is born with «Main» as its default, ``base/migrations/0015``), the default stays
    active and is never deleted, so a hub always has one; another place is added, renamed, turned off or deleted."""

    list_display = ("name", "is_default", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("-is_default", "name")

    def get_readonly_fields(self, request: HttpRequest, obj=None):
        if obj is not None and obj.is_default:
            return ("is_default", "is_active", "created_at")
        return ("is_default", "created_at")

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        if obj is not None and obj.is_default:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(AppActivation)
class AppActivationAdmin(admin.ModelAdmin):
    """Which apps each business turned on or off, and which it chose (PLAN-HUB §9), as they are: read only. Turning
    one on or off is ``base.app.enable``/``base.app.disable`` (the apps it needs, the plan's limit, the event), never a
    row edited by hand; a business without rows has every app on (``base.activation``)."""

    list_display = ("host", "app", "state", "chosen", "changed_at")
    list_filter = ("state", "chosen")
    search_fields = ("host", "app")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


def open_hub(request: HttpRequest, slug: str) -> HttpResponseRedirect:
    """Choose ``slug`` (a business's or a demo's) for this admin session and go to the admin's index; 404 if it is no
    hub's slug.

    Routed behind ``admin.site.admin_view`` (staff only). Phase 2 plugs the hub-DB selector here
    (``use_hub`` over ``hub_<hex>``, PLAN §17).
    """
    try:
        # A demo (``demo-<8 hex>``) is a hub of the registry too.
        validate_hub_slug(slug, allow_demo=True)
    except ValueError as exc:
        raise Http404(f"{slug!r} is no hub's slug ({exc}).") from None
    request.session[ADMIN_HUB_SESSION_KEY] = slug
    return HttpResponseRedirect(reverse("admin:index"))


def admin_hub_context(request: HttpRequest) -> dict[str, str]:
    """Context processor: ``admin_hub_label`` («Hub: a») when the admin session has chosen a hub."""
    session = getattr(request, "session", None)
    slug = session.get(ADMIN_HUB_SESSION_KEY) if session is not None else None
    if not slug:
        return {}
    return {"admin_hub_label": gettext("Hub: %(slug)s") % {"slug": slug}}
