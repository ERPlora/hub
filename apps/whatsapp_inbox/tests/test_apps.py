"""The WhatsApp inbox declares its module metadata, its menu, its permissions and what each role gets."""

from django.apps import apps
from django.conf import settings
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role


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
}
NOT_FOR_API_KEYS = {
    # Personal data of the team, an irreversible erasure and the system's doors.
    "whatsapp_inbox.agent.list",
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
    assert len(ops) == 38
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
