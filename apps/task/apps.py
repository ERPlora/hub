"""The task app: the team's to-do list, with projects, subtasks and comments (WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, Help, LiveAppConfig, Nav


class TaskConfig(LiveAppConfig):
    name = "apps.task"
    label = "task"
    blueprint_stays = {
        "Comment": "history",
        "TaskCounter": "internal",
    }
    kind = "app"
    verbose_name = _("Tasks")
    # Registered in the shell (ION_ICONS).
    icon = "ion:checkbox-outline"
    category = Category.ORGANIZATION
    premium = False
    # The public store's texts, which register_apps writes to shared.app.
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
    # What these words mean to the Hub's assistant (base.assistant.relevance.synonyms). A «tarea» and a «proyecto» are the task
    # and the project (task.task, task.project), and what one «comenta» a comment (task.comment), named by its phrases
    # and never by the word: «comentario» shares its stem with «comensales», a table's guests.
    assistant_synonyms = (
        ("tarea", "tareas", "task", "tasks"),
        ("proyecto", "proyectos", "project", "projects"),
        (
            "comment", "comments", "comenta en", "comenta que", "un comentario", "el comentario", "los comentarios",
            "sus comentarios", "que comentarios", "de comentarios",
        ),
    )
    permissions = {
        "task.view": _("View their own tasks and the projects"),
        "task.view_all": _("View all tasks"),
        "task.add": _("Create tasks and subtasks"),
        "task.change": _("Change, assign, complete and comment on their own tasks"),
        "task.change_all": _("Change, assign, complete and comment on any task"),
        "task.delete": _("Delete tasks"),
        "task.manage_project": _("Create, change and delete projects"),
    }
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). An employee sees
    # and changes their own tasks (assigned to them or created by them); a manager, every task.
    role_permissions = {
        "hub_owner": ["task.*"],
        "hub_admin": ["task.*"],
        "hub_manager": ["task.*"],
        "hub_employee": ["task.view", "task.add", "task.change"],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. Each entry is also a tab of the app's pages.
    navigation = [
        Nav("tasks", _("Tasks"), "ion:checkbox-outline", "/task/tasks", permission="task.view"),
        Nav("projects", _("Projects"), "ion:folder-outline", "/task/projects", permission="task.view"),
    ]
    help = Help(
        videos={"es": "73wOkcIBVpw", "en": "njU86EpkRC4"},
        flow_videos={
            "TASK-F01": {"es": ["cm6YZAImrmg"], "en": ["s_Hp15-5B18"]},
            "TASK-F04": {"es": ["aVwwCoD-FFo"], "en": ["NfhAAruRWik"]},
            "TASK-F05": {"es": ["R_T_HTZ6fAQ"], "en": ["ZaLS5IWfcbM"]},
            "TASK-F06": {"es": ["R_T_HTZ6fAQ"], "en": ["ZaLS5IWfcbM"]},
            "TASK-F07": {"es": ["R_T_HTZ6fAQ"], "en": ["ZaLS5IWfcbM"]},
            "TASK-F08": {"es": ["cm6YZAImrmg"], "en": ["s_Hp15-5B18"]},
            "TASK-F09": {"es": ["aVwwCoD-FFo"], "en": ["NfhAAruRWik"]},
            "TASK-F10": {"es": ["aVwwCoD-FFo"], "en": ["NfhAAruRWik"]},
            "TASK-F11": {"es": ["cm6YZAImrmg"], "en": ["s_Hp15-5B18"]},
            "TASK-F12": {"es": ["Z3CpRKoAGtE"], "en": ["Aw0iv2BJI8g"]},
            "TASK-F13": {"es": ["Z3CpRKoAGtE"], "en": ["Aw0iv2BJI8g"]},
            "TASK-F14": {"es": ["Z3CpRKoAGtE"], "en": ["Aw0iv2BJI8g"]},
        },
    )

    def blueprint_datasets(self) -> list:
        """What of Tasks travels in an export of the business (BASE-F35): its active projects and its open tasks."""
        from apps.task import blueprint  # base.blueprint loads the apps' models, not loaded yet when this module is

        return blueprint.DATASETS
