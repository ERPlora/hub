from django.contrib import admin
from .models import TokenCache, SyncQueue


@admin.register(TokenCache)
class TokenCacheAdmin(admin.ModelAdmin):
    list_display = ('id', 'jwt_cached_at', 'public_key_cached_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at', 'jwt_cached_at', 'public_key_cached_at')

    fieldsets = (
        ('JWT Tokens', {
            'fields': ('jwt_access_token', 'jwt_refresh_token', 'jwt_cached_at')
        }),
        ('RSA Public Key', {
            'fields': ('rsa_public_key', 'public_key_cached_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(SyncQueue)
class SyncQueueAdmin(admin.ModelAdmin):
    list_display = ('operation_type', 'status', 'method', 'retry_count', 'created_at', 'next_retry_at')
    list_filter = ('operation_type', 'status', 'method')
    search_fields = ('endpoint', 'last_error')
    ordering = ('created_at',)
    readonly_fields = ('created_at', 'updated_at', 'completed_at')

    fieldsets = (
        ('Operation Details', {
            'fields': ('operation_type', 'endpoint', 'method', 'payload', 'headers')
        }),
        ('Sync Status', {
            'fields': ('status', 'retry_count', 'max_retries', 'last_error')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'completed_at', 'next_retry_at')
        }),
    )
