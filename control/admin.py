"""The Hub admin of control (``hubs.erplora.com/admin``, staff only): the database clusters with their limit, and the
hubs with their database.

- **Hubs** is the registry's admin (``base.admin.HubAdmin``: read only, «Expire now») with each hub's database
  (``db_name``, or control's while it shares it), cluster, schema and size, filtered by cluster, status and schema.
  An empty ``Hub.cluster`` is the settings' own server, and the list, its filter and the hub's page say so in words
  («default server») once the hub's database was made (``base.registry.database_is_made``). The sizes come from
  ``control.cluster.sizes``, once per cluster on the page, kept ten minutes; a cluster that cannot be measured is said
  in a warning and its hubs show no size.

- **«Move to cluster…»** asks ``control.hub.move`` for each chosen hub, with an open cluster and when: in the business's
  next night (first, as a database's maintenance waits for its window) or now. One asked for the night stays open and
  its cluster says where and when it goes, on the business's own clock, until the worker starts it; «Cancel the move»
  takes it away until then, and undoes a started one. Its page says under each hub how long it can stay closed by the
  size of its database (``base.tenancy.move.longest_closure``), and what the staff is told adds them up, as the hubs
  move one after another.
- **«Restore from a copy…»** (BASE-F114) asks ``control.hub.restore`` for each chosen hub, with the temporary
  cluster its copy is on and the moment it is of; the worker restores it (``base.tenancy.restore``), or refuses it for
  its fiscal records, and then the hub's page says why in its ``last_error``, as the worker noted it. While it is
  restored, the hub's cluster says where the copy comes from, as a move says where it goes.
- **«Restore to a separate copy…»** (BASE-F114) asks ``control.hub.restore_aside`` the same way: the worker
  makes the copy next to the business, which is never closed nor changed, and **Separate copies** lists each one (read
  only, for support too) with its moment, how it went, its database and until when it is kept.
- **«Recover into the business…»** on Separate copies (BASE-F114) asks ``control.copy.recover`` for each
  chosen copy, with what to bring back (the apps that say what they give back from a copy,
  ``base.tenancy.recovery``); the worker creates in the business what it lacks, each record by its app's own
  operation, and **Recoveries** lists each one (read only, for support too) with what came back and why not.

Django reads an app's admin from its ``admin.py``, so this one also registers the parts beside it: the clusters
(``control.admin_clusters``), the recoveries (``control.admin_recoveries``) and the freeze switch
(``control.admin_freeze``).

Only the platform's admins (staff and superuser) add, change, close or delete; support reads (its ``view_*``
permissions). Nothing here writes the ORM: every write is an operation, called with the staff member's context.
"""

import datetime as dt
from collections.abc import Callable

from django import forms
from django.contrib import admin, messages
from django.http import HttpRequest
from django.contrib.admin import helpers
from django.template.defaultfilters import filesizeformat
from django.template.response import TemplateResponse
from django.utils.translation import gettext, gettext_lazy, ngettext, pgettext, pgettext_lazy
from live.errors import OperationError

from base import admin as base_admin
from base.registry import database_is_made
from base.tenancy.move import MOVED_COPY_DAYS, longest_closure
from control.admin_clusters import ClusterAdmin
from control.admin_freeze import FreezeAdmin
from control.admin_hub_actions import (
    CLOSING_ACTIONS,
    MoveToClusterForm,
    RestoreFromACopyForm,
    a_span,
    closed_for,
    closure_said,
    move_said,
    on_its_clock,
    the_night,
)
from control.admin_recoveries import CopyRecoveryAdmin, RecoverForm, recoverable_names
from control.admin_shared import SizedChangeList, copy_said, is_platform_admin, sizes_of, staff_context, utc
from control.models import Cluster, CopyRecovery, Freeze, Hub, RestoredCopy
from control.schemas import (
    CopyRecoverIn,
    HubIdIn,
    HubMoveIn,
    HubRestoreIn,
)
from control.services import (
    copy_recover,
    hub_move,
    hub_move_cancel,
    hub_restore,
    hub_restore_aside,
)


