"""A ticket of a round points at its check of Sales by ``order_id`` and each dish at its line by ``sale_line_id``:
opaque references, no foreign key between apps (like Tables). The id of a round's ticket is the id of its first line,
and the id of each dish the id of its line (UUIDv7 that Sales made; each dish of a menu, one derived from it:
``queries.rounds.dish_id``): a round the kitchen has not saved yet and the saved one share their ids. What was sent stays as it
was sent: the station, its destination and its printer, the options chosen and the menu's header are frozen on each
dish. Stations and tickets are deleted logically.

A label an app loaded before this one says in English too, but in Spanish with other words, goes through
``pgettext_lazy`` with the ``kitchen`` context (``kitchen station`` where a station's word is not a ticket's), so
Spanish says the kitchen's word, not that app's (hub#659).

One module per responsibility, each imported here so that Django registers its models, in this order.
"""

from . import (
    fields as fields,
    stations as stations,
    routing as routing,
    settings as settings,
    numbering as numbering,
    tickets as tickets,
    history as history,
)
