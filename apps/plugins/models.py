from django.db import models
from config.plugin_categories import CATEGORY_CHOICES


class Plugin(models.Model):
    """
    Installed plugins in the Hub.
    Plugins extend the functionality of the ERP system.
    """
    # Plugin identification
    plugin_id = models.CharField(max_length=100, unique=True)  # e.g., 'products', 'pos-basic'
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    version = models.CharField(max_length=50)

    # Plugin metadata
    author = models.CharField(max_length=255, blank=True)
    icon = models.CharField(max_length=50, default='extension-puzzle-outline')
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default='utilities',
        help_text='Plugin category from PLUGIN_CATEGORIES'
    )

    # Installation status
    is_installed = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    install_path = models.CharField(max_length=500, blank=True)

    # Menu configuration
    menu_label = models.CharField(max_length=100, blank=True)
    menu_icon = models.CharField(max_length=50, blank=True)
    menu_order = models.IntegerField(default=100)
    show_in_menu = models.BooleanField(default=True)

    # URLs
    main_url = models.CharField(max_length=200, blank=True)  # Main entry point URL

    # Timestamps
    installed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Plugin'
        verbose_name_plural = 'Plugins'
        ordering = ['menu_order', 'name']
        db_table = 'core_plugin'  # Keep existing table name

    def __str__(self):
        return f"{self.name} v{self.version}"
