"""
header component - Content header for module pages.

Displays inside #main-content-area with title, back button, and action buttons.

Usage:
    {% component "header" title=_("Products") %}{% endcomponent %}

With back button (automatic from context processor):
    {% component "header" title=_("Product Detail") %}{% endcomponent %}

With action buttons:
    {% component "header" title=_("Products") %}
        {% fill "actions" %}
        <button class="ux-button ux-button--sm ux-button--clear">
            {% icon "add-outline" %}
        </button>
        {% endfill %}
    {% endcomponent %}

Full example:
    {% component "header" title=_("Edit Product") back_url="inventory:products_list" %}
        {% fill "actions" %}
        <button class="ux-button ux-button--sm ux-color-danger">
            {% icon "trash-outline" %}
            Delete
        </button>
        {% endfill %}
    {% endcomponent %}
"""

from django_components import Component, register


@register("header")
class Header(Component):
    template_name = "header/header.html"

    def get_context_data(
        self,
        title: str = "",
        back_url: str = "",
        back_label: str = "",
        color: str = "light",
        oob: bool = False,
        **kwargs
    ):
        """
        Args:
            title: Page title
            back_url: Django URL name for back button (optional, uses context if not provided)
            back_label: Label for back button (default: empty, icon only)
            color: Toolbar color (default: light)
            oob: Out-of-band swap for HTMX (default: False)
        """
        return {
            "title": title,
            "back_url": back_url,
            "back_label": back_label,
            "color": color,
            "oob": oob,
            **kwargs,
        }
