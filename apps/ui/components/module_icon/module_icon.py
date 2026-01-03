"""
module_icon component - Displays module icons with customizable sizes and styles.

Supports both SVG files (from module's static/icons/) and Ionicons.
Automatically applies theme colors (primary fill, transparent stroke).

Usage:
    {% component "module_icon"
        module_id="inventory"
        size="m"
        label="Inventory"
        url="/m/inventory/"
        color="primary" %}
    {% endcomponent %}

    <!-- With custom SVG path -->
    {% component "module_icon"
        svg_path="/static/inventory/icons/icon.svg"
        size="l"
        label="Products" %}
    {% endcomponent %}

    <!-- With Ionicon -->
    {% component "module_icon"
        icon="cube-outline"
        size="xl"
        label="Storage" %}
    {% endcomponent %}

Sizes:
    s:   40x40px (icon 20px)
    m:   56x56px (icon 28px) - default
    l:   64x64px (icon 32px)
    xl:  80x80px (icon 40px)
    xxl: 96x96px (icon 48px)

Params:
    module_id: Module ID to auto-load SVG from static/icons/icon.svg
    icon: Ionicon name (fallback if no SVG)
    svg_path: Direct path to SVG file
    size: Size variant (s, m, l, xl, xxl)
    label: Text label below icon
    url: URL for navigation (HTMX)
    color: Color variant (primary, success, warning, danger, etc.)
    show_label: Show label below icon (default True)
    clickable: Enable click behavior (default True)
    add_style: Use "add" button style (dashed border)
"""

from django_components import Component, register


@register("module_icon")
class ModuleIcon(Component):
    template_name = "module_icon/module_icon.html"

    class Media:
        css = "module_icon/module_icon.css"

    # Size configurations: (container_size, icon_size, border_radius)
    SIZES = {
        "s": {"container": 40, "icon": 20, "radius": 10},
        "m": {"container": 56, "icon": 28, "radius": 14},
        "l": {"container": 64, "icon": 32, "radius": 16},
        "xl": {"container": 80, "icon": 40, "radius": 20},
        "xxl": {"container": 96, "icon": 48, "radius": 24},
    }

    def get_context_data(
        self,
        module_id: str = "",
        icon: str = "cube-outline",
        svg_path: str = "",
        size: str = "m",
        label: str = "",
        url: str = "",
        color: str = "primary",
        show_label: bool = True,
        clickable: bool = True,
        add_style: bool = False,
        hx_target: str = "#main-content-area",
        **kwargs
    ):
        # Get size configuration
        size_config = self.SIZES.get(size, self.SIZES["m"])

        # Determine SVG path from module_id if not provided
        if not svg_path and module_id:
            svg_path = f"/static/{module_id}/icons/icon.svg"

        # Determine URL from module_id if not provided
        if not url and module_id:
            url = f"/m/{module_id}/"

        # Use module_id as label if not provided
        if not label and module_id:
            label = module_id.replace("_", " ").title()

        return {
            "module_id": module_id,
            "icon": icon,
            "svg_path": svg_path,
            "size": size,
            "size_config": size_config,
            "label": label,
            "url": url,
            "color": color,
            "show_label": show_label,
            "clickable": clickable,
            "add_style": add_style,
            "hx_target": hx_target,
            **kwargs,
        }
