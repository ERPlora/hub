"""Input and output schemas of the staff app's operations (OpenAPI, live params, 422 per field, and the
assistant's tools: every input field carries a ``description``).

Cross-field rules are field validators on the later field (``info.data`` holds the earlier ones), so
a 422 names the field to fix. Their messages are raised as text in the active language: the
request's, through ``LocaleMiddleware``. A staff member can be named by id or by name, because the
assistant speaks names; ``queries.resolve_member`` turns the name into the record.
"""

from . import (
    accounts as accounts,
    availability as availability,
    commissions as commissions,
    fields as fields,
    members as members,
    roles as roles,
    schedules as schedules,
    settings as settings,
    time_off as time_off,
)
