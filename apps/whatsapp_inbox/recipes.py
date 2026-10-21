"""The factory automations the WhatsApp inbox brings to Automatizaciones (WORKBOOK WHATSAPP_INBOX-F23; FLOW-F33 of
``apps/flow``).

Data only: Automatizaciones offers them under «Comes with WhatsApp inbox» and turns one on with exactly the
permissions in ``grants``. They write to a customer only through ``whatsapp_inbox.message.notify`` (FLOW-F31): the
live conversation of exactly the number on their card, text within their 24 hours and the approved template after them.
Each reason not to write ends the run at a step of its own (no phone, no conversation), never as an error.
"""

from django.utils.translation import gettext_lazy as _

#: The approved Utility template an appointment's notice goes with after the customer's 24 hours: the business
#: makes it in Settings (WHATSAPP_INBOX-F29) with four values, the day, the time, the service and the professional.
APPOINTMENT_TEMPLATE = "appointment_confirmed"

RECIPES = [
    {
        "id": "appointment_confirmed",
        "name": _("Tell the customer by WhatsApp when their appointment is confirmed"),
        "summary": _(
            "When an appointment is confirmed, the customer gets a WhatsApp with its day, time, service and "
            "professional."
        ),
        "description": _(
            "Only to a customer who already has a WhatsApp conversation with your business, and only to exactly "
            "the number on their card. Within 24 hours of their last message it goes as text; after them WhatsApp only "
            "lets an approved template through: create the Utility template «appointment_confirmed» in WhatsApp "
            "settings with four values (the day, the time, the service and the professional). Whenever it cannot "
            "go, the reason is in this automation's history."
        ),
        "trigger": {"kind": "event", "event": "appointment.appointment.confirmed"},
        "steps": [
            {"id": "s1", "kind": "query", "operation": "customer.customer.detail", "params": {"id": "input.customer_id"}},
            {"id": "s2", "kind": "condition", "when": {"steps.s1.phone": {"exists": True, "neq": ""}}},
            {
                "id": "s3",
                "kind": "query",
                "operation": "whatsapp_inbox.conversation.by_phone",
                "params": {"phone": "steps.s1.phone"},
            },
            {"id": "s4", "kind": "condition", "when": {"steps.s3.conversation_id": {"exists": True}}},
            {"id": "s5", "kind": "query", "operation": "appointment.appointment.get", "params": {"id": "input.id"}},
            {
                "id": "s6",
                "kind": "command",
                "operation": "whatsapp_inbox.message.notify",
                "params": {
                    "phone": "steps.s3.phone",
                    "text": _(
                        "Confirmed! We are expecting you on {{steps.s5.start_date_label}} at "
                        "{{steps.s5.start_time_label}} for your {{steps.s5.service_names}} with "
                        "{{steps.s5.staff_name}}."
                    ),
                    "template": {
                        "name": APPOINTMENT_TEMPLATE,
                        "variables": [
                            "{{steps.s5.start_date_label}}",
                            "{{steps.s5.start_time_label}}",
                            "{{steps.s5.service_names}}",
                            "{{steps.s5.staff_name}}",
                        ],
                    },
                },
            },
        ],
        "grants": {
            "customer.customer.detail": _("Reads the customer's card, for the number to write to."),
            "whatsapp_inbox.conversation.by_phone": _(
                "Checks that exactly that number has a WhatsApp conversation with your business."
            ),
            "appointment.appointment.get": _("Reads the appointment, for its day, time, service and professional."),
            "whatsapp_inbox.message.notify": _(
                "Sends the customer the WhatsApp, only in their own conversation and within your plan's messages."
            ),
        },
    },
]
