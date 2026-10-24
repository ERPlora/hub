"""What System's operations share and touches no database (APP-BASE-7): an app's name as the business knows it, and
the release running (``APP_VERSION``, ``APP_RELEASED_AT``: the image's commit and its time, fixed by the build)."""

import datetime as dt

from django.apps import apps
from django.utils import timezone

#: How much of the commit's sha names the release: what ``git`` shows.
VERSION_LENGTH = 7


def app_name(label: str) -> str:
    """An app's name as the business knows it, in the active language; the label of an app the deployment no longer
    has (an event an app retired recorded), never an error."""
    try:
        return str(apps.get_app_config(label).verbose_name)
    except LookupError:
        return label


def version(app_version: str) -> str:
    """The release: its commit, short; ``dev`` without one (local development)."""
    return app_version[:VERSION_LENGTH] or "dev"


def released_at(value: str) -> dt.datetime | None:
    """When the release was published (ISO 8601 with its offset), in UTC; ``None`` when there is none or it cannot be
    read: a date is never made up."""
    try:
        moment = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment.astimezone(dt.UTC) if timezone.is_aware(moment) else None
