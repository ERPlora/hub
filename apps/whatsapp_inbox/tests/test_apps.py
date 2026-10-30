"""The WhatsApp inbox declares its module metadata, its menu, its permissions and what each role gets."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.live_registry import live_registry
from live.meta import (
    BellCounter,
    Category,
    DeviceNotice,
    LiveAppConfig,
    Nav,
    module_configs,
    permissions_for_role,
)

from apps.whatsapp_inbox import events


def inbox():
    return apps.get_app_config("whatsapp_inbox")


def test_it_is_an_installed_live_app_that_requires_customers():
    config = inbox()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.whatsapp_inbox"
    assert config.label == "whatsapp_inbox"
    assert "apps.whatsapp_inbox" in settings.INSTALLED_APPS
    # A conversation is joined to its customer card by phone (WORKBOOK F04).
    assert config.requires == ["customer"]


def test_it_is_a_free_module_of_the_organization_group():
    config = inbox()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.ORGANIZATION
    assert config.premium is False
    # Registered in the shell (packages/ui shell/icons.ts); logo-whatsapp waits in UI-REQUESTS.md.
    assert config.icon == "ion:chatbubbles-outline"


def test_it_is_in_the_store_and_in_both_verticals():
    config = inbox()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == ["hair_salon", "restaurant"]
    assert config.listed is True


def test_permissions():
    assert inbox().permissions == [
        "whatsapp_inbox.view",
        "whatsapp_inbox.reply",
        "whatsapp_inbox.assign",
        "whatsapp_inbox.configure",
        "whatsapp_inbox.erase",
    ]


def test_the_system_permission_is_held_by_no_role():
    # Receiving, delivery statuses and the channel's state come from erplora.com through /internal:
    # only the system context (``*``) runs them, never a person, an API key or the assistant.
    config = inbox()
    assert "whatsapp_inbox.receive" not in config.permissions
    for role in ("hub_owner", "hub_admin", "hub_manager", "hub_employee"):
        assert "whatsapp_inbox.receive" not in permissions_for_role([config], role)


def test_roles():
    config = inbox()
    everything = set(config.permissions)
    assert permissions_for_role([config], "hub_owner") == everything
    assert permissions_for_role([config], "hub_admin") == everything
    assert permissions_for_role([config], "hub_manager") == {
        "whatsapp_inbox.view",
        "whatsapp_inbox.reply",
        "whatsapp_inbox.assign",
    }
    assert permissions_for_role([config], "hub_employee") == {
        "whatsapp_inbox.view",
        "whatsapp_inbox.reply",
    }


def test_navigation_is_the_inbox_and_the_settings_with_registered_icons():
    entries = inbox().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    # Every role sees both entries (a menu entry carries no permission); Settings answers «You do not
    # have permission» to whoever cannot configure (WORKBOOK «Estados de cada pantalla»).
    assert [
        (entry.id, str(entry.label), entry.path, entry.icon) for entry in entries
    ] == [
        ("inbox", "Inbox", "/whatsapp_inbox/inbox", "ion:chatbubbles-outline"),
        ("settings", "Settings", "/whatsapp_inbox/settings", "ion:settings-outline"),
    ]


HIGH_RISK = {
    "whatsapp_inbox.message.send",
    "whatsapp_inbox.message.retry",
    "whatsapp_inbox.conversation.set_status",
    "whatsapp_inbox.conversation.erase",
    "whatsapp_inbox.note.delete",
    "whatsapp_inbox.conversation.erase_for_customer",
    "whatsapp_inbox.template.create",
    "whatsapp_inbox.template.update",
    "whatsapp_inbox.template.delete",
    "whatsapp_inbox.channel.connect",
    "whatsapp_inbox.channel.disconnect",
}
NOT_FOR_API_KEYS = {
    # Personal data of the team, an irreversible erasure, the business's own number and the system's doors.
    "whatsapp_inbox.agent.list",
    "whatsapp_inbox.channel.prepare",
    "whatsapp_inbox.channel.connect",
    "whatsapp_inbox.channel.disconnect",
    "whatsapp_inbox.conversation.erase",
    "whatsapp_inbox.message.receive",
    "whatsapp_inbox.message.update_status",
    "whatsapp_inbox.channel.sync",
    "whatsapp_inbox.conversation.claim_for_customer",
    "whatsapp_inbox.conversation.move_customer",
    "whatsapp_inbox.conversation.erase_for_customer",
    "whatsapp_inbox.conversation.release_customer",
    "whatsapp_inbox.message.claim_delivery",
    "whatsapp_inbox.message.record_delivery",
    "whatsapp_inbox.conversation.claim_erasure",
    "whatsapp_inbox.conversation.record_erasure",
    "whatsapp_inbox.delivery.resume",
    "whatsapp_inbox.template.claim_submit",
    "whatsapp_inbox.template.record_submit",
    "whatsapp_inbox.template.claim_delete",
    "whatsapp_inbox.template.record_delete",
}


def test_every_operation_is_described_for_the_assistant_and_says_its_risk():
    # The assistant uses the app by voice and text with the user's own session: it sees every
    # operation; sending, closing and erasing are high risk (it asks before).
    from live.operations import registry

    ops = {name: op for name, op in registry.items() if name.startswith("whatsapp_inbox.")}
    # FLOW-F31 added message.notify, the narrow send an automation may be granted; WHATSAPP_INBOX-F09 the bell's
    # count and the device's notices; WHATSAPP_INBOX-F29 template_sample.upload, the file of a header; WHATSAPP_INBOX-F20
    # and F21 message.get and conversation.flag, what the automatic answers read and mark; template_sample.detail, the
    # read the assistant's card names a header's file by (FIX-HUB-WHATSAPP-INBOX-ATTEMPT-KEYS-UNMARKED).
    assert len(ops) == 48
    for name, op in ops.items():
        assert isinstance(op.ai, dict) and len(str(op.ai.get("description", ""))) > 20, name
        if op.kind == "command":
            assert op.ai.get("risk") == ("high" if name in HIGH_RISK else "normal"), name
        else:
            assert "risk" not in op.ai, name
        assert op.expose_api is (name not in NOT_FOR_API_KEYS), name


def test_the_worker_resumes_what_was_left_for_erplora():
    # Phase 2: the worker reaches every hub (hub_due) and claims, with SKIP LOCKED, the messages and
    # erasures whose delivery after the COMMIT never ended (WORKBOOK «Contrato con el SaaS»).
    assert inbox().scheduled_tasks == [
        {
            "name": "resume_deliveries",
            "operation": "whatsapp_inbox.delivery.resume",
            "cron": "*/5 * * * *",
            "catch_up": "collapse",
        }
    ]


# ── The Home's hooks (PLAN-HUB round 2026-10-21) and the device's notices (round 2026-10-23) ──────────────────

#: What changes whether a conversation waits for an answer (open, its last message the customer's, not erased): a
#: message arrives (the customer's, or the echo of one sent from the business's phone), one is sent from the Hub, its
#: status changes (open, pending, closed) or it is erased. Never a read, an assignment, a note nor a card joined.
AWAITING = [
    events.MESSAGE_RECEIVED,
    events.MESSAGE_SENT,
    events.STATUS_CHANGED,
    events.FLAGGED,
    events.ERASED,
]


def test_the_bell_counts_the_customers_waiting_for_an_answer():
    """WHATSAPP_INBOX-F09: the old module's counter of the bell (its module.json ``bell``, whatsapp_inbox#244,
    hub#1678), «WhatsApp customers waiting for an answer», on what the inbox calls waiting for an answer, leading
    to the inbox; whoever may read the inbox sees it."""
    [counter] = inbox().bell
    assert isinstance(counter, BellCounter)
    assert (
        counter.key,
        counter.operation,
        dict(counter.params),
        counter.route,
        str(counter.label),
        counter.icon,
        counter.permission,
    ) == (
        "awaiting_reply",
        "whatsapp_inbox.conversation.count_awaiting_reply",
        {},
        "/whatsapp_inbox/inbox",
        "WhatsApp customers waiting for an answer",
        "ion:chatbubbles-outline",
        "whatsapp_inbox.view",
    )
    assert list(counter.refresh_on) == AWAITING


def test_the_counter_says_the_old_words_in_spanish():
    with translation.override("es"):
        assert str(inbox().bell[0].label) == "Clientes de WhatsApp esperando respuesta"


def test_the_counters_events_re_run_its_query_and_its_icon_is_registered():
    counter = inbox().bell[0]
    assert live_registry.is_subscribable(counter.operation)
    assert set(counter.refresh_on) <= set(live_registry.subscribable[counter.operation])
    assert set(counter.refresh_on) <= set(events.ALL)
    icons = (Path(settings.BASE_DIR) / "packages/ui/src/shell/icons.ts").read_text()
    assert f"'{counter.icon.removeprefix('ion:')}'" in icons


def test_it_tells_the_device_of_each_customer_left_waiting():
    """hub#2303 (whatsapp_inbox#244): the installed app tells the device, with a system notice, of each message of a
    customer that is left waiting for an answer: «WhatsApp · {display_name}» with what the customer wrote; a tap opens that
    conversation in the inbox. Refreshed by a message arriving and by a conversation opened again."""
    [notice] = inbox().notices
    assert isinstance(notice, DeviceNotice)
    assert (notice.key, notice.operation, list(notice.when), dict(notice.params)) == (
        "awaiting_reply",
        "whatsapp_inbox.conversation.notices",
        [],
        {},
    )
    assert [str(text) for text in notice.title] == [
        "WhatsApp · {display_name}",
        "WhatsApp customer waiting for an answer",
    ]
    assert [str(text) for text in notice.body] == ["{last_message_preview}"]
    assert notice.route == "/whatsapp_inbox/inbox?conversation={id}"
    assert notice.permission == "whatsapp_inbox.view"
    assert list(notice.refresh_on) == [events.MESSAGE_RECEIVED, events.STATUS_CHANGED]
    assert live_registry.is_subscribable(notice.operation)
    assert set(notice.refresh_on) <= set(live_registry.subscribable[notice.operation])


def test_the_notice_falls_back_to_the_old_words_in_spanish():
    with translation.override("es"):
        assert str(inbox().notices[0].title[1]) == "Cliente de WhatsApp esperando respuesta"


def test_the_inbox_has_no_setup_steps_nor_panels():
    # The old module declared neither (its module.json has only `bell`).
    assert (inbox().setup, inbox().widgets) == ([], [])
