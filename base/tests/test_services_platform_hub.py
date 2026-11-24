"""ERPlora's own hub in the registry (``base.services.platform_hub``): its row, its name, and what nobody does to it."""

import pytest
from django.db import IntegrityError, transaction
from live.errors import Conflict

from base.models import Hub
from base.services import platform_hub
from base.tenancy.context import current, use_hub
from base.tenancy.tests.business import HUB_DB

pytestmark = HUB_DB


@pytest.fixture
def own(hub_b):
    Hub.objects.filter(pk=hub_b.pk).update(slug="erplora", is_platform=True)
    return Hub.objects.get(pk=hub_b.pk)


def test_its_rows_are_the_ones_that_say_so_whatever_their_name(own, hub_a):
    assert [row.pk for row in platform_hub.platform_rows()] == [own.pk]


def test_without_one_there_is_none(hub_a):
    Hub.objects.filter(pk=hub_a.pk).update(slug="erplora")
    assert platform_hub.platform_rows() == []


def test_renaming_it_changes_its_name_alone(own):
    before = Hub.objects.filter(pk=own.pk).values().get()

    renamed = platform_hub.platform_hub_renamed(own.pk, "erp")

    after = Hub.objects.filter(pk=own.pk).values().get()
    assert (renamed.pk, renamed.slug) == (own.pk, "erp")
    assert {**after, "updated_at": None} == {**before, "slug": "erp", "updated_at": None}


def test_its_database_opens_under_the_new_name_as_before(own):
    with use_hub(own):
        before = current().alias

    with use_hub(platform_hub.platform_hub_renamed(own.pk, "erp")):
        assert (current().alias, current().hub.slug) == (before, "erp")


def test_a_name_another_row_bears_is_never_taken(own, hub_a):
    Hub.objects.filter(pk=hub_a.pk).update(slug="erp")

    with pytest.raises(IntegrityError), transaction.atomic():
        platform_hub.platform_hub_renamed(own.pk, "erp")

    assert Hub.objects.get(pk=own.pk).slug == "erplora"


def test_a_business_is_never_renamed(hub_a):
    with pytest.raises(Hub.DoesNotExist):
        platform_hub.platform_hub_renamed(hub_a.pk, "erp")

    assert Hub.objects.get(pk=hub_a.pk).slug == hub_a.slug


def test_only_its_row_is_refused(own, hub_a):
    with pytest.raises(Conflict) as refused:
        platform_hub.refuse_platform_hub(own)
    assert (refused.value.code, refused.value.status) == ("base.platform_hub_kept", 409)
    platform_hub.refuse_platform_hub(hub_a)
