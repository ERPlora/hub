"""Read operations of the staff app (``READ ONLY``), and the loaders services.py reuses.

A terminated record is the app's soft delete: no query returns it, nor its schedules or its time
off. «Today» is the business's day, on its clock (``reads.business_today``). A staff member may
be named by id or by name (the assistant speaks names): ``reads.resolve_member``.
"""

# Not alphabetical: the ones that register operations go first, in the order they register in.
from . import (
    members as members,
    commissions as commissions,
    accounts as accounts,
    roles as roles,
    schedules as schedules,
    availability as availability,
    time_off as time_off,
    settings as settings,
    reads as reads,
    time_off_reads as time_off_reads,
    records as records,
)
