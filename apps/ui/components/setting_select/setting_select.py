"""
Setting Select Component

A single select setting with title, description, and ion-select.
Designed for touch-friendly settings pages.
"""
from django_components import Component, register


@register("setting_select")
class SettingSelect(Component):
    template_name = "setting_select/setting_select.html"

    def get_context_data(
        self,
        name="",
        title="",
        description="",
        value="",
        options=None,
        placeholder="",
        interface="popover",
        disabled=False,
        **kwargs
    ):
        """
        Args:
            name: Setting key name (e.g., "default_sort")
            title: Display title
            description: Help text description
            value: Currently selected value
            options: List of dicts with 'value' and 'label' keys
            placeholder: Placeholder text
            interface: Ionic select interface (popover, action-sheet, alert)
            disabled: Whether select is disabled
        """
        return {
            "name": name,
            "title": title,
            "description": description,
            "value": value,
            "options": options or [],
            "placeholder": placeholder,
            "interface": interface,
            "disabled": disabled,
            **kwargs
        }
