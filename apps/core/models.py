"""
Core app models.

Contains the Plugin model for tracking installed plugins.
Other models have been refactored to their respective apps:

- LocalUser → apps.accounts.models
- HubConfig, StoreConfig → apps.configuration.models
- TokenCache, SyncQueue → apps.sync.models
"""

from django.db import models
from django.utils import timezone


class Plugin(models.Model):
    """
    Tracks installed plugins in the Hub.

    Each plugin is a Django app that can be dynamically loaded/unloaded.
    Plugin metadata is stored here after installation.
    """

    plugin_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    version = models.CharField(max_length=50, default='1.0.0')
    author = models.CharField(max_length=255, blank=True, default='')
    icon = models.CharField(max_length=50, blank=True, default='extension-puzzle-outline')
    category = models.CharField(max_length=50, blank=True, default='general')

    # Installation status
    is_installed = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    install_path = models.CharField(max_length=500, blank=True, default='')

    # Menu configuration
    menu_label = models.CharField(max_length=100, blank=True, default='')
    menu_icon = models.CharField(max_length=50, blank=True, default='')
    menu_order = models.IntegerField(default=100)
    show_in_menu = models.BooleanField(default=True)
    main_url = models.CharField(max_length=200, blank=True, default='')

    # Timestamps
    installed_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['menu_order', 'name']
        verbose_name = 'Plugin'
        verbose_name_plural = 'Plugins'

    def __str__(self):
        status = "active" if self.is_active else "inactive"
        return f"{self.name} v{self.version} ({status})"

    def get_menu_url(self):
        """Returns the main URL for this plugin."""
        if self.main_url:
            return self.main_url
        return f"/plugins/{self.plugin_id}/"
