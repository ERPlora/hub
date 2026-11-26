"""The WhatsApp channel's model: its key, its defaults, one row per database and the plan's monthly cap."""

from apps.whatsapp_inbox.models.channel import Channel
from apps.whatsapp_inbox.tests.conftest import HUB_DB, NOW, violates

pytestmark = HUB_DB


def test_keys_are_uuid7():
    channel = Channel.objects.create()
    assert channel.pk.version == 7


def test_defaults():
    channel = Channel.objects.create()
    assert (
        channel.status,
        channel.monthly_limit,
        channel.monthly_usage,
        channel.version,
    ) == (
        "not_connected",
        0,
        0,
        0,
    )


def test_one_channel_row_per_database():
    Channel.objects.create()
    assert violates("whatsapp_inbox_channel_one_per_host", Channel.objects.create)


def test_the_cap_is_the_platform_s_figure_of_this_month():
    channel = Channel(monthly_limit=150, monthly_usage=150, usage_month="2026-10", synced_at=NOW)
    assert channel.cap_reached("2026-10") is True
    # Another month's figure counts as nothing spent: November starts again even before the SaaS speaks.
    assert channel.cap_reached("2026-11") is False
    channel.monthly_usage = 149
    assert channel.cap_reached("2026-10") is False
    # 0 = the plan includes none, never «no cap»: tests/test_plan_cap.py.
    assert (
        Channel(monthly_limit=0, monthly_usage=0, usage_month="2026-10", synced_at=NOW).cap_reached(
            "2026-10"
        )
        is True
    )
