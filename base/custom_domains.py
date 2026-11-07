"""Which business a host outside ``ALLOWED_HOSTS`` belongs to (HUBS-F17, PLAN-SAAS §37 point 2), at no read per request.

The SaaS names a business's own domain in its photo (``custom_domain``, ``base.hub.state_apply``), and that is the only
way the Hub learns it: it is kept on the business's row and never asked of the SaaS. The ALB's last rule sends the Hub
every host nobody else claims, the scanners that its 404 used to stop included, so «whose is this host?» cannot cost a
read per request: each process keeps the answer in memory and reads it again every :data:`REFRESH_SECONDS`, whoever asks
meanwhile, one read at most per process. The process that applied a photo that changes a domain reads it again at once
(:func:`forget`); the others take up to that time, which the SaaS's probe has to allow for.

A domain two businesses name (its move between them: two photos, and their versions say nothing of each other's order)
is nobody's until the one that gave it up says so: the Hub never chooses a website for it and refuses neither photo,
so it is logged and left out. A business that left is left out too. A failed read keeps what was known and is tried
again after :data:`RETRY_SECONDS`, so a failover neither closes the domains nor piles reads on the database.

What the door does with the answer is ``base.middleware.CustomDomainMiddleware``'s. The map says whose a domain was at
its last read: before a page is served, the business's row is read again (``base.tenancy.connections`` needs it fresh,
a move changes where its database is), and it has to name the domain still.
"""

import logging
import threading
import uuid
from time import monotonic

from django.db import DatabaseError

from base import registry

logger = logging.getLogger(__name__)

#: How long a process trusts its map: what a domain given up in another process may take to be unknown here.
REFRESH_SECONDS = 30.0
#: How soon a read that failed is tried again.
RETRY_SECONDS = 5.0

_known: dict[str, uuid.UUID] = {}
_next_read = 0.0
_lock = threading.Lock()


def hub_of(domain: str) -> uuid.UUID | None:
    """The id of the business ``domain`` (lowercase, no port) belongs to, or ``None``; reads only when the map is due."""
    if monotonic() >= _next_read:
        _read_if_nobody_is()
    return _known.get(domain)


def served_on(hub) -> str:
    """The own domain the door opens ``hub``'s website on now, or ``""``: the one its row names, while the map gives
    it to ``hub`` (a domain two businesses name is nobody's). What its page names as its main address (hub#818)."""
    domain = hub.custom_domain
    return domain if domain and hub_of(domain) == hub.id else ""


def forget() -> None:
    """The next question reads the map again, in this process."""
    global _next_read
    _next_read = 0.0


def _read_if_nobody_is() -> None:
    """Read the map again, unless another thread is at it: meanwhile, what was known answers."""
    global _known, _next_read
    if not _lock.acquire(blocking=False):
        return
    try:
        try:
            rows = registry.custom_domains()
        except DatabaseError as error:
            logger.warning("base.custom_domains_unread: keeping what was known (%s).", error)
            _next_read = monotonic() + RETRY_SECONDS
            return
        _known = _one_business_each(rows)
        _next_read = monotonic() + REFRESH_SECONDS
    finally:
        _lock.release()


def _one_business_each(rows: list[tuple[str, uuid.UUID]]) -> dict[str, uuid.UUID]:
    """``rows`` as a map, without the domains more than one business names."""
    known: dict[str, uuid.UUID] = {}
    taken: set[str] = set()
    for domain, hub_id in rows:
        if domain in known:
            taken.add(domain)
        known[domain] = hub_id
    for domain in taken:
        logger.error("base.custom_domain_taken: %s is named by more than one business; it is not served.", domain)
        del known[domain]
    return known
