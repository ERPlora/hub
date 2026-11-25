"""The business's tax region (TAX-F11)."""

import pytest
from live.errors import InvalidPayload, PermissionDenied
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.tax import events
from apps.tax.models import TaxSettings
from apps.tax.schemas.settings import TaxSettingsIn
from apps.tax.services.settings import update_settings

from base.tenancy.context import use_hub

from .conftest import HUB_DB, HUB_DB_COMMITTED, QUIET, A, B, outbox, received, refused, run

# tax.settings.update (TAX-F11): the business keeps its region


def keep(region, role="hub_admin", scope=A):
    return run("tax.settings.update", TaxSettingsIn(region_code=region), role, scope)


@HUB_DB
def test_keep_change_and_clear_the_business_region():
    assert get("tax.settings.update") is update_settings
    kept = keep("es-cn")
    # The tax of the territory comes back with it: the screen renames every tax at once (TAX-F11).
    assert (kept.country_code, kept.region_code, kept.tax_kind) == ("ES", "ES-CN", "igic")
    settings = TaxSettings.objects.get()
    assert (settings.region_code, settings.updated_by) == ("ES-CN", "tester")
    assert outbox() == [(events.SETTINGS_UPDATED, A.key, {"country_code": "ES", "region_code": "ES-CN"})]
    OutboxEvent.objects.all().delete()
    # The same region again changes nothing: no event re-prices the open tills.
    assert keep("ES-CN").region_code == "ES-CN" and outbox() == []
    assert keep("ES-ML").region_code == "ES-ML"
    cleared = keep(None)
    assert (cleared.region_code, cleared.tax_kind, TaxSettings.objects.get().region_code) == (None, "vat", "")
    assert outbox() == [
        (events.SETTINGS_UPDATED, A.key, {"country_code": "ES", "region_code": "ES-ML"}),
        (events.SETTINGS_UPDATED, A.key, {"country_code": "ES", "region_code": None}),
    ]


@HUB_DB
@pytest.mark.parametrize("region", ["PT-20", "ES-MD"])
def test_only_a_tax_territory_of_the_business_country_is_kept(region):
    # PT-20 is of another country; Madrid is Spain but charges the national VAT: no rule of its own.
    error = refused(InvalidPayload, lambda: keep(region))
    assert (error.status, error.code) == (422, "tax.region_not_available")
    assert error.fields == {"region_code": error.message}
    assert not TaxSettings.objects.exists() and outbox() == []


@HUB_DB
def test_only_who_manages_taxes_changes_the_region():
    refused(PermissionDenied, lambda: keep("ES-CN", role="hub_employee"))
    assert not TaxSettings.objects.exists() and outbox() == []


@HUB_DB_COMMITTED
def test_the_region_kept_on_b_notifies_the_channel_of_b_only(listen, hub_b):
    on_a, on_b = listen(A), listen(B)

    with use_hub(hub_b):
        keep("ES-CN", scope=B)
        assert [(name, scope) for name, scope, _ in outbox()] == [(events.SETTINGS_UPDATED, B.key)]

    assert received(on_b, stop_after=1) == [
        (channel_for(B), {"events": [events.SETTINGS_UPDATED]})
    ]
    assert received(on_a, timeout=QUIET) == []
