"""Names of the hubs' databases (PLAN-DB §3 and §14.12; plan 2026-10-22-fase-2-tenencia, step 1).

Every name derives from the control database's (``settings.DATABASES["default"]["NAME"]``: ``hub`` in prod,
``pre_hub`` in pre, the test database in the tests), so no pattern of one environment ever reaches another's:

- a hub: ``<control>_<hex>``, the whole ``Hub.id.hex`` (never truncated: the first half of a UUIDv7 is its date);
- a demo: ``demo_<hex>`` (round 2026-10-15d; PLAN-DB §14.12 flags that this one does not carry the control's
  prefix);
- a template: ``<control>_template`` or ``<control>_template_<vertical>``.

PostgreSQL silently truncates an identifier past 63 bytes, so a longer name is refused, never cut. A name reaches SQL
only through :func:`identifier` (``psycopg.sql.Identifier``, after :func:`validate`): never an f-string.
"""

import re
import uuid

from psycopg import sql

#: Longest identifier PostgreSQL keeps (``NAMEDATALEN - 1``).
MAX_IDENTIFIER = 63
#: Longest control database name its hubs' fit after: a hub's ``_<hex>`` is the most a name adds to control's.
MAX_CONTROL = MAX_IDENTIFIER - len("_") - 32
DEMO_PREFIX = "demo"
TEMPLATE_SUFFIX = "template"
#: The suffix of a hub's migrator alias (``<alias>__ddl``, PLAN-DB §4): the same database, reached directly.
DDL_SUFFIX = "__ddl"

_HEX = r"[0-9a-f]{32}"
_VERTICAL = r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*"
_VERTICAL_RE = re.compile(_VERTICAL)


class InvalidDatabaseName(ValueError):
    """A database name that is not a hub's, a demo's or a template's of this control database."""


def _patterns(control: str) -> re.Pattern:
    escaped = re.escape(control)
    return re.compile(
        rf"(?:{escaped}|{DEMO_PREFIX})_{_HEX}|{escaped}_{TEMPLATE_SUFFIX}(?:_{_VERTICAL})?"
    )


def validate(name: str, *, control: str) -> str:
    """``name`` if it is a hub's, a demo's or a template's database of ``control``; ``InvalidDatabaseName`` if not."""
    if not isinstance(name, str) or not _patterns(control).fullmatch(name):
        raise InvalidDatabaseName(f"{name!r} is no hub's, demo's or template's database of {control!r}.")
    if len(name.encode()) > MAX_IDENTIFIER:
        raise InvalidDatabaseName(
            f"{name!r} is longer than PostgreSQL's {MAX_IDENTIFIER} characters, which would truncate it."
        )
    return name


def hub_db_name(control: str, hub_id: uuid.UUID) -> str:
    """The database of the hub ``hub_id`` next to the control database ``control``."""
    return validate(f"{control}_{hub_id.hex}", control=control)


def demo_db_name(hub_id: uuid.UUID) -> str:
    """The database of the demo ``hub_id`` (``demo_<hex>``, any control database)."""
    name = f"{DEMO_PREFIX}_{hub_id.hex}"
    return validate(name, control=DEMO_PREFIX)


def template_db_name(control: str, vertical: str | None = None) -> str:
    """The template a hub of ``vertical`` is cloned from (``<control>_template[_<vertical>]``)."""
    if vertical is not None and not _VERTICAL_RE.fullmatch(vertical):
        raise InvalidDatabaseName(f"{vertical!r} is no vertical's name.")
    name = f"{control}_{TEMPLATE_SUFFIX}" + (f"_{vertical}" if vertical else "")
    return validate(name, control=control)


def identifier(name: str, *, control: str) -> sql.Identifier:
    """``name``, validated, as the only form it may take in SQL."""
    return sql.Identifier(validate(name, control=control))


def is_hub_alias(alias: str, *, control: str) -> bool:
    """Whether ``alias`` names a database of a hub, demo or template of ``control``, or its migrator's alias."""
    base = alias.removesuffix(DDL_SUFFIX)
    try:
        validate(base, control=control)
    except InvalidDatabaseName:
        return False
    return True
