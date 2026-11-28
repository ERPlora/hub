"""Which station a product or a category of Inventory goes to."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.kitchen.models.fields import Audited
from apps.kitchen.models.stations import Station


class ProductRoute(Audited):
    """A product of Inventory goes to this station."""

    product = models.OneToOneField(
        "inventory.Product",
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name=_("product"),
    )
    station = models.ForeignKey(
        Station,
        on_delete=models.CASCADE,
        related_name="product_routes",
        verbose_name=_("station"),
    )

    class Meta:
        verbose_name = _("product route")
        verbose_name_plural = _("product routes")

    def __str__(self) -> str:
        return f"{self.product_id} → {self.station_id}"


class CategoryRoute(Audited):
    """A category of Inventory goes to this station (when its product has no route of its own)."""

    category = models.OneToOneField(
        "inventory.Category",
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name=_("category"),
    )
    station = models.ForeignKey(
        Station,
        on_delete=models.CASCADE,
        related_name="category_routes",
        verbose_name=_("station"),
    )

    class Meta:
        verbose_name = _("category route")
        verbose_name_plural = _("category routes")

    def __str__(self) -> str:
        return f"{self.category_id} → {self.station_id}"
