"""Deleting a row in a hub whose database lacks the tables of a module that hangs from it (hub#778, out of hub#608).

``Model.delete()``, ``QuerySet.delete()`` and the admin's confirmation page all walk the row's reverse relations with
Django's ``Collector``, which asks with ``.using()``: the ``TenantRouter`` never sees those queries, so
:class:`~base.tenancy.context.AppNotCreated` does not cover them and they reach Postgres as ``relation … does not exist``.
Nothing hangs from a table that is not there, so such a relation is passed over and the row goes away as usual.

The cut is ``Collector.related_objects``: the one method every walk goes through (``NestedObjects``, the admin's, calls it
with ``super()``) and the earliest one that knows the related model. It answers an empty queryset, which sends no SQL
whichever way the walk then uses it (read for a PROTECT, deleted for a CASCADE, updated for a SET_NULL). There is no
public way in: ``Model.delete()`` and ``QuerySet.delete()`` build the ``Collector`` themselves, so this replaces the
method on the class, once, when the app is ready (:func:`install`). Upgrading Django, the tests of
``base/tenancy/tests/test_deletion.py`` fail if the method stops being what the walk calls.

Only what is sure is passed over:

- only the database the active hub's context works on: what that row says decides nothing about another hub's database
  or about the migrator's ``…__ddl`` alias, where the tables are being made, and no context says nothing at all;
- only a module :func:`base.activation.has_tables` says is missing, the router's own reading: every module with tables
  keeps its PROTECT, CASCADE and SET_NULL. That reading can be behind a table just made, up to its cache's minute; what
  is passed over then is still refused by the foreign key in the database at the ``COMMIT``, and no row is left hanging.
"""

from django.db.models.deletion import Collector

from base import activation
from base.tenancy import context

_walk_the_relation = Collector.related_objects


def _lacks_the_tables(related_model, using: str) -> bool:
    active = context.peek()
    if active is None or active.kind != context.HUB or active.alias != using:
        return False
    return not activation.has_tables(active.hub, related_model._meta.app_label)


def related_objects(self, related_model, related_fields, objs):
    """``Collector.related_objects``, with nothing to walk where the related model's module has no tables."""
    walked = _walk_the_relation(self, related_model, related_fields, objs)
    return walked.none() if _lacks_the_tables(related_model, self.using) else walked


def install() -> None:
    """Called once by ``base.apps.BaseConfig.ready``."""
    Collector.related_objects = related_objects
