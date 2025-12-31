"""
tab component - Single tab button for ion-tab-bar.

Usage with SVG icon (recommended):
    {% with cv=current_view %}
    {% component "tab" url="inventory:dashboard" icon_svg="inventory/icons/overview.svg" label=_("Overview") view="dashboard" current_view=cv %}{% endcomponent %}
    {% component "tab" url="inventory:products_list" icon_svg="inventory/icons/products.svg" label=_("Products") view="products" current_view=cv %}{% endcomponent %}
    {% endwith %}

Usage with Ionicon (fallback):
    {% component "tab" url="inventory:dashboard" icon="grid-outline" label=_("Overview") view="dashboard" current_view=cv %}{% endcomponent %}

The 'view' parameter is compared with 'current_view' to determine active state.
The icon_svg path is relative to the module's static folder.
"""

from django_components import Component, register


@register("tab")
class Tab(Component):
    template_name = "tab/tab.html"

    def get_context_data(
        self,
        url: str,
        label: str,
        icon: str = "",
        icon_svg: str = "",
        view: str = "",
        current_view: str = "",
        disabled: bool = False,
        badge: str = None,
        badge_color: str = "danger",
        **kwargs
    ):
        """
        Args:
            url: Django URL name (required) - will be resolved with {% url %}
            label: Tab label text (required) - use _("text") for translation
            icon: Ionicon name (optional, fallback if no icon_svg)
            icon_svg: Path to SVG icon in static folder (e.g., "inventory/icons/overview.svg")
            view: View identifier for this tab
            current_view: Current active view - compared with view for active state
            disabled: If True, tab is disabled
            badge: Badge text to show
            badge_color: Badge color (default: danger)
        """
        # Rename to avoid conflict with context processor's current_view
        return {
            "url": url,
            "label": label,
            "icon": icon,
            "icon_svg": icon_svg,
            "view": view,
            "tab_current_view": current_view,
            "is_active": view == current_view if view and current_view else False,
            "disabled": disabled,
            "badge": badge,
            "badge_color": badge_color,
            **kwargs,
        }
