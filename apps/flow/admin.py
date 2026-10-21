"""Django admin of the flow app: full CRUD on every model, for the platform's staff, but the secrets.

Round 12 (PLAN §17, CLAUDE.md «Frontend y admin») gives the Hub admin full CRUD over all of a hub's
tables. A raw admin write records no event and checks nothing against the active apps: to run, grant
or switch an automation with its rules, use its operations (services.py). A secret (FLOW-F26) shows only
its name and can only be deleted: its value is sealed with the server's key by ``flow.secret.set``, and an
admin form would neither seal it nor ever show it.
"""

from django.contrib import admin

from apps.flow.models import Draft, Flow, FlowRun, Question, Secret


class FlowRunInline(admin.TabularInline):
    model = FlowRun
    extra = 0
    fields = ("started_at", "status", "trigger_kind", "event_name", "error_code", "finished_at")
    readonly_fields = fields
    show_change_link = True
    ordering = ("-started_at",)
    max_num = 0


@admin.register(Flow)
class FlowAdmin(admin.ModelAdmin):
    list_display = ("name", "enabled", "trigger_kind", "trigger_event", "version", "next_fire_at", "deleted_at")
    list_filter = ("enabled", "trigger_kind")
    search_fields = ("name", "trigger_event", "search_text", "recipe")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [FlowRunInline]
    fields = (
        "id",
        ("name", "enabled"),
        ("trigger_kind", "trigger_event"),
        "trigger_filter",
        "schedule",
        ("run_at", "next_fire_at"),
        "steps",
        "grants",
        ("version", "language"),
        ("recipe", "recipe_digest"),
        "search_text",
        ("created_by", "updated_by"),
        ("created_at", "updated_at", "deleted_at"),
    )


@admin.register(FlowRun)
class FlowRunAdmin(admin.ModelAdmin):
    list_display = ("flow", "started_at", "status", "trigger_kind", "event_name", "error_code")
    list_filter = ("status", "trigger_kind")
    search_fields = ("flow__name", "event_name", "trigger_key", "error_code")
    raw_id_fields = ("flow",)
    readonly_fields = ("id",)


@admin.register(Draft)
class DraftAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "created_by", "created_at", "decided_at")
    list_filter = ("status",)
    search_fields = ("name",)
    raw_id_fields = ("flow",)
    readonly_fields = ("id", "created_at")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("title", "flow", "role", "status", "expires_at", "decided_by", "decided_at")
    list_filter = ("status", "role")
    search_fields = ("title", "flow__name", "decided_by")
    raw_id_fields = ("run", "flow")
    readonly_fields = ("id",)


@admin.register(Secret)
class SecretAdmin(admin.ModelAdmin):
    list_display = ("name", "updated_by", "updated_at")
    search_fields = ("name",)
    fields = ("id", "name", "created_by", "updated_by", "created_at", "updated_at")
    readonly_fields = fields

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