def default_server() -> str:
    """What an empty ``Hub.cluster`` means: the settings' own server (``base.tenancy.connections``)."""
    return pgettext("hub cluster", "default server")


#: The confirmation pages of «Move to cluster…», «Restore from a copy…», «Restore to a separate copy…» and «Recover into
#: the business…».
MOVE_TEMPLATE = "admin/control/hub/move_to_cluster.html"
RESTORE_TEMPLATE = "admin/control/hub/restore_from_a_copy.html"
ASIDE_TEMPLATE = "admin/control/hub/restore_aside.html"
RECOVER_TEMPLATE = "admin/control/restoredcopy/recover.html"


class AsksFirst:
    """The actions of an admin that ask for something on a confirmation page first, then ask its operation of each
    chosen row (Hubs, Separate copies). The admin says ``confirmation_row(obj)``, each one's id, name and database on
    that page, ``confirmation_note(obj, action)``, what that page says under it (nothing by default), and
    ``chosen_name(obj)``, its name in what the staff is told."""

    def confirmation(  # noqa: PLR0913, PLR0917
        self, request: HttpRequest, chosen, form: forms.Form, action: str, title: str, template: str, **more
    ):
        """The confirmation page of ``action`` for ``chosen``: what it does and its ``form``, asked again until
        valid."""
        context = {
            **self.admin_site.each_context(request),
            "title": title,
            "opts": self.model._meta,
            "rows": [(*self.confirmation_row(obj), self.confirmation_note(obj, action)) for obj in chosen],
            "form": form,
            "action": action,
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            **more,
        }
        return TemplateResponse(request, template, context)

    def confirmation_note(self, obj, action: str) -> str:
        return ""

    def ask_each(self, request: HttpRequest, chosen, ask: Callable[[object], object]) -> int:
        """Ask ``ask`` (an operation) of each chosen row: what it refuses is said with its name; how many were asked."""
        asked = 0
        for obj in chosen:
            try:
                ask(obj)
            except OperationError as refused:
                self.message_user(request, f"{self.chosen_name(obj)}: {refused.message}", messages.ERROR)
                continue
            asked += 1
        return asked


