"""How the hub finds a piece of text in a column: ignoring case and accents, so «cafe» finds «Café con leche».

PostgreSQL's ``unaccent``, which a migration of ``base`` installs in every hub's database, strips the accents of both
the column and the term, as stores, tills and search engines do.
"""

from functools import reduce
from operator import or_

from django.contrib.postgres.lookups import Unaccent
from django.db.models import F, Q, TextField, Value
from django.db.models.functions import Cast
from django.db.models.lookups import IContains


def contains_text(term: str, *fields: str) -> Q:
    """The rows where any of ``fields`` contains ``term``, ignoring case and accents.

    A field is a column or a path through relations (``"product__name"``); one that is not text (a number, an id) is
    searched as its text. ``%`` and ``_`` in the term are searched as themselves.
    """
    wanted = Unaccent(Value(term))
    return reduce(or_, (Q(IContains(Unaccent(Cast(F(field), TextField())), wanted)) for field in fields))
