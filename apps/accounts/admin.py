from django.contrib import admin
from .models import LocalUser


@admin.register(LocalUser)
class LocalUserAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'role', 'is_active', 'last_login', 'created_at')
    list_filter = ('role', 'is_active', 'created_at')
    search_fields = ('name', 'email')
    ordering = ('name',)
    readonly_fields = ('cloud_user_id', 'created_at', 'updated_at', 'last_login')

    fieldsets = (
        ('User Information', {
            'fields': ('cloud_user_id', 'email', 'name')
        }),
        ('Authentication', {
            'fields': ('pin_hash', 'is_active')
        }),
        ('Role & Preferences', {
            'fields': ('role', 'language')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'last_login')
        }),
    )
