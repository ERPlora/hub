"""The business's number as erplora.com syncs it (WHATSAPP_INBOX-F13, F27, F28): its status, its version, its month
and its templates, each business in its own database.
"""

from apps.whatsapp_inbox.models.channel import Channel
from apps.whatsapp_inbox.models.templates import Template
from apps.whatsapp_inbox.tests.conftest import HUB_DB, NOW, connect, ctx_for, events, receive, run, system, template
from base.tenancy.context import use_hub

pytestmark = HUB_DB


# ── WHATSAPP_INBOX-F13, F27, F28 The channel and its templates ─────────────────────────────────


def test_the_channel_follows_erplora_s_newest_version():
    assert connect(version=2).applied is True
    channel = Channel.objects.get()
    assert (
        channel.status,
        channel.phone_number,
        channel.monthly_limit,
        channel.monthly_usage,
        channel.version,
    ) == (
        "connected",
        "+34910000000",
        150,
        10,
        2,
    )
    assert channel.synced_at == NOW
    stale = connect(version=2, status="reconnect_needed")
    assert stale.model_dump() == {"applied": False, "version": 2}
    assert connect(version=1, status="not_connected").applied is False
    assert Channel.objects.get().status == "connected"
    assert connect(version=3, status="reconnect_needed").applied is True
    assert Channel.objects.get().status == "reconnect_needed"
    assert len(events("whatsapp_inbox.channel.synced")) == 2


def channel_of(scope):
    return run("whatsapp_inbox.channel.get", {}, ctx_for(scope=scope))


@HUB_DB
def test_each_business_keeps_its_own_number_and_its_own_version(hub_a, hub_b):
    from live.context import Scope

    with use_hub(hub_a):
        assert system("whatsapp_inbox.channel.sync", {"version": 50, "status": "connected", "phone_number": "+34910000000", "monthly_limit": 150}, Scope("host", hub_a.slug)).applied is True
        assert system("whatsapp_inbox.channel.sync", {"version": 60, "status": "reconnect_needed", "phone_number": "+34910000000", "monthly_limit": 150}, Scope("host", hub_a.slug)).applied is True
    with use_hub(hub_b):
        b = {"version": 120, "status": "not_connected", "phone_number": "", "display_name": ""}
        assert system("whatsapp_inbox.channel.sync", b, Scope("host", hub_b.slug)).applied is True
        assert system("whatsapp_inbox.channel.sync", {**b, "version": 110}, Scope("host", hub_b.slug)).applied is False
        assert Channel.objects.get().version == 120

    with use_hub(hub_a):
        a_now = channel_of(Scope("host", hub_a.slug))
        assert (a_now.status, a_now.phone_number, a_now.monthly_limit) == ("reconnect_needed", "+34910000000", 150)
    with use_hub(hub_b):
        b_now = channel_of(Scope("host", hub_b.slug))
        assert (b_now.status, b_now.phone_number, b_now.monthly_limit) == ("not_connected", "", 0)


@HUB_DB
def test_only_the_business_with_its_number_connected_may_send_and_its_month_is_its_own(hub_a, hub_b):
    from live.context import Scope

    with use_hub(hub_a):
        system(
            "whatsapp_inbox.channel.sync",
            {"version": 1, "status": "connected", "phone_number": "+34910000000", "monthly_limit": 150, "monthly_usage": 150, "usage_month": "2026-10"},
            Scope("host", hub_a.slug),
        )
        conversation = receive("wamid.1", "34600111222", scope=Scope("host", hub_a.slug))
        ref = {"id": str(conversation.conversation_id)}
        a = run("whatsapp_inbox.conversation.detail", ref, ctx_for(scope=Scope("host", hub_a.slug)))
        a_month = run("whatsapp_inbox.conversation.summary", {}, ctx_for(scope=Scope("host", hub_a.slug)))
    with use_hub(hub_b):
        other = receive("wamid.2", "34600222111", scope=Scope("host", hub_b.slug))
        b = run(
            "whatsapp_inbox.conversation.detail",
            {"id": str(other.conversation_id)},
            ctx_for(scope=Scope("host", hub_b.slug)),
        )
        b_month = run("whatsapp_inbox.conversation.summary", {}, ctx_for(scope=Scope("host", hub_b.slug)))
    assert (a.send_blocked, b.send_blocked) == ("cap_reached", "not_connected")
    assert (a_month.cap_reached, b_month.cap_reached) == (True, False)


@HUB_DB
def test_each_business_s_photo_keeps_its_own_number(client, settings, hub_a, hub_b):
    from base.tests.test_internal import SECRET, signed

    settings.INTERNAL_SHARED_SECRET, settings.INTERNAL_SHARED_SECRET_PREVIOUS = SECRET, ""
    a_id, b_id = str(hub_a.id), str(hub_b.id)
    block = {"status": "connected", "phone_number": "+34910000000", "display_name": "Ana", "version": 1}

    def photo(hub_id, slug, version, **whatsapp):
        body = {"hub_id": hub_id, "slug": slug, "version": version, "status": "active", "whatsapp": {**block, **whatsapp}}
        return signed(client, "put", f"/internal/hubs/{hub_id}/state", body)

    assert photo(a_id, "a", 50).json() == {"applied": True, "version": 50}
    assert photo(b_id, "b", 120, status="not_connected", phone_number="", display_name="").json()["applied"] is True

    from live.context import Scope

    with use_hub(hub_a):
        assert (channel_of(Scope("host", hub_a.slug)).status, channel_of(Scope("host", hub_a.slug)).phone_number) == ("connected", "+34910000000")
    with use_hub(hub_b):
        assert (channel_of(Scope("host", hub_b.slug)).status, channel_of(Scope("host", hub_b.slug)).phone_number) == ("not_connected", "")


def test_templates_are_replaced_by_the_list_and_the_missing_ones_stay_deleted():
    connect(
        version=1,
        templates=[template("recordatorio"), template("promo", category="MARKETING")],
    )
    assert set(Template.objects.values_list("name", "status")) == {
        ("recordatorio", "APPROVED"),
        ("promo", "APPROVED"),
    }
    connect(version=2, templates=[template("recordatorio", status="PAUSED")])
    assert dict(Template.objects.values_list("name", "status")) == {
        "recordatorio": "PAUSED",
        "promo": "DELETED",
    }
    connect(version=3, templates=None)  # null leaves them as they are
    assert Template.objects.count() == 2
    rejected = template("nuevo", status="REJECTED", rejected_reason="INVALID_FORMAT")
    connect(version=4, templates=[rejected])
    assert Template.objects.get(name="nuevo").rejected_reason == "INVALID_FORMAT"
