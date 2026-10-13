"""Django admin of base (only on the platform host ``hubs.erplora.com`` in production; phase 1 serves it everywhere).

The deep link ``/admin/hub/<slug>/`` (round 13, PLAN §18.1), where «Open in the Hub admin» of the
SaaS admin lands, chooses the hub the admin works on: it is kept in the session and every admin
page shows it in a banner (``templates/admin/base_site.html`` through :func:`admin_hub_context`).
"""

from django.contrib import admin
from django.http import Http404, HttpRequest, HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext
from live.slugs import validate_hub_slug

from base.models import Membership

#: The hub chosen for the admin (its slug), set by the deep link.
ADMIN_HUB_SESSION_KEY = "admin_hub"


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "host", "role")
    list_filter = ("role", "host")
    search_fields = ("user__username", "user__email", "host")
    list_select_related = ("user",)


def open_hub(request: HttpRequest, slug: str) -> HttpResponseRedirect:
    """Choose ``slug`` for this admin session and go to the admin's index; 404 if it is no hub's slug.

    Routed behind ``admin.site.admin_view`` (staff only). Phase 2 plugs the hub-DB selector here
    (``use_hub`` over ``hub_<hex>``, PLAN §17).
    """
    try:
        validate_hub_slug(slug)
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
