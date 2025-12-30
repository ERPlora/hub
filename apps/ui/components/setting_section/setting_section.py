"""
Setting Section Component

Groups related settings with a title header.
"""
from django_components import Component, register


@register("setting_section")
class SettingSection(Component):
    template_name = "setting_section/setting_section.html"

    def get_context_data(self, title="", **kwargs):
        """
        Args:
            title: Section title (e.g., "Payment Methods")
        """
        return {
            "title": title,
            **kwargs
        }
