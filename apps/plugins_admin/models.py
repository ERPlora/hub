# apps/plugins_admin/models.py
from django.db import models


class Plugin(models.Model):
    """
    Plugin model for managing installed plugins in the Hub.
    This is the single source of truth for plugin metadata.
    """
    # Plugin identification
    plugin_id = models.CharField(max_length=100, unique=True)  # e.g. "products"
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    version = models.CharField(max_length=50, default="1.0.0")
    author = models.CharField(max_length=100, blank=True)

    # Installation
    install_path = models.CharField(max_length=500, blank=True)
    is_installed = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)

    # UI/Menu configuration
    icon = models.CharField(max_length=50, default="cube-outline")
    category = models.CharField(max_length=50, default="general")
    menu_label = models.CharField(max_length=100, blank=True)
    menu_icon = models.CharField(max_length=50, blank=True)
    menu_order = models.IntegerField(default=100)
    show_in_menu = models.BooleanField(default=True)

    # URL routing
    main_url = models.CharField(max_length=200, blank=True)  # "/products/" or empty

    # Multiple menu items support (JSON field)
    # Format: [{"label": "Products", "url": "/products/", "icon": "cube-outline"}, ...]
    menu_items = models.JSONField(default=list, blank=True)

    # Timestamps
    installed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'plugins_admin_plugin'
        verbose_name = 'Plugin'
        verbose_name_plural = 'Plugins'
        ordering = ['menu_order', 'name']

    def __str__(self):
        return f"{self.name} v{self.version}"
