"""The Hub admin of control (``hubs.erplora.com/admin``, staff only): the database clusters with their limit, and the
hubs with their database (round 2026-10-30b of PLAN-DB, decision 1 of Ioan; tranche S7, part 1).

- **Clusters** lists each with its writer, its PgBouncer, whether it is open to new hubs, its limit, the hubs on it
  against that limit, its secret and the total size of its hubs' databases. Its writes are operations
  (``control.services``): the form's save is ``control.cluster.create``/``update`` and shows on its fields what they
  refused (a secret that does not resolve, a writer under its hubs); «Close to new hubs» is ``control.cluster.close``;
  a delete is ``control.cluster.delete``, and one that holds hubs is refused (Django lists them, as the foreign key
  protects it). A deletion is logged once its operation deleted the cluster, never before.
- **Hubs** is the registry's admin (``base.admin.HubAdmin``: read only, «Expire now») with each hub's database
  (``db_name``, or control's while it shares it), cluster, schema and size, filtered by cluster, status and schema.
  An empty ``Hub.cluster`` is the settings' own server, and the list, its filter and the hub's page say so in words
  («default server») once the hub's database was made (``base.registry.database_is_made``). The sizes come from
  ``control.cluster.sizes``, once per cluster on the page, kept ten minutes; a cluster that cannot be measured is said
  in a warning and its hubs show no size.

- **«Restore from a copy…»** (hub#1198, BASE-F114) asks ``control.hub.restore`` for each chosen hub, with the temporary
  cluster its copy is on and the moment it is of; the worker restores it (``base.tenancy.restore``), or refuses it for
  its fiscal records, and then the hub's page says why in its ``last_error``, as the worker noted it. While it is
  restored, the hub's cluster says where the copy comes from, as a move says where it goes.
- **«Restore to a separate copy…»** (hub#1213, BASE-F114) asks ``control.hub.restore_aside`` the same way: the worker
  makes the copy next to the business, which is never closed nor changed, and **Separate copies** lists each one (read
  only, for support too) with its moment, how it went, its database and until when it is kept.

- **Freeze** is the one switch that freezes the platform for a database upgrade (hub#930; PLAN-DB round 2026-11-04e,
  «Congelar»): ticked, the worker makes, drops and moves no database and ``migrate_hubs`` refuses to start, while the
  relay, the tasks and VeriFactu go on. Its form saves through ``control.freeze.set`` (shows on its field what it
  refuses); while frozen its pages say how many hubs the worker is still working on (``control.freeze.get``), the 0 the
  staff waits for before the upgrade. It is never deleted, and added only if its row is missing.

Only the platform's admins (staff and superuser) add, change, close or delete; support reads (its ``view_*``
permissions). Nothing here writes the ORM: every write is an operation, called with the staff member's context.
"""

import datetime as dt
from collections.abc import Callable

import pydantic
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.views.main import ChangeList
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponseRedirect
from django.contrib.admin import helpers
from django.template.defaultfilters import filesizeformat
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.translation import gettext, gettext_lazy, ngettext, pgettext, pgettext_lazy
from live.context import OperationContext
from live.errors import OperationError

from base import admin as base_admin
from base.registry import REGISTRY_SCOPE, database_is_made
from base.tenancy.move import MOVED_COPY_DAYS
from control.models import Cluster, Freeze, Hub, RestoredCopy
from control.queries import cluster_sizes, freeze_get
from control.schemas import (
    ClusterIdIn,
    ClusterIn,
    ClusterSizesIn,
    ClusterUpdateIn,
    FreezeGetIn,
    FreezeIn,
    HubIdIn,
    HubMoveIn,
    HubRestoreIn,
)
from control.services import (
    CLUSTER_FIELDS,
    cluster_close,
    cluster_create,
    cluster_delete,
    cluster_update,
    freeze_set,
    hub_move,
    hub_move_cancel,
    hub_restore,
    hub_restore_aside,
)


def staff_context(request: HttpRequest) -> OperationContext:
    """The staff member's context for control's operations: the registry's scope, in the admin's language."""
    return OperationContext(
        scope=REGISTRY_SCOPE,
        actor=request.user,
        permissions=frozenset(),
        language=getattr(request, "LANGUAGE_CODE", "en"),
        request=request,
    )


def is_platform_admin(request: HttpRequest) -> bool:
    """Staff and superuser (``platform_admin``): support only reads."""
    return request.user.is_staff and request.user.is_superuser


