from django.contrib import admin
from .models import HubConfig, StoreConfig


@admin.register(HubConfig)
class HubConfigAdmin(admin.ModelAdmin):
    list_display = ('hub_id', 'is_configured', 'os_language', 'currency', 'dark_mode', 'created_at')
    readonly_fields = ('hub_id', 'cloud_api_token', 'created_at', 'updated_at')

    fieldsets = (
        ('Cloud Connection', {
            'fields': ('hub_id', 'cloud_api_token', 'is_configured')
        }),
        ('Language & Currency', {
            'fields': ('os_language', 'currency')
        }),
        ('Theme Preferences', {
            'fields': ('color_theme', 'dark_mode', 'auto_print')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(StoreConfig)
class StoreConfigAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'vat_number', 'is_configured', 'created_at')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Business Information', {
            'fields': ('business_name', 'business_address', 'vat_number', 'phone', 'email', 'website', 'logo')
        }),
        ('Tax Configuration', {
            'fields': ('tax_rate', 'tax_included')
        }),
        ('Receipt Configuration', {
            'fields': ('receipt_header', 'receipt_footer')
        }),
        ('Configuration Status', {
            'fields': ('is_configured',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
