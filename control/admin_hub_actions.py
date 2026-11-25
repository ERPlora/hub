"""What the actions of Hubs that move a hub, or put it back from a copy, ask on their confirmation page and
tell the staff: the cluster and when, the night a move waits for and how long each hub can stay closed."""

import datetime as dt

from django import forms
from django.template.defaultfilters import filesizeformat
from django.utils.timesince import timesince
from django.utils.translation import gettext, gettext_lazy, ngettext, pgettext, pgettext_lazy

from base.business import zone_name, zone_of
from base.tenancy.move.bucket import longest_closure
from control.models import Cluster, Hub
from control.schemas import MOVE_AT_NIGHT, MOVE_NOW
from control.services.move import NIGHT_ENDS, NIGHT_STARTS


def the_night() -> dict[str, str]:
    """The window a move asked for the night starts in, as a page says it: ``{"start": "03:00", "end": "05:00"}``."""
    return {"start": f"{NIGHT_STARTS:%H:%M}", "end": f"{NIGHT_ENDS:%H:%M}"}


def a_span(span: dt.timedelta) -> str:
    """A span of time as the staff reads it, in the admin's language: ``1 hour, 7 minutes``."""
    start = dt.datetime(2000, 1, 1, tzinfo=dt.UTC)
    return timesince(start, start + span)


#: The actions that close each hub chosen while its database is copied: their page says for how long under each one.
CLOSING_ACTIONS = ("move_to_cluster", "restore_from_a_copy")


def closure_said(hub: Hub) -> str:
    """How long a move or a restore can keep ``hub`` closed by the size of its database (``database_bytes``: ``None``
    when it could not be read), as their confirmation page says it under the hub."""
    size = getattr(hub, "database_bytes", None)
    span = a_span(longest_closure(size))
    if size is None:
        return gettext("Size unknown: closed for up to %(span)s") % {"span": span}
    return gettext("%(size)s: closed for up to %(span)s") % {"size": filesizeformat(size), "span": span}


def closed_for(hubs: list[Hub]) -> str:
    """How long ``hubs`` can stay closed in all, copied one after another, as the staff is told."""
    return a_span(sum((longest_closure(getattr(hub, "database_bytes", None)) for hub in hubs), dt.timedelta()))


def move_said(when: str, count: int) -> str:
    """What the staff is told of ``count`` hubs asked to move ``when``; ``closed``: how long all of them take, as they
    move one after another."""
    if when == MOVE_AT_NIGHT:
        return ngettext(
            "%(count)d hub will move to %(cluster)s in its next night, starting between %(start)s and %(end)s on "
            "its own clock: open until then, and closed while it moves, for up to %(closed)s.",
            "%(count)d hubs will move to %(cluster)s in their next night, each starting between %(start)s and "
            "%(end)s on its own clock: open until then, and closed while they move one after another, for up to "
            "%(closed)s in all.",
            count,
        )
    return ngettext(
        "%(count)d hub will move to %(cluster)s: closed while it moves, for up to %(closed)s.",
        "%(count)d hubs will move to %(cluster)s, one after another: each closed until its own move ends, for up to "
        "%(closed)s in all.",
        count,
    )


def on_its_clock(moment: dt.datetime, timezone_name: str) -> str:
    """A moment on a business's own clock, with it: ``2026-11-17 03:00 Europe/Madrid``."""
    zone = zone_of(timezone_name)
    return f"{moment.astimezone(zone):%Y-%m-%d %H:%M} {zone_name(zone)}"


class MoveToClusterForm(forms.Form):
    """The cluster the chosen hubs move to, an open one (``control.hub.move`` checks its room, hub by hub), and when:
    in each business's next night, first, or now."""

    cluster = forms.ModelChoiceField(
        queryset=Cluster.objects.filter(is_open=True).order_by("name"),
        label=gettext_lazy("cluster"),
        empty_label=None,
    )
    # Radio buttons, as RDS asks when a change applies: their text wraps on a phone, a select's runs past its edge.
    when = forms.ChoiceField(
        label=pgettext_lazy("move", "When"), initial=MOVE_AT_NIGHT, widget=forms.RadioSelect(attrs={"class": "radiolist"})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        at_night = gettext("In its next night, between %(start)s and %(end)s of the business's time") % the_night()
        self.fields["when"].choices = [(MOVE_AT_NIGHT, at_night), (MOVE_NOW, pgettext("move", "Now"))]


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