def utc(moment: dt.datetime) -> str:
    """A moment as the Hub admin says it, whatever its language: ``2026-11-09 14:30 UTC``."""
    return f"{moment.astimezone(dt.UTC):%Y-%m-%d %H:%M} UTC"


def no_limit() -> str:
    return pgettext("cluster limit", "no limit")


def default_server() -> str:
    """What an empty ``Hub.cluster`` means: the settings' own server (``base.tenancy.connections``)."""
    return pgettext("hub cluster", "default server")


def sizes_of(request: HttpRequest, cluster_id) -> dict[str, int] | None:
    """The sizes of the hubs' databases on ``cluster_id`` (none: the settings' own server), or ``None`` after saying
    in a warning why they could not be read."""
    try:
        return cluster_sizes(staff_context(request), ClusterSizesIn(cluster=cluster_id)).databases
    except OperationError as refused:
        messages.warning(request, refused.message)
        return None


def saved_by(form: forms.ModelForm, save: Callable[[], object]) -> object | None:
    """Save ``form`` through ``save``, its operation, once Django's own checks passed: what the operation's schema or the
    operation itself refuses is shown on its field (or on the form), and nothing is saved (``None``); else its answer."""
    try:
        return save()
    except pydantic.ValidationError as invalid:
        for error in invalid.errors():
            field = error["loc"][0] if error["loc"] and error["loc"][0] in form.fields else None
            form.add_error(field, error["msg"])
    except OperationError as refused:
        for field, message in (refused.fields or {None: refused.message}).items():
            form.add_error(field if field in form.fields else None, message)
    return None


class SizedChangeList(ChangeList):
    """A changelist whose page knows its databases' sizes (``model_admin.attach_sizes``), measured once per page."""

    def get_results(self, request):
        super().get_results(request)
        self.model_admin.attach_sizes(request, self.result_list)


class ClusterForm(forms.ModelForm):
    """The cluster's form, saved by its operation once Django's own checks passed: what the operation refuses is shown
    on its field; what it saved is the form's instance. ``request`` is set by ``ClusterAdmin.get_form``."""

    request: HttpRequest | None = None

    class Meta:
        model = Cluster
        fields = list(CLUSTER_FIELDS)

    def _post_clean(self):
        super()._post_clean()
        if self.errors:
            return
        values = {field: self.cleaned_data[field] for field in CLUSTER_FIELDS}
        ctx = staff_context(self.request)
        if self.instance._state.adding:
            saved = saved_by(self, lambda: cluster_create(ctx, ClusterIn(**values)))
        else:
            saved = saved_by(self, lambda: cluster_update(ctx, ClusterUpdateIn(id=self.instance.pk, **values)))
        if saved is not None:
            self.instance = Cluster.objects.get(pk=saved.id)


