"""The freeze switch in control's Hub admin, registered by ``control.admin``.

**Freeze** is the one switch that freezes the platform for a database upgrade: ticked, the worker makes, drops and
moves no database and ``migrate_hubs`` refuses to start, while the relay, the tasks and VeriFactu go on. Its form
saves through ``control.freeze.set`` (shows on its field what it refuses); while frozen its pages say how many hubs
the worker is still working on (``control.freeze.get``), the 0 the staff waits for before the upgrade. It is never
deleted, and added only if its row is missing.
"""

from django import forms
from django.contrib import admin, messages
from django.http import HttpRequest
from django.utils.translation import gettext, ngettext, pgettext_lazy

from control.admin_shared import is_platform_admin, saved_by, staff_context
from control.models.freeze import Freeze
from control.queries import freeze_get
from control.schemas import FreezeGetIn, FreezeIn
from control.services.freeze import freeze_set


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
