"""The input schema of the History: one action of its closed list, one ticket and the business's days."""

import datetime as dt

from apps.kitchen.schemas.history import LogListIn

from .test_schemas_fields import refuses


def test_the_history_filters_by_one_known_action_and_the_business_days():
    data = LogListIn.model_validate({"action": "rushed", "date_from": "2026-11-01", "date_to": "2026-11-02"})
    assert (data.action, data.date_from, data.date_to) == ("rushed", dt.date(2026, 11, 1), dt.date(2026, 11, 2))
    assert refuses(LogListIn, action="exploded")
    assert refuses(LogListIn, ticket_id="Table 4")
