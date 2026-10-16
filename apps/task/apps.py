"""The task app: the team's to-do list, with projects, subtasks and comments (WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


class TaskConfig(LiveAppConfig):
    name = "apps.task"
    label = "task"
    kind = "app"
    verbose_name = _("Tasks")
    # Registered in the shell (ION_ICONS); the old module's `checkbox-outline` waits in UI-REQUESTS.md.
    icon = "ion:checkmark-circle-outline"
    category = Category.ORGANIZATION
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Your team's to-do list: tasks with who does them, priority and due date, projects and comments."
    )
    description = _(
        "Tasks is the to-do list of your team: each task has a title, a priority, a due date and the "
        "person who takes care of it, and can be grouped in projects, split into subtasks and discussed "
        "in a comment thread. Everyone sees the tasks they have to do, overdue ones stand out in red, and "
        "managers see and assign the whole team's work."
    )
    # A salon and a restaurant both run their opening, closing and stock chores from it.
    verticals = ["hair_salon", "restaurant"]
    # The assignee and a project's owner are staff records (staff.Member).
    requires = ["staff"]
    default_auto_field = "django.db.models.BigAutoField"
    permissions = [
        "task.view",
        "task.view_all",
        "task.add",
        "task.change",
        "task.change_all",
        "task.delete",
        "task.manage_project",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). An employee sees
    # and changes their own tasks (assigned to them or created by them); a manager, every task.
    role_permissions = {
        "hub_owner": ["task.*"],
        "hub_admin": ["task.*"],
        "hub_manager": ["task.*"],
        "hub_employee": ["task.view", "task.add", "task.change"],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. The same icons as the tabbar (frontend/tabs.ts); the old
    # `folder-outline` of Projects waits in UI-REQUESTS.md.
    navigation = [
        Nav("tasks", _("Tasks"), "ion:checkmark-circle-outline", "/task/tasks"),
        Nav("projects", _("Projects"), "ion:file-tray-outline", "/task/projects"),
    ]
