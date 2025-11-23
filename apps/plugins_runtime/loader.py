"""
Plugin Loader for CPOS Hub
Dynamically loads and manages plugins from external data directory

Plugins are stored in platform-specific locations:
- Windows: C:\\Users\\<user>\\AppData\\Local\\ERPloraHub\\plugins\\
- macOS: ~/Library/Application Support/ERPloraHub/plugins/
- Linux: ~/.cpos-hub/plugins/

This allows plugins to persist across app updates and reinstalls.
"""
import os
import sys
import json
import importlib
from pathlib import Path
from typing import List, Dict, Optional
from django.conf import settings
from django.apps import apps
from django.core.management import call_command


class PluginLoader:
    """
    Loads and manages plugins dynamically from external data directory.

    Plugins are Django apps that live outside the main application bundle
    to ensure persistence across updates.
    """

    def __init__(self):
        # Use external plugins directory from settings
        self.plugins_dir = Path(settings.PLUGINS_DIR)
        self.loaded_plugins = {}

        # Ensure plugins directory exists
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

        # Add plugins directory to Python path for dynamic imports
        plugins_parent = str(self.plugins_dir.parent)
        if plugins_parent not in sys.path:
            sys.path.insert(0, plugins_parent)

        print(f"[INFO] Plugin loader initialized")
        print(f"[INFO] Plugins directory: {self.plugins_dir}")


    def load_plugin(self, plugin_id: str) -> bool:
        """
        Load a plugin directly from filesystem (no DB check).

        Simply checks if folder exists and doesn't start with _.

        Returns True if successful
        """
        try:
            # Build plugin path directly from plugin_id
            plugin_path = self.plugins_dir / plugin_id

            # Check if plugin directory exists
            if not plugin_path.exists():
                print(f"[ERROR] Plugin directory not found: {plugin_path}")
                return False

            # Check if disabled (starts with _)
            if plugin_id.startswith('_'):
                print(f"[INFO] Plugin {plugin_id} is disabled (starts with _)")
                return False

            # Ensure parent directory (plugins/) is in Python path
            plugin_parent = str(plugin_path.parent)
            if plugin_parent not in sys.path:
                sys.path.insert(0, plugin_parent)
                print(f"[INFO] Added to PYTHONPATH: {plugin_parent}")

            # Check if already loaded
            if plugin_id in self.loaded_plugins:
                print(f"[INFO] Plugin {plugin_id} already loaded")
                return True

            try:
                # Import the plugin module
                print(f"[INFO] Importing plugin module: {plugin_id}")
                plugin_module = importlib.import_module(plugin_id)

                # Add to Django INSTALLED_APPS if not already there
                if plugin_id not in settings.INSTALLED_APPS:
                    settings.INSTALLED_APPS = list(settings.INSTALLED_APPS) + [plugin_id]
                    print(f"[OK] Added {plugin_id} to INSTALLED_APPS")

                # Store in loaded plugins
                self.loaded_plugins[plugin_id] = {
                    'module': plugin_module,
                    'path': str(plugin_path),
                    'app_label': plugin_id
                }

                # Note: Migrations must be run manually via:
                # python manage.py migrate
                # (Cannot run migrations during app initialization)

                print(f"[OK] Plugin {plugin_id} loaded successfully")
                return True

            except ImportError as e:
                print(f"[ERROR] Failed to import plugin {plugin_id}: {e}")
                import traceback
                traceback.print_exc()
                return False

        except Exception as e:
            print(f"[ERROR] Failed to load plugin {plugin_id}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def load_all_active_plugins(self) -> int:
        """
        Load all active plugins from filesystem (folders without _)
        Returns count of successfully loaded plugins
        """
        loaded_count = 0

        # Scan filesystem for active plugins
        for plugin_dir in self.plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue

            # Skip disabled plugins (start with _ or .)
            if plugin_dir.name.startswith('.') or plugin_dir.name.startswith('_'):
                continue

            plugin_id = plugin_dir.name

            if self.load_plugin(plugin_id):
                loaded_count += 1

        return loaded_count

    def unload_plugin(self, plugin_id: str) -> bool:
        """
        Unload a plugin (just remove from memory).
        To disable permanently: rename folder to _{plugin_id}
        """
        # Remove from loaded plugins
        if plugin_id in self.loaded_plugins:
            del self.loaded_plugins[plugin_id]
            print(f"[INFO] Plugin {plugin_id} unloaded from memory")
            return True

        print(f"[WARNING] Plugin {plugin_id} was not loaded")
        return False


    def get_menu_items(self) -> List[Dict]:
        """
        Get all active plugin menu items directly from filesystem.
        Scans plugins directory and reads plugin.json for each active plugin.

        Returns list of menu items sorted by order
        """
        menu_items = []

        if not self.plugins_dir.exists():
            return menu_items

        # Scan filesystem for active plugins
        for plugin_dir in self.plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue

            # Skip disabled plugins (start with _ or .)
            if plugin_dir.name.startswith('.') or plugin_dir.name.startswith('_'):
                continue

            plugin_id = plugin_dir.name
            plugin_json_path = plugin_dir / 'plugin.json'

            # Read plugin.json if exists
            menu_config = {}
            if plugin_json_path.exists():
                try:
                    with open(plugin_json_path, 'r', encoding='utf-8') as f:
                        plugin_data = json.load(f)
                        menu_config = plugin_data.get('menu', {})
                except Exception as e:
                    print(f"[WARNING] Error reading plugin.json for {plugin_id}: {e}")

            # Build menu item
            menu_item = {
                'plugin_id': plugin_id,
                'label': menu_config.get('label', plugin_id.title()),
                'icon': menu_config.get('icon', 'cube-outline'),
                'order': menu_config.get('order', 100),
            }

            # Check if plugin has submenu items
            menu_items_config = menu_config.get('items', [])
            if menu_items_config:
                menu_item['items'] = menu_items_config
                menu_item['has_submenu'] = True
            else:
                # Single menu item, use url from menu.url
                menu_item['url'] = menu_config.get('url', f'/plugins/{plugin_id}/')
                menu_item['has_submenu'] = False

            # Only add if show_in_menu is not explicitly False
            if menu_config.get('show', True):
                menu_items.append(menu_item)

        # Sort by order, then by label
        menu_items.sort(key=lambda x: (x['order'], x['label']))

        return menu_items


# Global plugin loader instance
plugin_loader = PluginLoader()
