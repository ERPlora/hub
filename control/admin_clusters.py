"""The database clusters in control's Hub admin, registered by ``control.admin``.

**Clusters** lists each with its writer, its PgBouncer, whether it is open to new hubs, its limit, the hubs on it
against that limit, its secret and the total size of its hubs' databases. Its writes are operations
(``control.services``): the form's save is ``control.cluster.create``/``update`` and shows on its fields what they
refused (a secret that does not resolve, a writer under its hubs); «Close to new hubs» is ``control.cluster.close``;
a delete is ``control.cluster.delete``, and one that holds hubs is refused (Django lists them, as the foreign key
protects it). A deletion is logged once its operation deleted the cluster, never before.
"""

from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponseRedirect
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils.translation import gettext_lazy, ngettext, pgettext, pgettext_lazy
from live.errors import OperationError

from control.admin_shared import SizedChangeList, is_platform_admin, saved_by, sizes_of, staff_context
from control.models import Cluster, Hub
from control.schemas import ClusterIdIn, ClusterIn, ClusterUpdateIn
from control.services.clusters import CLUSTER_FIELDS, cluster_close, cluster_create, cluster_delete, cluster_update


def no_limit() -> str:
    return pgettext("cluster limit", "no limit")


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
