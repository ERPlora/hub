"""The places where the business works."""

from django.db import models
from django.db.models import Q
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel


#: The name of the location every hub's database is born with (``base/migrations/0015_location``), kept in canonical
#: English and read in the reader's language while it keeps that name.
DEFAULT_LOCATION_NAME = "Main"
DEFAULT_LOCATION_LABEL = pgettext_lazy("location", "Main")
LOCATION_NAME_MAX_LENGTH = 100


class Location(UUIDModel):
    """A place where the business works: a shop, a bar, a salon.

    A hub is one business, with its tax id and one database: a business with several premises keeps them here, as
    Square, Shopify, Lightspeed and Odoo keep several shops in one company. Every hub's database is born with exactly
    one, the default «Main» (its migration plants it; a new hub inherits it from the template it is cloned from), so a
    business with one place never sees any. At most one is the default (a partial unique index) and the default is
    always active.
    """

    name = models.CharField(pgettext_lazy("location", "name"), max_length=LOCATION_NAME_MAX_LENGTH)
    is_default = models.BooleanField(pgettext_lazy("location", "default"), default=False)
    is_active = models.BooleanField(pgettext_lazy("location", "active"), default=True)
    created_at = models.DateTimeField(pgettext_lazy("location", "created at"), auto_now_add=True)

    class Meta:
        verbose_name = pgettext_lazy("location", "location")
        verbose_name_plural = pgettext_lazy("location", "locations")
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"], condition=Q(is_default=True), name="base_location_one_default"
            ),
            models.CheckConstraint(
                condition=Q(is_active=True) | Q(is_default=False), name="base_location_default_active"
            ),
        ]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        """The default's factory name in the reader's language; any other name as it was given."""
        if self.is_default and self.name == DEFAULT_LOCATION_NAME:
            return str(DEFAULT_LOCATION_LABEL)
        return self.name