@admin.register(Cluster)
class ClusterAdmin(admin.ModelAdmin):
    """The database clusters (see the module): every write through ``control.cluster.*``."""

    form = ClusterForm
    list_display = (
        "name",
        "writer",
        "pgbouncer",
        "is_open",
        "limit",
        "hubs_of_limit",
        "secret_name",
        "total_size",
    )
    list_filter = ("is_open",)
    search_fields = ("name", "host", "pooler_host", "secret_name")
    ordering = ("name",)
    actions = ["close_to_new_hubs"]

    def get_queryset(self, request: HttpRequest):
        # The same hubs the placement counts: all but the purged demos, which have no database left.
        return (
            super()
            .get_queryset(request)
            .annotate(living_hubs=Count("hubs", filter=~Q(hubs__status=Hub.Status.PURGED)))
        )

    def get_changelist(self, request: HttpRequest, **kwargs):
        return SizedChangeList

    def get_form(self, request: HttpRequest, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change=change, **kwargs)
        return type(form.__name__, (form,), {"request": request})

    def attach_sizes(self, request: HttpRequest, clusters) -> None:
        for cluster in clusters:
            sizes = sizes_of(request, cluster.pk)
            cluster.total_database_size = sum(sizes.values()) if sizes else None

    @admin.display(description=pgettext_lazy("cluster", "writer"), ordering="host")
    def writer(self, cluster: Cluster) -> str:
        return f"{cluster.host}:{cluster.port}"

    @admin.display(description=pgettext_lazy("cluster", "PgBouncer"), ordering="pooler_host")
    def pgbouncer(self, cluster: Cluster) -> str:
        if not cluster.pooler_host:
            return pgettext("cluster pgbouncer", "none: its writer")
        return f"{cluster.pooler_host}:{cluster.pooler_port}"

    @admin.display(description=pgettext_lazy("cluster limit", "limit"), ordering="max_hubs")
    def limit(self, cluster: Cluster) -> str:
        return str(cluster.max_hubs) if cluster.max_hubs else no_limit()

    @admin.display(description=pgettext_lazy("cluster", "hubs / limit"), ordering="living_hubs")
    def hubs_of_limit(self, cluster: Cluster) -> str:
        return f"{cluster.living_hubs} / {cluster.max_hubs if cluster.max_hubs else no_limit()}"

    @admin.display(description=pgettext_lazy("cluster", "total size"))
    def total_size(self, cluster: Cluster) -> str:
        size = getattr(cluster, "total_database_size", None)
        return filesizeformat(size) if size else self.get_empty_value_display()

    @admin.action(description=gettext_lazy("Close to new hubs"), permissions=["close"])
    def close_to_new_hubs(self, request: HttpRequest, queryset) -> None:
        """No new hub is placed on the chosen clusters from now on; the hubs on them stay there."""
        ctx = staff_context(request)
        closed = 0
        for cluster in queryset:
            try:
                cluster_close(ctx, ClusterIdIn(id=cluster.pk))
            except OperationError as refused:
                self.message_user(request, f"{cluster.name}: {refused.message}", messages.ERROR)
                continue
            closed += 1
        if closed:
            self.message_user(
                request,
                ngettext(
                    "%(count)d cluster closed to new hubs: the hubs on it stay there.",
                    "%(count)d clusters closed to new hubs: the hubs on them stay there.",
                    closed,
                )
                % {"count": closed},
                messages.SUCCESS,
            )

    def has_close_permission(self, request: HttpRequest) -> bool:
        return is_platform_admin(request)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return is_platform_admin(request)

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return is_platform_admin(request)

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return is_platform_admin(request)

    def get_deleted_objects(self, objs, request: HttpRequest):
        """Django's, but the hubs on a cluster are protected, never deleted with it: the page lists them as what
        stops the deletion, not as rows the staff member lacks the permission to delete."""
        deleted, model_count, perms_needed, protected = super().get_deleted_objects(objs, request)
        if protected:
            perms_needed = set()
        return deleted, model_count, perms_needed, protected

    def save_model(self, request: HttpRequest, obj, form, change) -> None:
        """Nothing to write: the form's operation saved it (``ClusterForm``)."""

    def log_deletions(self, request: HttpRequest, queryset) -> None:
        """Deferred: each deletion is logged once its operation deleted the cluster (a refused one logs nothing)."""

    def delete_model(self, request: HttpRequest, obj) -> None:
        cluster_delete(staff_context(request), ClusterIdIn(id=obj.pk))
        super().log_deletions(request, [obj])

    def delete_queryset(self, request: HttpRequest, queryset) -> None:
        ctx = staff_context(request)
        for cluster in queryset:
            try:
                cluster_delete(ctx, ClusterIdIn(id=cluster.pk))
            except OperationError as refused:
                self.message_user(request, f"{cluster.name}: {refused.message}", messages.ERROR)
                continue
            super().log_deletions(request, [cluster])

    def delete_view(self, request: HttpRequest, object_id, extra_context=None):
        """Django's, but a refusal of the operation (a hub placed on it meanwhile) is said on the cluster's page."""
        try:
            return super().delete_view(request, object_id, extra_context)
        except OperationError as refused:
            self.message_user(request, refused.message, messages.ERROR)
            return HttpResponseRedirect(reverse("admin:control_cluster_change", args=[object_id]))


class MoveToClusterForm(forms.Form):
    """The cluster the chosen hubs move to: an open one (``control.hub.move`` checks its room, hub by hub)."""

    cluster = forms.ModelChoiceField(
        queryset=Cluster.objects.filter(is_open=True).order_by("name"),
        label=gettext_lazy("cluster"),
        empty_label=None,
    )


class RestoreFromACopyForm(forms.Form):
    """The temporary cluster the chosen hubs' copy is on (a point-in-time restore of their cluster, registered closed to
    new hubs) and the moment it is of; ``control.hub.restore`` checks the rest, hub by hub."""

    cluster = forms.ModelChoiceField(
        queryset=Cluster.objects.filter(is_open=False).order_by("name"),
        label=pgettext_lazy("restore", "Temporary cluster"),
        empty_label=None,
    )
    at = forms.DateTimeField(
        label=pgettext_lazy("restore", "Moment"),
        help_text=gettext_lazy(
            "The moment the temporary cluster was restored to, with its time zone: 2026-11-09T14:30:00Z is UTC."
        ),
    )


