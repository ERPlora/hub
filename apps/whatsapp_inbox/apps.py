"""The WhatsApp inbox: the business's WhatsApp conversations, read and answered from the Hub (WORKBOOK.md).

The WhatsApp Business account, Meta's webhook and the approved templates live in the SaaS: messages
come in through ``/internal`` and go out through it (WORKBOOK «Contrato con el SaaS»).
"""

from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext_lazy, pgettext_lazy
from live.meta import BellCounter, Category, DeviceNotice, Help, LiveAppConfig, Nav

from apps.whatsapp_inbox.events import AWAITING_REPLY_EVENTS, NOTICE_EVENTS


class WhatsappInboxConfig(LiveAppConfig):
    name = "apps.whatsapp_inbox"
    label = "whatsapp_inbox"
    blueprint_stays = {
        "Channel": "outside",
        "Conversation": "history",
        "Message": "history",
        "Note": "history",
        "TemplateSample": "outside",
        "Template": "outside",
    }
    kind = "app"
    verbose_name = _("WhatsApp inbox")
    icon = "ion:chatbubbles-outline"
    category = Category.ORGANIZATION
    premium = False
    # The public store's texts, which register_apps writes to shared.app.
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
    # What these words mean to the Hub's assistant (base.assistant.relevance.synonyms). A «plantilla» and a «mensaje» are the
    # inbox's template and message (whatsapp_inbox.template, whatsapp_inbox.message), as «template» and «message»
    # already are in English; a business template (base.blueprint) or the staff a «plantilla» also names are said with
    # their own words beside it («plantilla de negocio», «el personal»).
    assistant_synonyms = (
        ("plantilla", "plantillas", "template", "templates"),
        ("mensaje", "mensajes", "message", "messages"),
    )
    # Not declared on purpose: ``whatsapp_inbox.receive``, which only the system context holds (the
    # doors erplora.com calls through /internal and the reactions to Customers).
    permissions = {
        "whatsapp_inbox.view": _("Read conversations"),
        "whatsapp_inbox.reply": _("Reply, add notes and take a free conversation"),
        "whatsapp_inbox.assign": _("Assign conversations to others and take them from others"),
        "whatsapp_inbox.configure": _("Connect the number and manage the templates and settings"),
        "whatsapp_inbox.erase": _("Erase a number's data"),
    }
    # The files of the templates' headers (samples.py), which the template's sheet shows to the hub's people only
    # (base.media serves them at /p/media/ to a session of this hub; a visitor gets a 404).
    members_media = ["whatsapp_inbox/samples/"]
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
    # The worker reaches every hub (hub_due) and hands erplora.com again, with SKIP LOCKED, the messages and erasures
    # whose delivery after the COMMIT never ended (cron in UTC).
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
        Nav(
            "inbox", pgettext_lazy("whatsapp menu", "Inbox"), "ion:chatbubbles-outline", "/whatsapp_inbox/inbox",
            permission="whatsapp_inbox.view",
        ),
        Nav(
            "settings",
            pgettext_lazy("whatsapp menu", "Settings"),
            "ion:settings-outline",
            "/whatsapp_inbox/settings",
            permission="whatsapp_inbox.configure",
        ),
    ]
    # The bell counts the customers waiting for an answer the inbox's summary counts, leading to the inbox
    # (WHATSAPP_INBOX-F09).
    bell = [
        BellCounter(
            key="awaiting_reply",
            operation="whatsapp_inbox.conversation.count_awaiting_reply",
            route="/whatsapp_inbox/inbox",
            label=_("WhatsApp customers waiting for an answer"),
            icon="ion:chatbubbles-outline",
            permission="whatsapp_inbox.view",
            refresh_on=AWAITING_REPLY_EVENTS,
            severity="warning",
            title=ngettext_lazy(
                "%(count)d WhatsApp customer waiting for an answer",
                "%(count)d WhatsApp customers waiting for an answer",
                "count",
            ),
            body=_("Answer within 24 hours of their last message: after that, WhatsApp only lets you send an approved template."),
            action_label=_("Answer the customers"),
        )
    ]
    # What the plan includes and the month has spent, for System › «Usage and plan» and the bell (BASE-F40): base reads no
    # other app's tables. No figure until erplora.com sent the channel's (its 0 would say the plan includes none).
    plan_meter = {
        "operation": "whatsapp_inbox.channel.get",
        "used": "monthly_usage",
        "limit": "monthly_limit",
        "measured": "synced_at",
        "label": _("WhatsApp"),
    }
    # The Home's health row, for who runs the business (base.E021 checks it at start): whether the number is connected.
    health = {
        "operation": "whatsapp_inbox.channel.health",
        "permission": "whatsapp_inbox.configure",
        "route": "/whatsapp_inbox/settings",
        "action": _("Connect WhatsApp"),
        "titles": {
            "ok": _("WhatsApp connected"),
            "no_signal": _("WhatsApp needs reconnecting"),
            "not_configured": _("WhatsApp not connected"),
            "unknown": _("We couldn't check WhatsApp"),
        },
    }
    # The installed app tells the device of each message of a customer left waiting for an answer, with who and what she
    # wrote; a tap opens that conversation in the inbox.
    notices = [
        DeviceNotice(
            key="awaiting_reply",
            operation="whatsapp_inbox.conversation.notices",
            title=[_("WhatsApp · {display_name}"), _("WhatsApp customer waiting for an answer")],
            body=["{last_message_preview}"],
            route="/whatsapp_inbox/inbox?conversation={id}",
            permission="whatsapp_inbox.view",
            refresh_on=NOTICE_EVENTS,
        )
    ]
    help = Help(
        flow_videos={
            "WHATSAPP_INBOX-F16": {"es": ["bdZh9fc-kM8"], "en": ["mEqjI-FsgX8"]},
        },
    )
