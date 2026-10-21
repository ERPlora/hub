"""The factory automations Citas brings to Automatizaciones (WORKBOOK FLOW-F33 of ``apps/flow``).

Data only: Automatizaciones offers them in its gallery, under «Comes with Appointments», and turns one on
with exactly the permissions in ``grants``. Its steps name other apps' operations by name, as any
automation does; this app imports nothing of Automatizaciones.
"""

from django.utils.translation import gettext_lazy as _

RECIPES = [
    {
        "id": "customer_cancelled",
        "name": _("Fill the gap when a customer cancels"),
        "summary": _("When a customer cancels their appointment, leaves you a task to fill the gap."),
        "description": _(
            "Only the cancellations the customer asks for: the ones your team makes do not start it. "
            "The task is high priority and names the appointment."
        ),
        "trigger": {
            "kind": "event",
            "event": "appointment.appointment.cancelled",
            "filter": {"input.by_customer": {"eq": True}},
        },
        "steps": [
            {
                "id": "s1",
                "kind": "command",
                "operation": "task.task.create",
                "params": {"title": _("Fill the gap of appointment {{input.number}}"), "priority": "high"},
            }
        ],
        "grants": {"task.task.create": _("Leaves you the task, so you remember to offer the free time.")},
    },
]
