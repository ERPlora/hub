"""The factory automations online booking brings to Automatizaciones (WORKBOOK FLOW-F33 of ``apps/flow``).

Data only: Automatizaciones offers them in its gallery, under «Comes with Online booking», and turns one
on with exactly the permissions in ``grants``. Its steps name other apps' operations by name, as any
automation does; this app imports nothing of Automatizaciones.
"""

from django.utils.translation import gettext_lazy as _

RECIPES = [
    {
        "id": "booked_online",
        "name": _("Check each booking made online"),
        "summary": _("When a customer books online, leaves you a task to check the appointment."),
        "description": _("Every booking made on your booking page, whatever its state. The task names the appointment."),
        "trigger": {"kind": "event", "event": "online_booking.booking.created"},
        "steps": [
            {
                "id": "s1",
                "kind": "command",
                "operation": "task.task.create",
                "params": {"title": _("Check the online booking {{input.number}}"), "priority": "medium"},
            }
        ],
        "grants": {"task.task.create": _("Leaves you the task, so no online booking goes unseen.")},
    },
]
