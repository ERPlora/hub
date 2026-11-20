"""Django admin of the website app, read-mostly, for the staff only on hubs.erplora.com.

The staff see a business's site (its draft and what is published) and its images, in the admin of that business's
database, and may take the site offline (``is_live``: ``/`` jumps to the team's sign-in again), for instance for
content that must not be online. Nothing else is edited here: the content goes through the editor's operations, which
validate it and write its images' URLs; a row is never added or deleted (the site is created by its first save, an image
by its upload).
"""

from django.contrib import admin

from apps.website.models import Image, Site


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ("template", "is_live", "published_version", "published_at", "updated_at", "updated_by")
    fields = (
        "id",
        "is_live",
        "template",
        "theme",
        "content",
        "published_version",
        "published_at",
        "published_content",
        "reviews_snapshot",
        "updated_by",
        "updated_at",
    )
    readonly_fields = (
        "id",
        "template",
        "theme",
        "content",
        "published_version",
        "published_at",
        "published_content",
        "reviews_snapshot",
        "updated_by",
        "updated_at",
    )

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ("key", "content_type", "width", "height", "size", "created_at")
    search_fields = ("key", "sha256")
    date_hierarchy = "created_at"
    fields = ("id", "key", "sha256", "content_type", "width", "height", "size", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
