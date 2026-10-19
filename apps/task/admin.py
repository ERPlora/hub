"""Django admin of the task app: full CRUD on every model, for the platform's staff.

Round 12 (PLAN §17, CLAUDE.md «Frontend y admin») gives the Hub admin full CRUD over all of a hub's
tables. A raw admin write records no event and checks no business rule (no number, no completion
date): the actions that need one call the operations of services.py. A task's or a project's «Delete»
locks it first (``lock_tasks``, ``lock_projects``), as the operations that delete them and every write
that names them do: it waits for the one under way and then takes what that write added.
"""

from django.contrib import admin
from django.db import transaction

from apps.task.models import Comment, Project, Task, TaskCounter
from apps.task.services import lock_projects, lock_tasks


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "color", "is_active", "owner", "created_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    readonly_fields = ("id", "created_at", "updated_at")

    def delete_model(self, request, obj):
        with transaction.atomic():
            lock_projects([obj.pk])
            super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            lock_projects(queryset.values_list("pk", flat=True))
            super().delete_queryset(request, queryset)


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    fields = ("text", "author", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "status", "priority", "due_date", "assigned_to", "project")
    list_filter = ("status", "priority")
    search_fields = ("number", "title", "description")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("parent",)
    inlines = [CommentInline]
    fields = (
        "id",
        ("number", "title"),
        "description",
        ("status", "priority"),
        ("project", "parent"),
        ("assigned_to", "created_by"),
        ("due_date", "completed_at"),
        "tags",
        ("created_at", "updated_at"),
    )

    def delete_model(self, request, obj):
        with transaction.atomic():
            lock_tasks([obj.pk])
            super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            lock_tasks(queryset.values_list("pk", flat=True))
            super().delete_queryset(request, queryset)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("task", "author", "created_at")
    search_fields = ("text", "task__number", "task__title")
    raw_id_fields = ("task",)
    readonly_fields = ("id", "created_at")


@admin.register(TaskCounter)
class TaskCounterAdmin(admin.ModelAdmin):
    list_display = ("__str__", "day", "last_number")