#: The confirmation pages of «Move to cluster…», «Restore from a copy…» and «Restore to a separate copy…».
MOVE_TEMPLATE = "admin/control/hub/move_to_cluster.html"
RESTORE_TEMPLATE = "admin/control/hub/restore_from_a_copy.html"
ASIDE_TEMPLATE = "admin/control/hub/restore_aside.html"


class ClusterListFilter(admin.RelatedFieldListFilter):
    """The filter by cluster, whose choice for the hubs on none is called what it is: the default server."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.empty_value_display = default_server()


# The registry's admin is base's (read only, «Expire now»); control's adds where each hub's data lives.
admin.site.unregister(Hub)


@admin.register(Hub)
class HubAdmin(base_admin.HubAdmin):
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
    list_select_related = ("cluster", "moving_to", "restoring_from")
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
        (``control.hub.move``): the worker moves it, its host answering 503 «maintenance» meanwhile."""
        form = MoveToClusterForm(request.POST if "apply" in request.POST else None)
        if not form.is_bound or not form.is_valid():
            return self.confirmation(request, queryset, form, "move_to_cluster", gettext("Move to cluster"), MOVE_TEMPLATE)
        target = form.cleaned_data["cluster"]
        ctx = staff_context(request)
        asked = self.ask_each(request, queryset, lambda hub: hub_move(ctx, HubMoveIn(hub=hub.pk, cluster=target.pk)))
        if asked:
            self.message_user(
                request,
                ngettext(
                    "%(count)d hub will move to %(cluster)s: closed for a few minutes while it moves.",
                    "%(count)d hubs will move to %(cluster)s: each closed for a few minutes while it moves.",
                    asked,
                )
                % {"count": asked, "cluster": target.name},
                messages.SUCCESS,
            )
        return None

    @admin.action(description=gettext_lazy("Cancel the move"), permissions=["move"])
    def cancel_the_move(self, request: HttpRequest, queryset) -> None:
        """Ask the worker to undo each chosen hub's move (``control.hub.move_cancel``): back on its own cluster."""
        ctx = staff_context(request)
        asked = self.ask_each(request, queryset, lambda hub: hub_move_cancel(ctx, HubIdIn(id=hub.pk)))
        if asked:
            self.message_user(
                request,
                ngettext(
                    "%(count)d move will be undone: the hub goes back to its cluster within a minute.",
                    "%(count)d moves will be undone: each hub goes back to its cluster within a minute.",
                    asked,
                )
                % {"count": asked},
                messages.SUCCESS,
            )

    @admin.action(description=gettext_lazy("Restore from a copy…"), permissions=["restore"])
    def restore_from_a_copy(self, request: HttpRequest, queryset):
        """Choose the temporary cluster the hubs' copy is on and the moment it is of on a confirmation page, then ask
        each chosen hub to be put back as it was (``control.hub.restore``): the worker restores it, its host answering
        503 «maintenance» meanwhile, or refuses it for its fiscal records, the reason in its ``last_error``."""
        return self.from_a_copy(
            request,
            queryset,
            "restore_from_a_copy",
            gettext("Restore from a copy"),
            RESTORE_TEMPLATE,
            hub_restore,
            lambda asked: ngettext(
                "%(count)d hub will be restored from %(cluster)s as it was at %(moment)s: closed for a few minutes "
                "while it is restored. If it is refused, its page says why under «last error».",
                "%(count)d hubs will be restored from %(cluster)s as they were at %(moment)s: each closed for a few "
                "minutes while it is restored. If one is refused, its page says why under «last error».",
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

    def from_a_copy(self, request: HttpRequest, hubs, action: str, title: str, template: str, operation, said):
        """The temporary cluster and the moment asked on ``action``'s confirmation page, then ``operation`` asked of
        each hub with them; ``said(count)``: what the staff is told of those asked."""
        form = RestoreFromACopyForm(request.POST if "apply" in request.POST else None)
        if not form.is_bound or not form.is_valid():
            return self.confirmation(request, hubs, form, action, title, template, kept_days=MOVED_COPY_DAYS)
        source, at = form.cleaned_data["cluster"], form.cleaned_data["at"]
        ctx = staff_context(request)
        asked = self.ask_each(
            request, hubs, lambda hub: operation(ctx, HubRestoreIn(hub=hub.pk, cluster=source.pk, at=at))
        )
        if asked:
            self.message_user(
                request,
                said(asked) % {"count": asked, "cluster": source.name, "moment": utc(at)},
                messages.SUCCESS,
            )
        return None

    def confirmation(self, request: HttpRequest, hubs, form: forms.Form, action: str, title: str, template: str, **more):
        """The confirmation page of ``action`` for ``hubs``: what it does and its ``form``, asked again until valid."""
        context = {
            **self.admin_site.each_context(request),
            "title": title,
            "opts": self.model._meta,
            "hubs": hubs,
            "form": form,
            "action": action,
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            **more,
        }
        return TemplateResponse(request, template, context)

    def ask_each(self, request: HttpRequest, hubs, ask: Callable[[Hub], object]) -> int:
        """Ask ``ask`` (an operation) of each hub: what it refuses is said with the hub's slug; how many were asked."""
        asked = 0
        for hub in hubs:
            try:
                ask(hub)
            except OperationError as refused:
                self.message_user(request, f"{hub.slug}: {refused.message}", messages.ERROR)
                continue
            asked += 1
        return asked

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
        return here

    @admin.display(description=pgettext_lazy("hub database", "size"))
    def database_size(self, hub: Hub) -> str:
        size = getattr(hub, "database_bytes", None)
        return filesizeformat(size) if size is not None else self.get_empty_value_display()


@admin.register(RestoredCopy)
class RestoredCopyAdmin(base_admin.ReadOnlyAdmin):
    """The separate copies of hubs as they were at a moment (hub#1213, BASE-F114): asked from Hubs with «Restore to a
    separate copy…», made and dropped by the worker; read only, for support too."""

    # What the staff looks for at a glance; its database (searchable), who asked, when, from where and on which cluster
    # are on its page: a database's name is 40-odd characters in one piece, which pushes the rest out of sight.
    list_display = ("hub", "moment", "status", "kept_until", "last_error")
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


class FreezeForm(forms.ModelForm):
    """The switch's form, saved by ``control.freeze.set`` once Django's own checks passed: what the operation refuses is
    shown on its field. ``request`` is set by ``FreezeAdmin.get_form``."""

    request: HttpRequest | None = None

    class Meta:
        model = Freeze
        fields = ["frozen", "reason"]

    def _post_clean(self):
        super()._post_clean()
        if self.errors:
            return
        wanted = {"frozen": self.cleaned_data["frozen"], "reason": self.cleaned_data["reason"]}
        if saved_by(self, lambda: freeze_set(staff_context(self.request), FreezeIn(**wanted))) is not None:
            self.instance = Freeze.objects.get()


@admin.register(Freeze)
class FreezeAdmin(admin.ModelAdmin):
    """The freeze switch (see the module): its one row, every write through ``control.freeze.set``."""

    form = FreezeForm
    # Its state in words is the link to its page; the icon beside it, as every yes/no of the admin.
    list_display = ("state", "frozen", "reason", "since", "by")
    readonly_fields = ("since", "by")

    def get_form(self, request: HttpRequest, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change=change, **kwargs)
        return type(form.__name__, (form,), {"request": request})

    @admin.display(description=pgettext_lazy("freeze", "state"))
    def state(self, switch: Freeze) -> str:
        return str(switch)

    def say_what_is_running(self, request: HttpRequest) -> None:
        """While frozen, how many hubs the worker is still working on: none, the upgrade may start."""
        state = freeze_get(staff_context(request), FreezeGetIn())
        if not state.frozen:
            return
        if state.working:
            self.message_user(
                request,
                ngettext(
                    "Frozen: the worker is still working on %(count)d hub; wait until it is 0 before the upgrade.",
                    "Frozen: the worker is still working on %(count)d hubs; wait until it is 0 before the upgrade.",
                    state.working,
                )
                % {"count": state.working},
                messages.WARNING,
            )
        else:
            self.message_user(
                request,
                gettext("Frozen: the worker is working on no hub: the database may be upgraded."),
                messages.SUCCESS,
            )

    def changelist_view(self, request: HttpRequest, extra_context=None):
        if request.method == "GET":
            self.say_what_is_running(request)
        return super().changelist_view(request, extra_context)

    def change_view(self, request: HttpRequest, object_id, form_url="", extra_context=None):
        if request.method == "GET":
            self.say_what_is_running(request)
        return super().change_view(request, object_id, form_url, extra_context)

    def has_add_permission(self, request: HttpRequest) -> bool:
        # Its one row is control's migration's: added here only where it is missing.
        return is_platform_admin(request) and not Freeze.objects.exists()

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return is_platform_admin(request)

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def save_model(self, request: HttpRequest, obj, form, change) -> None:
        """Nothing to write: the form's operation saved it (``FreezeForm``)."""
