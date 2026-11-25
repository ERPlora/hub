"""Input schemas of what a price list, a price or a rule points at in another app, and of those apps' events."""

import uuid

from apps.pricing.schemas.catalog import CatalogEventIn


def test_an_event_payload_keeps_only_the_id():
    the_id = uuid.uuid7()
    assert CatalogEventIn.model_validate({"id": str(the_id), "sku": "S", "name": "N"}).id == the_id
