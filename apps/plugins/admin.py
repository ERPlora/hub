from django.contrib import admin
from .models import Plugin


@admin.register(Plugin)
class PluginAdmin(admin.ModelAdmin):
    list_display = ('name', 'version', 'plugin_id', 'is_installed', 'is_active', 'category', 'installed_at')
    list_filter = ('is_installed', 'is_active', 'category', 'show_in_menu')
    search_fields = ('name', 'plugin_id', 'description', 'author')
    ordering = ('menu_order', 'name')
    readonly_fields = ('installed_at', 'updated_at')

    fieldsets = (
        ('Plugin Information', {
            'fields': ('plugin_id', 'name', 'description', 'version', 'author', 'icon', 'category')
        }),
        ('Installation', {
            'fields': ('is_installed', 'is_active', 'install_path')
        }),
        ('Menu Configuration', {
            'fields': ('show_in_menu', 'menu_label', 'menu_icon', 'menu_order', 'main_url')
        }),
        ('Timestamps', {
            'fields': ('installed_at', 'updated_at')
        }),
    )
