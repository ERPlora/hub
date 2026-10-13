"""The Hub's mirror of ``shared.app`` and ``shared.app_doc``, in the SaaS's ``saas`` database.

The SaaS owns the tables and migrates them (``saas-next/apps``); the columns are written once in
``live.shared_catalog``. Here ``managed = False``: the Hub never creates or alters them, and
``SharedRouter`` forbids migrating them on any alias. The unique constraint repeats the SaaS's own,
by name, so that a test database built from these models has it too.
"""

from django.db import models
from live.shared_catalog import APP_DOC_TABLE, APP_TABLE, AbstractApp, AbstractAppDoc


class App(AbstractApp):
    """A module some release of the Hub registered; ``listed = False`` keeps it out of the store."""

    class Meta:
        managed = False
        db_table = APP_TABLE

    def __str__(self) -> str:
        return self.id


class AppDoc(AbstractAppDoc):
    """The user documentation of a module in one language."""

    class Meta:
        managed = False
        db_table = APP_DOC_TABLE
        constraints = [
            models.UniqueConstraint(
                fields=["app", "lang"], name="shared_app_doc_app_lang_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.app_id} ({self.lang})"
