"""What the parts of control's Hub admin share: the staff member's context and permission, a moment and a
separate copy as a list says them, the sizes of the hubs' databases on a cluster, and a form saved by its
operation."""

import datetime as dt
from collections.abc import Callable

import pydantic
from django import forms
from django.contrib import messages
from django.contrib.admin.views.main import ChangeList
from django.http import HttpRequest
from django.utils.html import format_html
from live.context import OperationContext
from live.errors import OperationError

from base.registry import REGISTRY_SCOPE
from control.models.copies import RestoredCopy
from control.queries import cluster_sizes
from control.schemas import ClusterSizesIn


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


def copy_said(copy: RestoredCopy) -> str:
    """A separate copy in a list: its business and its moment on two lines, so a phone keeps room for the rest."""
    return format_html("{}<br>{}", copy.hub.slug, utc(copy.restore_point))


def sizes_of(request: HttpRequest, cluster_id) -> dict[str, int] | None:
    """The sizes of the hubs' databases on ``cluster_id`` (none: the settings' own server), or ``None`` after saying
    in a warning why they could not be read; once per request (an action's list measured them before the action)."""
    known = request.__dict__.setdefault("control_sizes", {})
    if cluster_id not in known:
        try:
            known[cluster_id] = cluster_sizes(staff_context(request), ClusterSizesIn(cluster=cluster_id)).databases
        except OperationError as refused:
            messages.warning(request, refused.message)
            known[cluster_id] = None
    return known[cluster_id]


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
