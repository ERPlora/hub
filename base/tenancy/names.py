"""Names of the hubs' databases (PLAN-DB §3 and §14.12; plan 2026-10-22-fase-2-tenencia, step 1).

Every name derives from the control database's (``settings.DATABASES["default"]["NAME"]``: ``hub`` in prod,
``pre_hub`` in pre, the test database in the tests), so no pattern of one environment ever reaches another's:

- a hub: ``<control>_<hex>``, the whole ``Hub.id.hex`` (never truncated: the first half of a UUIDv7 is its date);
- a demo: ``<control>_demo_<hex>`` (prod ``hub_demo_<hex>``, pre ``pre_hub_demo_<hex>``: round 2026-10-30 of
  PLAN-DB, proposal (e); before it a demo was ``demo_<hex>`` in every environment, and no such database was ever made);
- a template: ``<control>_template`` or ``<control>_template_<vertical>``;
- the copy a hub leaves behind on the server it moved from: ``<control>_move_<hex>`` (round 2026-10-30b of PLAN-DB,
  decision 3; ``base.tenancy.move``), as long as a demo's;
- the database a restore replaced, kept aside: ``<control>_old_<hex>`` (hub#1198; ``base.tenancy.restore``), the hex of
  a UUIDv7 of its own: the moment it was kept is in it (a date suffix would not fit in 63 characters after the longest
  control name), and two restores of a hub within the days keep both;
- a hub's database as it was at a moment, made aside while the business goes on: ``<control>_copy_<hex>`` (hub#1213;
  ``base.tenancy.restore``, «restore aside»), the hex of its ``control.RestoredCopy`` row (a UUIDv7). It is a copy left
  behind as the two above are: no process registers an alias of it, and it is only ever dropped.

PostgreSQL silently truncates an identifier past 63 bytes, so a longer name is refused, never cut. A name reaches SQL
only through :func:`identifier` (``psycopg.sql.Identifier``, after :func:`validate`): never an f-string.
"""

import re
import uuid

from psycopg import sql

#: Longest identifier PostgreSQL keeps (``NAMEDATALEN - 1``).
MAX_IDENTIFIER = 63
DEMO_INFIX = "demo"
MOVED_INFIX = "move"
KEPT_INFIX = "old"
COPY_INFIX = "copy"
#: Longest control database name its hubs' and demos' fit after: a demo's ``_demo_<hex>`` is the most a name adds.
MAX_CONTROL = MAX_IDENTIFIER - len(f"_{DEMO_INFIX}_") - 32
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
        rf"{escaped}(?:_{DEMO_INFIX}|_{MOVED_INFIX}|_{KEPT_INFIX}|_{COPY_INFIX})?_{_HEX}"
        rf"|{escaped}_{TEMPLATE_SUFFIX}(?:_{_VERTICAL})?"
    )


def validate(name: str, *, control: str) -> str:
    """``name`` if it is a hub's, a demo's, a template's, a moved copy's, a kept copy's or a copy aside's database of
    ``control``; ``InvalidDatabaseName`` if not."""
    if not isinstance(name, str) or not _patterns(control).fullmatch(name):
        raise InvalidDatabaseName(f"{name!r} is no hub's, demo's or template's database of {control!r}.")
    if len(name.encode()) > MAX_IDENTIFIER:
        raise InvalidDatabaseName(
            f"{name!r} is longer than PostgreSQL's {MAX_IDENTIFIER} characters, which would truncate it."
        )
    return name


def validate_hub(name: str, *, control: str) -> str:
    """``name`` if it is a hub's or a demo's database of ``control`` (never a template's); else ``InvalidDatabaseName``.

    What may be dropped (``base.tenancy.ops.drop_database``): a template is every hub's source, never one hub's.
    """
    validate(name, control=control)
    if not re.fullmatch(rf"{re.escape(control)}(?:_{DEMO_INFIX})?_{_HEX}", name):
        raise InvalidDatabaseName(f"{name!r} is a template of {control!r}, not a hub's or a demo's database.")
    return name


