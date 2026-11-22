"""The row that says which hub a hub's database is (``base.tenancy.identity``)."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class HubIdentity(models.Model):
    """The one row that says which hub a hub's database is.

    Written when the database is made (its clone; the tests' ``conftest.py``) and read once per process and alias
    by ``use_hub`` (``base.tenancy.identity``): a database that says it is another hub is refused and nothing is served
    from it. Control's database has the table and no row.
    """

    hub_id = models.UUIDField(_("hub"), primary_key=True)

    class Meta:
        db_table = "base_hub_identity"
        verbose_name = _("hub identity")
        verbose_name_plural = _("hub identities")

    def __str__(self) -> str:
        return str(self.hub_id)
