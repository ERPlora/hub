"""What the models of the sale app share: exact quantities, percentages, who did something and JSON lists."""

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q

QUANTITY = {"max_digits": 15, "decimal_places": 3}
PERCENT = {"max_digits": 5, "decimal_places": 2}
ACTOR_MAX_LENGTH = 128


def _percent_range(
    name: str, field: str = "discount_percent"
) -> models.CheckConstraint:
    return models.CheckConstraint(
        condition=Q(**{f"{field}__gte": 0, f"{field}__lte": 100}), name=name
    )


def _actor(verbose_name) -> models.CharField:
    """Who did something, as the operation's actor names them; empty when there is none."""
    return models.CharField(verbose_name, max_length=ACTOR_MAX_LENGTH, blank=True)


def _json_list(verbose_name) -> models.JSONField:
    """A list kept as JSON; ``db_default``: a process still on the previous code inserts rows without it."""
    return models.JSONField(verbose_name, default=list, blank=True, db_default=[], encoder=DjangoJSONEncoder)
