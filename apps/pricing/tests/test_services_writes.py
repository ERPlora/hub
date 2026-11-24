"""What the writes share: another app's row a write names that does not exist is refused under the field it came
from, and the write leaves nothing."""

import uuid

from live.errors import InvalidPayload

from apps.pricing.models import PriceList

from .conftest import HUB_DB
from .test_services import refused

pytestmark = HUB_DB


def test_a_group_that_does_not_exist_is_said_under_its_field():
    error = refused(InvalidPayload, "pricing.price_list.create", {"code": "X", "name": "X", "customer_group": "Nobody"})
    assert set(error.fields) == {"customer_group"}
    error = refused(InvalidPayload, "pricing.price_list.create", {"code": "X", "name": "X", "customer_group_id": str(uuid.uuid7())})
    assert set(error.fields) == {"customer_group_id"}
    assert not PriceList.objects.exists()