class ClusterListFilter(admin.RelatedFieldListFilter):
    """The filter by cluster, whose choice for the hubs on none is called what it is: the default server."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.empty_value_display = default_server()


admin.site.register(Cluster, ClusterAdmin)

# The registry's admin is base's (read only, «Expire now»); control's adds where each hub's data lives.
admin.site.unregister(Hub)


@admin.register(Hub)
class HubAdmin(AsksFirst, base_admin.HubAdmin):
    """The registry of hubs with each one's database, cluster, schema and size (see the module)."""

    list_display = (
        "slug",
        "name",
        "status",
        "database",
        "on_cluster",
        "schema_state",
        "database_size",
        "is_demo",
        "expires_at",
        "vertical",
        "created_at",
    )
    list_filter = ("status", ("cluster", ClusterListFilter), "schema_state", "is_demo")
    list_select_related = ("cluster", "moving_to", "move_scheduled_to", "restoring_from")
    actions = [
        *base_admin.HubAdmin.actions,
        "move_to_cluster",
        "cancel_the_move",
        "restore_from_a_copy",
        "restore_aside",
    ]
    # Never a form's field, even on the page of a hub on no cluster, where ``on_cluster`` takes its place.
    exclude = ("cluster",)

    def get_readonly_fields(self, request: HttpRequest, obj=None):
        """A hub's page says an empty ``cluster`` as the list does; one on a cluster keeps Django's link to it."""
        fields = super().get_readonly_fields(request, obj)
        if obj is None or obj.cluster_id:
            return fields
        return ["on_cluster" if field == "cluster" else field for field in fields]

    @admin.action(description=gettext_lazy("Move to cluster…"), permissions=["move"])
    def move_to_cluster(self, request: HttpRequest, queryset):
        """Choose an open cluster on a confirmation page, then ask each chosen hub to move there
        (``control.hub.move``): the worker moves it, its host answering 503 «maintenance» meanwhile. The page and what
        the staff is told say how long each can stay closed, by the size of its database."""
        hubs = list(queryset)
        self.attach_sizes(request, hubs)
        form = MoveToClusterForm(request.POST if "apply" in request.POST else None)
        if not form.is_bound or not form.is_valid():
            title, limit = gettext("Move to cluster"), a_span(longest_closure(None))
            return self.confirmation(
                request, hubs, form, "move_to_cluster", title, MOVE_TEMPLATE, limit=limit, **the_night()
            )
        target, when = form.cleaned_data["cluster"], form.cleaned_data["when"]
        ctx = staff_context(request)
        moved: list[Hub] = []

        def ask(hub: Hub) -> None:
            hub_move(ctx, HubMoveIn(hub=hub.pk, cluster=target.pk, when=when))
            moved.append(hub)

        if self.ask_each(request, hubs, ask):
            values = {"count": len(moved), "cluster": target.name, "closed": closed_for(moved)} | the_night()
            self.message_user(request, move_said(when, len(moved)) % values, messages.SUCCESS)
        return None

    @admin.action(description=gettext_lazy("Cancel the move"), permissions=["move"])
    def cancel_the_move(self, request: HttpRequest, queryset) -> None:
        """Ask the worker to undo each chosen hub's move (``control.hub.move_cancel``): back on its own cluster. One
        asked for the night that has not started is taken away: it stays where it is, open."""
        ctx = staff_context(request)
        answers: list = []
        self.ask_each(request, queryset, lambda hub: answers.append(hub_move_cancel(ctx, HubIdIn(id=hub.pk))))
        undone = sum(1 for answer in answers if answer.moving_to is not None)
        if undone:
            self.message_user(
                request,
                ngettext(
                    "%(count)d move will be undone: the hub goes back to its cluster within a minute.",
                    "%(count)d moves will be undone: each hub goes back to its cluster within a minute.",
                    undone,
                )
                % {"count": undone},
                messages.SUCCESS,
            )
        if unscheduled := len(answers) - undone:
            self.message_user(
                request,
                ngettext(
                    "%(count)d move asked for the night was cancelled: the hub stays where it is, open.",
                    "%(count)d moves asked for the night were cancelled: each hub stays where it is, open.",
                    unscheduled,
                )
                % {"count": unscheduled},
                messages.SUCCESS,
            )

    @admin.action(description=gettext_lazy("Restore from a copy…"), permissions=["restore"])
    def restore_from_a_copy(self, request: HttpRequest, queryset):
        """Choose the temporary cluster the hubs' copy is on and the moment it is of on a confirmation page, then ask
        each chosen hub to be put back as it was (``control.hub.restore``): the worker restores it, its host answering
        503 «maintenance» meanwhile, or refuses it for its fiscal records, the reason in its ``last_error``. The page
        and what the staff is told say how long each can stay closed, by the size of its database."""
        hubs = list(queryset)
        self.attach_sizes(request, hubs)
        return self.from_a_copy(
            request,
            hubs,
            "restore_from_a_copy",
            gettext("Restore from a copy"),
            RESTORE_TEMPLATE,
            hub_restore,
            lambda asked: ngettext(
                "%(count)d hub will be restored from %(cluster)s as it was at %(moment)s: closed while it is "
                "restored, for up to %(closed)s. If it is refused, its page says why under «last error».",
                "%(count)d hubs will be restored from %(cluster)s as they were at %(moment)s, one after another: each "
                "closed until its own restore ends, for up to %(closed)s in all. If one is refused, its page says why "
                "under «last error».",
                asked,
            ),
        )

    @admin.action(description=gettext_lazy("Restore to a separate copy…"), permissions=["restore"])
    def restore_aside(self, request: HttpRequest, queryset):
        """As «Restore from a copy…», but each chosen hub gets a separate copy of its database as it was, made next to
        it (``control.hub.restore_aside``): the business is never closed nor changed, its fiscal records stop nothing,
        and Separate copies lists the copy."""
        return self.from_a_copy(
            request,
            queryset,
            "restore_aside",
            gettext("Restore to a separate copy"),
            ASIDE_TEMPLATE,
            hub_restore_aside,
            lambda asked: ngettext(
                "%(count)d hub will get a separate copy as it was at %(moment)s, made from %(cluster)s: the business "
                "stays open as it is. Separate copies lists it, and says if it could not be made.",
                "%(count)d hubs will get a separate copy each as they were at %(moment)s, made from %(cluster)s: the "
                "businesses stay open as they are. Separate copies lists them, and says if one could not be made.",
                asked,
            ),
        )

    def from_a_copy(self, request: HttpRequest, hubs, action: str, title: str, template: str, operation, said):  # noqa: PLR0913, PLR0917
        """The temporary cluster and the moment asked on ``action``'s confirmation page, then ``operation`` asked of
        each hub with them; ``said(count)``: what the staff is told of those asked (``closed``: how long all of them
        can stay closed)."""
        form = RestoreFromACopyForm(request.POST if "apply" in request.POST else None)
        if not form.is_bound or not form.is_valid():
            return self.confirmation(request, hubs, form, action, title, template, kept_days=MOVED_COPY_DAYS)
        source, at = form.cleaned_data["cluster"], form.cleaned_data["at"]
        ctx = staff_context(request)
        asked: list[Hub] = []

        def ask(hub: Hub) -> None:
            operation(ctx, HubRestoreIn(hub=hub.pk, cluster=source.pk, at=at))
            asked.append(hub)

        if self.ask_each(request, hubs, ask):
            values = {"count": len(asked), "cluster": source.name, "moment": utc(at), "closed": closed_for(asked)}
            self.message_user(request, said(len(asked)) % values, messages.SUCCESS)
        return None

    def confirmation_row(self, hub: Hub) -> tuple:
        return hub.pk, hub.slug, hub.db_name

    def confirmation_note(self, hub: Hub, action: str) -> str:
        return closure_said(hub) if action in CLOSING_ACTIONS else ""

    def chosen_name(self, hub: Hub) -> str:
        return hub.slug

    def has_move_permission(self, request: HttpRequest) -> bool:
        return is_platform_admin(request)

    def has_restore_permission(self, request: HttpRequest) -> bool:
        return is_platform_admin(request)

    def get_changelist(self, request: HttpRequest, **kwargs):
        return SizedChangeList

    def attach_sizes(self, request: HttpRequest, hubs) -> None:
        # Only a hub with a database of its own has a size; the query leaves out the purged ones itself.
        measured = {hub.cluster_id for hub in hubs if hub.db_name}
        sizes = {cluster_id: sizes_of(request, cluster_id) for cluster_id in sorted(measured, key=str)}
        for hub in hubs:
            on_its_server = sizes.get(hub.cluster_id) or {}
            hub.database_bytes = on_its_server.get(hub.db_name) if hub.db_name else None

    @admin.display(description=gettext_lazy("database"), ordering="db_name")
    def database(self, hub: Hub) -> str:
        return hub.db_name or pgettext("hub database", "shared with control")

    @admin.display(description=gettext_lazy("cluster"), ordering="cluster__name")
    def on_cluster(self, hub: Hub) -> str:
        if hub.cluster_id:
            here = hub.cluster.name
        elif hub.db_name and database_is_made(hub):
            here = default_server()
        else:
            here = self.get_empty_value_display()
        if hub.moving_to_id:
            return f"{here} → {hub.moving_to.name}"
        if hub.restoring_from_id:
            return f"{here} ← {hub.restoring_from.name}"
        if hub.move_scheduled_to_id:
            return pgettext("scheduled move", "%(here)s (to %(there)s at %(moment)s)") % {
                "here": here,
                "there": hub.move_scheduled_to.name,
                "moment": on_its_clock(hub.move_scheduled_for, hub.timezone),
            }
        return here

    @admin.display(description=pgettext_lazy("hub database", "size"))
    def database_size(self, hub: Hub) -> str:
        size = getattr(hub, "database_bytes", None)
        return filesizeformat(size) if size is not None else self.get_empty_value_display()


