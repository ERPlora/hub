"""
Setting Toggle Component

A single toggle setting with title, description, and ion-toggle.
Designed for touch-friendly settings pages.
"""
from django_components import Component, register


@register("setting_toggle")
class SettingToggle(Component):
    template_name = "setting_toggle/setting_toggle.html"

    def get_context_data(
        self,
        name="",
        title="",
        description="",
        checked=False,
        ref="",
        color="success",
        disabled=False,
        **kwargs
    ):
        """
        Args:
            name: Setting key name (e.g., "allow_negative_stock")
            title: Display title
            description: Help text description
            checked: Initial checked state
            ref: Alpine.js x-ref name (auto-generated from name if not provided)
            color: Toggle color when checked (success, primary, warning, danger)
            disabled: Whether toggle is disabled
        """
        return {
            "name": name,
            "title": title,
            "description": description,
            "checked": checked,
            "ref": ref or f"toggle_{name}",
            "color": color,
            "disabled": disabled,
            **kwargs
        }
