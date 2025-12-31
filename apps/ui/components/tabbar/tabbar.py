"""
tabbar component - Ion Tab Bar for module navigation.

Usage:
    {% component "tabbar" module_id="inventory" current_view="products" oob=True %}{% endcomponent %}

Parameters:
    module_id: Module identifier to load tabs from module.json
    current_view: Current view identifier to highlight active tab
    oob: If True, renders with hx-swap-oob for #global-tabbar (default: True)
    color: Tab bar color (default: light)
    max_visible: Maximum visible tabs before showing "More" (default: 5)

The tabbar is sent via OOB swap to #global-tabbar in app_base.html.
If module.json has no "tabs" section, nothing is rendered.
If there are more than 5 tabs, shows 4 + "More" button with action sheet.
"""

import json
from pathlib import Path
from django.conf import settings
from django_components import Component, register


@register("tabbar")
class TabBar(Component):
    template_name = "tabbar/tabbar.html"

    def get_context_data(
        self,
        module_id: str = "",
        current_view: str = "",
        oob: bool = True,
        color: str = "light",
        max_visible: int = 5,
        **kwargs
    ):
        # If module_id provided, load tabs from module.json
        tabs = []
        if module_id:
            tabs = self._load_tabs_from_module(module_id)

        # If no tabs from module.json, render empty tabbar (to clear previous)
        if not tabs and module_id:
            return {
                "render": True,  # Still render to clear the tabbar
                "visible_tabs": [],
                "use_slots": False,
                "active_view": current_view,
                "oob": oob,
                "color": color,
            }

        # If no module_id, use slots mode (legacy)
        if not module_id:
            return {
                "render": True,
                "use_slots": True,
                "active_view": current_view,
                "oob": oob,
                "color": color,
                **kwargs,
            }

        # Calculate visible and overflow tabs
        if len(tabs) > max_visible:
            visible_tabs = tabs[:4]  # Show first 4
            overflow_tabs = tabs[4:]  # Rest in "More"
        else:
            visible_tabs = tabs
            overflow_tabs = []

        # Check if current view is in overflow
        active_view_in_overflow = any(
            t.get("id") == current_view for t in overflow_tabs
        )

        return {
            "render": True,
            "use_slots": False,
            "tabbar_module_id": module_id,
            "active_view": current_view,
            "visible_tabs": visible_tabs,
            "overflow_tabs": overflow_tabs,
            "active_view_in_overflow": active_view_in_overflow,
            "oob": oob,
            "color": color,
            **kwargs,
        }

    def _load_tabs_from_module(self, module_id: str) -> list:
        """Load tabs configuration from module.json"""
        modules_dir = Path(settings.MODULES_DIR)
        module_json_path = modules_dir / module_id / "module.json"

        if not module_json_path.exists():
            return []

        try:
            with open(module_json_path, "r", encoding="utf-8") as f:
                module_config = json.load(f)
                return module_config.get("tabs", [])
        except (json.JSONDecodeError, Exception):
            return []
