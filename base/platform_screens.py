"""The Hub's own screens, as its help serves them (``base.help.get``): each one is a section of base's WORKBOOK. And what
a person holds to get a task done on them, from who does it there."""

from collections.abc import Collection

from django.utils.translation import pgettext_lazy

from base.permissions import ADMINISTER_HUB, OPEN_MANAGEMENT, OWN_BUSINESS, VIEW_HOME
from base.workbook_help import Tab

#: How the help of these screens is named: base's own name means nothing to whoever uses the Hub.
NAME = "ERPlora"

#: A page with tabs has a screen per tab. Its label is the title of its section; its path, its route in the SPA's router
#: (``frontend/routes.ts``, the parameters unread) with the hash of its tab; its permission, the one its page asks. In
#: the order of the side menu.
SCREENS = (
    Tab("home", pgettext_lazy("workbook", "Home · Summary"), "/", VIEW_HOME),
    Tab("home_activity", pgettext_lazy("workbook", "Home · Activity"), "/#actividad", VIEW_HOME),
    Tab("employees", pgettext_lazy("workbook", "Employees · Staff"), "/employees", VIEW_HOME),
    Tab("employees_roles", pgettext_lazy("workbook", "Employees · Roles"), "/employees#roles", VIEW_HOME),
    Tab("role", pgettext_lazy("workbook", "Employees · Roles · What it allows"), "/employees/roles/:role", VIEW_HOME),
    Tab("employees_apikeys", pgettext_lazy("workbook", "Employees · API keys"), "/employees#apikeys", ADMINISTER_HUB),
    Tab("employees_approvals", pgettext_lazy("workbook", "Employees · Approvals"), "/employees#approvals", ADMINISTER_HUB),
    Tab("person", pgettext_lazy("workbook", "A person's page"), "/employees/:person", ADMINISTER_HUB),
    Tab("files", pgettext_lazy("workbook", "Files"), "/files", "base.view_files"),
    Tab("apps", pgettext_lazy("workbook", "Apps"), "/apps", VIEW_HOME),
    Tab("system_usage", pgettext_lazy("workbook", "System · Usage and plan"), "/system#usage", ADMINISTER_HUB),
    Tab("system_updates", pgettext_lazy("workbook", "System · Updates"), "/system#updates", ADMINISTER_HUB),
    Tab("system_events", pgettext_lazy("workbook", "System · Failed events"), "/system#events", ADMINISTER_HUB),
    Tab("system_logs", pgettext_lazy("workbook", "System · Logs"), "/system#logs", ADMINISTER_HUB),
    Tab("settings_general", pgettext_lazy("workbook", "Settings · General"), "/settings#general", VIEW_HOME),
    Tab("settings_business", pgettext_lazy("workbook", "Settings · Business"), "/settings#business", VIEW_HOME),
    # It only leads to the Printing app's printers.
    Tab("settings_printing", pgettext_lazy("workbook", "Settings · Printing"), "/settings#tickets", "printing.manage_settings"),
    Tab("settings_data", pgettext_lazy("workbook", "Settings · Data and backups"), "/settings#data", ADMINISTER_HUB),
    Tab("profile", pgettext_lazy("workbook", "My profile"), "/profile", VIEW_HOME),
)

#: The roles base's WORKBOOK names as a task's actor, the least first, each with what it and those above it hold and those
#: below it do not.
ROLES = (
    (pgettext_lazy("workbook", "accountancy firm"), VIEW_HOME),
    (pgettext_lazy("workbook", "employee"), VIEW_HOME),
    (pgettext_lazy("workbook", "manager"), OPEN_MANAGEMENT),
    (pgettext_lazy("workbook", "administrator"), ADMINISTER_HUB),
    (pgettext_lazy("workbook", "owner"), OWN_BUSINESS),
)


def permission_of(actors: Collection[str]) -> str:
    """What whoever does a task of ``actors``, written in the active language, holds: what the least of the roles among
    them does. With none of them (the system, whoever downloads a file), anyone who sees its screen."""
    return next((permission for role, permission in ROLES if str(role) in actors), VIEW_HOME)
