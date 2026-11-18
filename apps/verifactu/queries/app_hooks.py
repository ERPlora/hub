"""What the platform asks VeriFactu through its app config (``apps.py``): whether the app may go on or off,
and what its fiscal records hold."""

import datetime as dt

from django.db.models import Min
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from psycopg import sql

from base import activation
from apps.verifactu.models import Environment, Record

from .country import ONLY_IN_SPAIN, outside_spain

#: This app's label: what ``base.activation`` names its state by.
VERIFACTU = "verifactu"
#: Why VeriFactu never goes off once on, in Spain (VERIFACTU-F32).
NEVER_OFF = _("VeriFactu can't be turned off once it's on: the law requires your invoices to keep reaching the AEAT.")


def enable_refusal(ctx: OperationContext) -> str | None:
    """VERIFACTU-F01: why the app may not go on, in ``ctx``'s language, or ``None``: outside Spain it would seal and send
    nothing (``outside_spain``), so it does not go on. One already on stays as it is, and goes off when asked.
    A business without a country (a demo) is in Spain."""
    if not outside_spain(ctx.scope):
        return None
    with translation.override(ctx.language):
        return str(ONLY_IN_SPAIN)


def disable_refusal(ctx: OperationContext) -> str | None:
    """VERIFACTU-F32: why the app may not go off, in ``ctx``'s language, or ``None``. In Spain, never once on: from
    then on the business's invoices reach the AEAT, VERI*FACTU binds it at least to the end of the natural year
    (RD 1007/2023, Orden HAC/1177/2024) and ERPlora keeps no other way of recording them, so whatever its queue holds
    the answer is the same. A business without a country (a demo) is in Spain.
    One that never got on (its tables being made, or making them failed: ``base.activation``) sealed nothing, so
    nothing binds it yet. Outside Spain no record is ever sent, so turning it off stops nothing: never refused (the
    records are kept). Both are read in the hub of the active context, inside ``base.app.disable``'s transaction."""
    if not activation.states_of(ctx.scope)[VERIFACTU].on or outside_spain(ctx.scope):
        return None
    with translation.override(ctx.language):
        return str(NEVER_OFF)


def oldest_unsent_at() -> dt.datetime | None:
    """Since when the oldest production record not in the AEAT yet (``Record.UNSENT``: pending, its retry
    waiting included, or sent without an answer) waits, or ``None``: the platform's ``OldestPendingAgeSeconds``, read
    in the database of the active context. A record of the AEAT's test environment files nothing, so it never counts;
    what the AEAT answered is out of the queue."""
    return Record.objects.filter(status__in=Record.UNSENT, environment=Environment.PRODUCTION).aggregate(
        oldest=Min("created_at")
    )["oldest"]


def keeps_fiscal_documents() -> bool:
    """Whether this database holds its records for the tax authority (``fiscal_documents_kept`` on this app's config), of any status: a draft counts
    too, for what it asks is whether a database can go, and that cannot be undone."""
    return Record.objects.exists()


def record_states(conn) -> dict:
    """What each production record says of its life at the AEAT (its status, when it was sent, when it last
    changed), by id, in the database of ``conn``; nothing where the app was never set up. ``conn`` is a direct
    connection (``fiscal_record_states`` on this app's config: the platform's restore reads the business's database and
    its copy, both closed to the app, and the copy has no alias), so it is read by its own SQL over the model's names,
    never the ORM. Only the AEAT's production counts: its test environment files nothing."""
    table = Record._meta.db_table
    if conn.execute("SELECT to_regclass(%s)", [table]).fetchone()[0] is None:
        return {}
    read, where = ("id", "status", "transmitted_at", "updated_at"), "environment"
    columns = {field: sql.Identifier(Record._meta.get_field(field).column) for field in (*read, where)}
    query = sql.SQL("SELECT {} FROM {} WHERE {} = %s").format(
        sql.SQL(", ").join(columns[field] for field in read), sql.Identifier(table), columns[where]
    )
    return {row[0]: tuple(row[1:]) for row in conn.execute(query, [Environment.PRODUCTION])}