def is_moved(name: str, *, control: str) -> bool:
    """Whether ``name`` is the copy a hub of ``control`` left behind when it moved (never a hub's own database)."""
    return bool(re.fullmatch(rf"{re.escape(control)}_{MOVED_INFIX}_{_HEX}", name))


def validate_moved(name: str, *, control: str) -> str:
    """``name`` if it is the copy a hub left behind when it moved (``<control>_move_<hex>``); else
    ``InvalidDatabaseName``. What the move renames a hub's database to and drops after its days
    (``base.tenancy.move``)."""
    validate(name, control=control)
    if not is_moved(name, control=control):
        raise InvalidDatabaseName(f"{name!r} is no copy a hub of {control!r} left behind when it moved.")
    return name


def is_kept(name: str, *, control: str) -> bool:
    """Whether ``name`` is the database a restore of a hub of ``control`` replaced and kept aside."""
    return bool(re.fullmatch(rf"{re.escape(control)}_{KEPT_INFIX}_{_HEX}", name))


def is_copy_aside(name: str, *, control: str) -> bool:
    """Whether ``name`` is a database of a hub of ``control`` as it was at a moment, made aside (hub#1213)."""
    return bool(re.fullmatch(rf"{re.escape(control)}_{COPY_INFIX}_{_HEX}", name))


def validate_copy_aside(name: str, *, control: str) -> str:
    """``name`` if it is a separate copy of a hub (``<control>_copy_<hex>``, :func:`is_copy_aside`); else
    ``InvalidDatabaseName``. What the worker clones a template to when it makes one (``base.tenancy.ops``)."""
    validate(name, control=control)
    if not is_copy_aside(name, control=control):
        raise InvalidDatabaseName(f"{name!r} is no separate copy of a hub of {control!r}.")
    return name


def is_left_behind(name: str, *, control: str) -> bool:
    """Whether ``name`` is a copy a hub of ``control`` left behind, moved, restored or made aside: closed to the app,
    only dropped."""
    return is_moved(name, control=control) or is_kept(name, control=control) or is_copy_aside(name, control=control)


def validate_left_behind(name: str, *, control: str) -> str:
    """``name`` if it is a copy a hub left behind (:func:`is_left_behind`); else ``InvalidDatabaseName``. What the
    worker drops after its days (``base.tenancy.move``)."""
    validate(name, control=control)
    if not is_left_behind(name, control=control):
        raise InvalidDatabaseName(f"{name!r} is no copy a hub of {control!r} left behind.")
    return name


def hub_db_name(control: str, hub_id: uuid.UUID) -> str:
    """The database of the hub ``hub_id`` next to the control database ``control``."""
    return validate(f"{control}_{hub_id.hex}", control=control)


def demo_db_name(control: str, hub_id: uuid.UUID) -> str:
    """The database of the demo ``hub_id`` next to the control database ``control`` (``<control>_demo_<hex>``)."""
    return validate(f"{control}_{DEMO_INFIX}_{hub_id.hex}", control=control)


def moved_db_name(control: str, hub_id: uuid.UUID) -> str:
    """The copy the hub ``hub_id`` leaves behind on the server it moves from (``<control>_move_<hex>``)."""
    return validate(f"{control}_{MOVED_INFIX}_{hub_id.hex}", control=control)


def kept_db_name(control: str, kept_id: uuid.UUID) -> str:
    """The database a restore replaced, kept aside next to the control database ``control`` (``<control>_old_<hex>``,
    ``kept_id`` a UUIDv7 of its own)."""
    return validate(f"{control}_{KEPT_INFIX}_{kept_id.hex}", control=control)


def copy_db_name(control: str, copy_id: uuid.UUID) -> str:
    """A hub's database as it was at a moment, made aside next to the control database ``control``
    (``<control>_copy_<hex>``, ``copy_id`` its ``control.RestoredCopy`` row's)."""
    return validate(f"{control}_{COPY_INFIX}_{copy_id.hex}", control=control)


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
