"""The flow app: automations — «when this happens, do that» — and the engine that runs them (WORKBOOK.md).

An automation starts on an event of another app, on a schedule, on a date or by hand, and runs its steps
in one column: other apps' actions and reads, by their operation's name (so it requires no app), a
condition that ends it quietly when not met, and waits.
"""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


class FlowConfig(LiveAppConfig):
    name = "apps.flow"
    label = "flow"
    kind = "app"
    verbose_name = _("Automations")
    # Registered in the shell (ION_ICONS); the old module's `git-branch` waits in UI-REQUESTS.md.
    icon = "ion:sync-outline"
    category = Category.ORGANIZATION
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Rules that run on their own: when something happens in your business, do something else."
    )
    description = _(
        "Automations runs the repetitive work for you: when a sale is charged, a customer is created or "
        "a till is closed, or every day at a time, it does what you told it, such as leaving a task or a "
        "note on a customer's card. Start from a ready-made card, allow it only what it needs, try it "
        "without effects against something that really happened, turn it on and read in plain words "
        "what it did each time. The assistant can draft one for you, and it waits for you to review it."
    )
    # A salon and a restaurant both automate their follow-ups and their opening and closing chores.
    verticals = ["hair_salon", "restaurant"]
    # Other apps' actions and reads are called by their operation's name, never by their models: an
    # automation that names an app that is off fails with its reason, visible in its history.
    requires = []
    default_auto_field = "django.db.models.BigAutoField"
    # The old module's two permissions (module.json), renamed <app>.<action>.
    permissions = ["flow.view", "flow.manage"]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). An automation acts
    # in the name of the business with nobody watching: only the owner and the admin (old module).
    role_permissions = {
        "hub_owner": ["flow.*"],
        "hub_admin": ["flow.*"],
        "hub_manager": [],
        "hub_employee": [],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with `icon =`
    # as the module's own icon.
    navigation = [
        Nav("automations", _("Automations"), "ion:sync-outline", "/flow/automations")
    ]
    # FLOW-F22 and FLOW-F23: the worker runs them every minute as the system (cron in UTC): phase 1 on
    # its one fixed scope, phase 2 on every hub.
    scheduled_tasks = [
        {
            "name": "fire_due",
            "operation": "flow.schedule.fire_due",
            "cron": "* * * * *",
            "catch_up": "collapse",
        },
        {
            "name": "resume_due",
            "operation": "flow.run.resume_due",
            "cron": "* * * * *",
            "catch_up": "collapse",
        },
    ]
