"""The fiscal documents of a business's database, read for its fiscal archive (``base.tenancy.fiscal_archive``, which
``base.tenancy.offboarding`` hands :func:`documents`).

Every app that keeps fiscal documents names, in ``fiscal_archive_models`` on its config, the models that hold them;
each is read whole, with its base manager (no row a default manager hides is left out), a page at a time by its key
(UUIDv7: in the order the rows were made), and written as Django's JSON Lines serializer writes it: what is stored,
never rebuilt. Read in the database of the active hub.
"""

from collections.abc import Iterator

from django.apps import apps as django_apps
from django.core import serializers
from django.db.models import Model

#: How many rows are read at once.
PAGE_ROWS = 1000


def documents(label: str) -> Iterator[tuple[str, Iterator[bytes]]]:
    """Each model the app ``label`` keeps fiscal documents in, as its config names them, by its label (``sale.sale``),
    with its rows."""
    config = django_apps.get_app_config(label)
    for name in config.fiscal_archive_models:
        model = config.get_model(name)
        yield model._meta.label_lower, rows(model)


def rows(model: type[Model]) -> Iterator[bytes]:
    """Every row of ``model``, one line of JSON each (with its ending), in the order the rows were made."""
    last = None
    while True:
        page = model._base_manager.order_by("pk")
        if last is not None:
            page = page.filter(pk__gt=last)
        found = list(page[:PAGE_ROWS])
        if not found:
            return
        yield from serializers.serialize("jsonl", found).encode().splitlines(keepends=True)
        last = found[-1].pk
