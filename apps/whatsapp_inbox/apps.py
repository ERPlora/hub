"""The WhatsApp inbox: the business's WhatsApp conversations, read and answered from the Hub (WORKBOOK.md).

The WhatsApp Business account, Meta's webhook and the approved templates live in the SaaS: messages
come in through ``/internal`` and go out through it (WORKBOOK «Contrato con el SaaS»).
"""

from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.meta import BellCounter, Category, DeviceNotice, LiveAppConfig, Nav

from apps.whatsapp_inbox.events import AWAITING_REPLY_EVENTS, NOTICE_EVENTS


class WhatsappInboxConfig(LiveAppConfig):
    name = "apps.whatsapp_inbox"
    label = "whatsapp_inbox"
    kind = "app"
    verbose_name = _("WhatsApp inbox")
    icon = "ion:chatbubbles-outline"
    category = Category.ORGANIZATION
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Your business's WhatsApp in the Hub: read, answer, assign and close every conversation."
    )
    description = _(
        "WhatsApp inbox brings your business's WhatsApp number into the Hub: every customer who "
        "writes has one conversation, joined to their customer card by phone. Your team reads and "
        "answers from any device, assigns each conversation, marks it open, pending or closed and "
        "leaves internal notes. After 24 hours without a message from the customer it offers your "
        "templates approved by Meta, and marketing ones only reach customers who gave their consent."
    )
    verticals = ["hair_salon", "restaurant"]
    requires = ["customer"]
    default_auto_field = "django.db.models.BigAutoField"
    # Not declared on purpose: ``whatsapp_inbox.receive``, which only the system context holds (the
    # doors erplora.com calls through /internal and the reactions to Customers).
    permissions = [
        "whatsapp_inbox.view",
        "whatsapp_inbox.reply",
        "whatsapp_inbox.assign",
        "whatsapp_inbox.configure",
        "whatsapp_inbox.erase",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included).
    role_permissions = {
        "hub_owner": ["whatsapp_inbox.*"],
        "hub_admin": ["whatsapp_inbox.*"],
        "hub_manager": [
            "whatsapp_inbox.view",
            "whatsapp_inbox.reply",
            "whatsapp_inbox.assign",
        ],
        "hub_employee": ["whatsapp_inbox.view", "whatsapp_inbox.reply"],
    }
    # Phase 2: the worker reaches every hub (hub_due) and hands erplora.com again, with SKIP LOCKED,
    # the messages and erasures whose delivery after the COMMIT never ended (cron in UTC).
    scheduled_tasks = [
        {
            "name": "resume_deliveries",
            "operation": "whatsapp_inbox.delivery.resume",
            "cron": "*/5 * * * *",
            "catch_up": "collapse",
        }
    ]
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. Registered icons only (UI-REQUESTS.md asks for logo-whatsapp).
    navigation = [
        Nav("inbox", pgettext_lazy("whatsapp menu", "Inbox"), "ion:chatbubbles-outline", "/whatsapp_inbox/inbox"),
        Nav(
            "settings",
            pgettext_lazy("whatsapp menu", "Settings"),
            "ion:settings-outline",
            "/whatsapp_inbox/settings",
        ),
    ]
    # The Home's hooks (PLAN-HUB round 2026-10-21; WHATSAPP_INBOX-F09): the old module's counter of the bell
    # (``whatsapp_inbox.needs_attention``, whatsapp_inbox#244), here the customers waiting for an answer the inbox's
    # summary counts, leading to the inbox. No steps of «Finish setting up your business» nor panels of the dashboard:
    # the old module had none.
    bell = [
        BellCounter(
            key="awaiting_reply",
            operation="whatsapp_inbox.conversation.count_awaiting_reply",
            route="/whatsapp_inbox/inbox",
            label=_("WhatsApp customers waiting for an answer"),
            icon="ion:chatbubbles-outline",
            permission="whatsapp_inbox.view",
            refresh_on=AWAITING_REPLY_EVENTS,
        )
    ]
    # hub#2303 (round 2026-10-23): the installed app tells the device of each message of a customer left waiting for
    # an answer, with who and what she wrote; a tap opens that conversation in the inbox.
    notices = [
        DeviceNotice(
            key="awaiting_reply",
            operation="whatsapp_inbox.conversation.notices",
            title=[_("WhatsApp · {name}"), _("WhatsApp customer waiting for an answer")],
            body=["{preview}"],
            route="/whatsapp_inbox/inbox?conversation={id}",
            permission="whatsapp_inbox.view",
            refresh_on=NOTICE_EVENTS,
        )
    ]
