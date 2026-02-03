"""
Setting Input Component

A single input setting with title, description, and native input element.
Designed for touch-friendly settings pages.
"""
from django_components import Component, register


@register("setting_input")
class SettingInput(Component):
    template_name = "setting_input/setting_input.html"

    def get_context_data(
        self,
        name="",
        title="",
        description="",
        value="",
        type="text",
        placeholder="",
        min=None,
        max=None,
        step=None,
        disabled=False,
        **kwargs
    ):
        """
        Args:
            name: Setting key name (e.g., "default_capacity")
            title: Display title
            description: Help text description
            value: Initial value
            type: Input type (text, number, email, url, etc.)
            placeholder: Placeholder text
            min: Minimum value (for number type)
            max: Maximum value (for number type)
            step: Step value (for number type)
            disabled: Whether input is disabled
        """
        return {
            "name": name,
            "title": title,
            "description": description,
            "value": value,
            "type": type,
            "placeholder": placeholder,
            "min": min,
            "max": max,
            "step": step,
            "disabled": disabled,
            **kwargs
        }
