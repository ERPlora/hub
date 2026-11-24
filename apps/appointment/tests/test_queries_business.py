"""The business's clock and settings as the rules read them."""

import datetime as dt

import pytest
from live.errors import InvalidPayload

from apps.appointment.queries.business import read_moment

from .conftest import HUB_DB

pytestmark = HUB_DB


def test_a_time_the_clock_change_skips_is_refused_on_the_field_it_came_in():
    with pytest.raises(InvalidPayload) as refused:
        read_moment(dt.datetime(2027, 3, 28, 2, 30), "start")
    assert (refused.value.code, list(refused.value.fields)) == ("appointment.invalid_local_time", ["start"])