@admin.register(RestoredCopy)
class RestoredCopyAdmin(AsksFirst, base_admin.ReadOnlyAdmin):
    """The separate copies of hubs as they were at a moment (BASE-F114): asked from Hubs with «Restore to a
    separate copy…», made and dropped by the worker; read only, for support too. «Recover into the business…»
    asks a made copy to give back what its business lacks, for the platform's admins only."""

    actions = ["recover_into_the_business"]

    # What the staff looks for at a glance, in four columns a phone shows whole; its database (searchable), who asked,
    # when, from where and on which cluster are on its page: a database's name is 40-odd characters in one piece.
    list_display = ("made_from", "status", "kept_until", "last_error")
    list_filter = ("status",)
    list_select_related = ("hub", "cluster")
    search_fields = ("hub__slug", "db_name")
    fields = (
        "hub",
        "moment",
        "status",
        "db_name",
        "on_cluster",
        "source",
        "kept_until",
        "asked_by",
        "asked_at",
        "made_at",
        "last_error",
    )
    readonly_fields = fields

    class Media:
        # A long last error breaks inside its cell and, up to a tablet's width, the filter goes under the list.
        css = {"all": ["control/admin.css"]}

    @admin.display(description=gettext_lazy("separate copy"), ordering="restore_point")
    def made_from(self, copy: RestoredCopy) -> str:
        return copy_said(copy)

    @admin.display(description=pgettext_lazy("restore", "Moment"), ordering="restore_point")
    def moment(self, copy: RestoredCopy) -> str:
        return utc(copy.restore_point)

    @admin.display(description=gettext_lazy("cluster"))
    def on_cluster(self, copy: RestoredCopy) -> str:
        return copy.cluster.name if copy.cluster_id else default_server()

    @admin.display(description=pgettext_lazy("separate copy", "kept until"))
    def kept_until(self, copy: RestoredCopy) -> str:
        if copy.made_at is None:
            return self.get_empty_value_display()
        return utc(copy.made_at + dt.timedelta(days=MOVED_COPY_DAYS))

    @admin.action(description=gettext_lazy("Recover into the business…"), permissions=["recover"])
    def recover_into_the_business(self, request: HttpRequest, queryset):
        """Choose what to bring back on a confirmation page, then ask each chosen copy to give it back into its business
        (``control.copy.recover``): the worker creates what the business lacks, each record by its app's own
        operation, and Recoveries says how it went."""
        form = RecoverForm(request.POST if "apply" in request.POST else None)
        copies = queryset.select_related("hub")
        if not form.is_bound or not form.is_valid():
            title = gettext("Recover into the business")
            return self.confirmation(request, copies, form, "recover_into_the_business", title, RECOVER_TEMPLATE)
        apps = form.cleaned_data["apps"]
        ctx = staff_context(request)
        asked = self.ask_each(
            request, copies, lambda copy: copy_recover(ctx, CopyRecoverIn(copy_id=copy.pk, apps=apps))
        )
        if asked:
            self.message_user(
                request,
                ngettext(
                    "%(count)d separate copy will give back %(what)s into its business within a few minutes: "
                    "Recoveries says how it went.",
                    "%(count)d separate copies will give back %(what)s into their businesses within a few minutes: "
                    "Recoveries says how each went.",
                    asked,
                )
                % {"count": asked, "what": recoverable_names(apps)},
                messages.SUCCESS,
            )
        return None

    def has_recover_permission(self, request: HttpRequest) -> bool:
        return is_platform_admin(request)

    def confirmation_row(self, copy: RestoredCopy) -> tuple:
        return copy.pk, str(copy), copy.db_name

    def chosen_name(self, copy: RestoredCopy) -> str:
        return str(copy)


admin.site.register(CopyRecovery, CopyRecoveryAdmin)
admin.site.register(Freeze, FreezeAdmin)
