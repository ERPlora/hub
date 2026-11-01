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
        "Rules that run on their own when something happens, on a schedule or by hand: repetitive work, done for you."
    )
    # The store's card says what it does today: it starts when something happens in the business (FLOW-F21), at a
    # time, on a date or by hand, and the assistant drafts one when asked (FLOW-F17).
    description = _(
        "Automations runs the repetitive work for you: when something happens in your business, every day, week or "
        "month at a time, on a date, or when you run it, it does what you told it, such as leaving a task or a note "
        "on a customer's card. Start from a ready-made card or ask the assistant to draft one, allow it only what it "
        "needs, try it without effects, turn it on and read in plain words what it did each time."
    )
    # A salon and a restaurant both automate their follow-ups and their opening and closing chores.
    verticals = ["hair_salon", "restaurant"]
    # Other apps' actions and reads are called by their operation's name, never by their models: an
    # automation that names an app that is off fails with its reason, visible in its history.
    requires = []
    default_auto_field = "django.db.models.BigAutoField"
    # The old module's two permissions (module.json), renamed <app>.<action>, and answering what an
    # automation asks (FLOW-F29): what is asked of employees, and what is asked of managers.
    permissions = ["flow.view", "flow.manage", "flow.answer", "flow.answer_manager"]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). An automation acts
    # in the name of the business with nobody watching: only the owner and the admin (old module) see,
    # change or run them; a manager and an employee only answer the questions asked of their role.
    role_permissions = {
        "hub_owner": ["flow.*"],
        "hub_admin": ["flow.*"],
        "hub_manager": ["flow.answer", "flow.answer_manager"],
        "hub_employee": ["flow.answer"],
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
        # FLOW-F16: the history forgets the finished runs older than 90 days, once an hour.
        {
            "name": "prune",
            "operation": "flow.run.prune",
            "cron": "17 * * * *",
            "catch_up": "collapse",
        },
        # FLOW-F30: the questions nobody answered in time, every minute.
        {
            "name": "expire_questions",
            "operation": "flow.question.expire_due",
            "cron": "* * * * *",
            "catch_up": "collapse",
        },
    ]
