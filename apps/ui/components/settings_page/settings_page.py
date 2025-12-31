"""
Settings Page Component

Provides a consistent structure for module settings pages with:
- Tabbar OOB swap for HTMX navigation
- CSRF token
- Page header
- Slots for settings sections and info
"""
from django_components import Component, register


@register("settings_page")
class SettingsPage(Component):
    template_name = "settings_page/settings_page.html"

    def get_context_data(
        self,
        title="",
        subtitle="",
        module_id="",
        tabbar_template="",  # Legacy - kept for backwards compatibility
        tabbar_view="settings",
        save_url="",
        alpine_app="",
        **kwargs
    ):
        """
        Args:
            title: Page title (e.g., "Inventory Settings")
            subtitle: Page subtitle description
            module_id: Module ID for tabbar component (new system)
            tabbar_template: Path to tabbar template for OOB swap (legacy)
            tabbar_view: Current view name for tabbar highlighting
            save_url: URL for saving settings (used by Alpine.js)
            alpine_app: Name of Alpine.js app function (e.g., "settingsApp")
        """
        return {
            "title": title,
            "subtitle": subtitle,
            "module_id": module_id,
            "tabbar_template": tabbar_template,
            "tabbar_view": tabbar_view,
            "save_url": save_url,
            "alpine_app": alpine_app,
            **kwargs
        }
