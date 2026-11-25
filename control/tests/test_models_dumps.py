"""The copies of a hub's database kept in the dumps bucket."""

import pytest
from django.db import IntegrityError, transaction

from control.models.hubs import Hub

pytestmark = pytest.mark.django_db


def test_a_dump_is_kept_by_its_key_newest_first():
    from control.models.dumps import HubDump

    hub = Hub.objects.create(slug="acme", db_name="hub_test_dump")
    older = HubDump.objects.create(
        hub=hub, kind=HubDump.Kind.RESET, key="k/20261030T100000Z-reset.dump", bytes=10, created_at="2026-10-30T10:00Z"
    )
    newer = HubDump.objects.create(
        hub=hub,
        kind=HubDump.Kind.OFFBOARDING,
        key="k/20261031T100000Z-offboarding.dump",
        bytes=0,
        created_at="2026-10-31T10:00Z",
        requested_by="Olga",
    )

    assert list(hub.dumps.all()) == [newer, older]
    assert newer.id.version == 7
    with pytest.raises(IntegrityError), transaction.atomic():
        HubDump.objects.create(hub=hub, kind="reset", key=older.key, bytes=1, created_at="2026-10-31T11:00Z")


def test_the_copies_and_the_use_are_in_spanish():
    from django.utils import translation

    from control.models.dumps import HubDump
    from control.models.usage import HubUsageDaily, HubVisit, UsageRun

    with translation.override("es"):
        assert str(HubDump._meta.verbose_name_plural) == "copias de los datos"
        assert [str(label) for label in HubDump.Kind.labels] == ["Antes de restablecer", "Al darse de baja"]
        assert str(HubDump._meta.get_field("bytes").verbose_name) == "tamaño (bytes)"
        assert str(HubDump._meta.get_field("requested_by").verbose_name) == "pedida por"
        assert str(HubUsageDaily._meta.verbose_name_plural) == "uso diario de los hubs"
        assert str(HubVisit._meta.verbose_name_plural) == "entradas diarias"
        assert str(UsageRun._meta.verbose_name_plural) == "mediciones nocturnas"
        assert str(Hub._meta.get_field("reset_requested_at").verbose_name) == "restablecimiento pedido"
        assert str(Hub._meta.get_field("reset_sections").verbose_name) == "restablecimiento"
