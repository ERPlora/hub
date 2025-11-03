from django.contrib import admin
from .models import HubConfig, LocalUser


@admin.register(HubConfig)
class HubConfigAdmin(admin.ModelAdmin):
    list_display = ('id', 'hub_id', 'is_configured', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(LocalUser)
class LocalUserAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'role', 'is_active', 'last_login')
    list_filter = ('role', 'is_active')
    search_fields = ('name', 'email')
    readonly_fields = ('created_at', 'updated_at', 'last_login')
