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

    def discover_plugins(self) -> List[Dict]:
        """
        Discover all plugins in the plugins directory
        Returns list of plugin metadata
        """
        discovered = []

        if not self.plugins_dir.exists():
            return discovered

        # Iterate through plugin directories
        for plugin_dir in self.plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue

            # Skip hidden directories and example
            if plugin_dir.name.startswith('.') or plugin_dir.name.startswith('_'):
                continue

            # Check for plugin.json
            plugin_json = plugin_dir / 'plugin.json'
            if not plugin_json.exists():
                continue

            try:
                with open(plugin_json, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    metadata['install_path'] = str(plugin_dir)
                    discovered.append(metadata)
            except (json.JSONDecodeError, Exception) as e:
                print(f"Error loading plugin {plugin_dir.name}: {e}")
                continue

        return discovered

    def load_plugin(self, plugin_id: str) -> bool:
        """
        Load a plugin into Django INSTALLED_APPS from external directory.

        Plugins are Django apps stored in the external plugins directory.
        This method:
        1. Adds the plugin directory to PYTHONPATH
        2. Imports the plugin module
        3. Adds it to INSTALLED_APPS
        4. Runs migrations

        Returns True if successful
        """
        from django.apps import apps as django_apps
        Plugin = django_apps.get_model("plugins_admin", "Plugin")

        try:
            # Get plugin from database
            plugin = Plugin.objects.get(plugin_id=plugin_id, is_active=True)

            if not plugin.install_path:
                print(f"[ERROR] Plugin {plugin_id} has no install path")
                return False

            plugin_path = Path(plugin.install_path)

            # Check if plugin directory exists
            if not plugin_path.exists():
                print(f"[ERROR] Plugin directory not found: {plugin_path}")
                return False

            # Ensure parent directory (plugins/) is in Python path
            plugin_parent = str(plugin_path.parent)
            if plugin_parent not in sys.path:
                sys.path.insert(0, plugin_parent)
                print(f"[INFO] Added to PYTHONPATH: {plugin_parent}")

            # Import plugin module using relative import from plugins directory
            plugin_module_name = plugin_path.name

            # Check if already loaded
            if plugin_module_name in self.loaded_plugins:
                print(f"[INFO] Plugin {plugin_id} already loaded")
                return True

            try:
                # Import the plugin module
                # Since plugins/ is in sys.path, we can import directly
                print(f"[INFO] Importing plugin module: {plugin_module_name}")
                plugin_module = importlib.import_module(plugin_module_name)

                # Add to Django INSTALLED_APPS if not already there
                # Use just the module name since it's importable from plugins/
                app_label = plugin_module_name
                if app_label not in settings.INSTALLED_APPS:
                    settings.INSTALLED_APPS = list(settings.INSTALLED_APPS) + [app_label]
                    print(f"[OK] Added {app_label} to INSTALLED_APPS")

                # Store in loaded plugins
                self.loaded_plugins[plugin_id] = {
                    'module': plugin_module,
                    'path': str(plugin_path),
                    'app_label': app_label
                }

                # Apply migrations if any
                try:
                    print(f"[INFO] Running migrations for {plugin_module_name}...")
                    call_command('migrate', plugin_module_name, '--noinput')
                    print(f"[OK] Migrations applied for {plugin_module_name}")
                except Exception as e:
                    print(f"[WARNING] Migration warning for {plugin_id}: {e}")

                print(f"[OK] Plugin {plugin_id} loaded successfully")
                return True

            except ImportError as e:
                print(f"[ERROR] Failed to import plugin {plugin_id}: {e}")
                import traceback
                traceback.print_exc()
                return False

        except Plugin.DoesNotExist:
            print(f"[ERROR] Plugin {plugin_id} not found in database")
            return False
        except Exception as e:
            print(f"[ERROR] Failed to load plugin {plugin_id}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def load_all_active_plugins(self) -> int:
        """
        Load all active plugins from database
        Returns count of successfully loaded plugins
        """
        from django.apps import apps as django_apps
        Plugin = django_apps.get_model("plugins_admin", "Plugin")

        active_plugins = Plugin.objects.filter(is_active=True, is_installed=True)
        loaded_count = 0

        for plugin in active_plugins:
            if self.load_plugin(plugin.plugin_id):
                loaded_count += 1

        return loaded_count

    def unload_plugin(self, plugin_id: str) -> bool:
        """
        Unload a plugin (mark as inactive)
        Note: Cannot truly unload from Python runtime, but can mark as inactive
        """
        from django.apps import apps as django_apps
        Plugin = django_apps.get_model("plugins_admin", "Plugin")

        try:
            plugin = Plugin.objects.get(plugin_id=plugin_id)
            plugin.is_active = False
            plugin.save()

            # Remove from loaded plugins
            if plugin_id in self.loaded_plugins:
                del self.loaded_plugins[plugin_id]

            return True
        except Plugin.DoesNotExist:
            return False

    def install_plugin_from_metadata(self, metadata: Dict) -> Optional['Plugin']:
        """
        Install a plugin from its metadata (plugin.json)
        Creates/updates Plugin model instance
        """
        from django.apps import apps as django_apps
        Plugin = django_apps.get_model("plugins_admin", "Plugin")

        plugin_id = metadata.get('plugin_id')
        if not plugin_id:
            return None

        # Get or create plugin
        plugin, created = Plugin.objects.get_or_create(
            plugin_id=plugin_id,
            defaults={
                'name': metadata.get('name', plugin_id),
                'description': metadata.get('description', ''),
                'version': metadata.get('version', '1.0.0'),
                'author': metadata.get('author', ''),
                'icon': metadata.get('icon', 'cube-outline'),
                'category': metadata.get('category', 'general'),
                'install_path': metadata.get('install_path', ''),
                'is_installed': True,
                'is_active': True,
            }
        )

        # Update if already exists
        if not created:
            plugin.name = metadata.get('name', plugin.name)
            plugin.description = metadata.get('description', plugin.description)
            plugin.version = metadata.get('version', plugin.version)
            plugin.author = metadata.get('author', plugin.author)
            plugin.icon = metadata.get('icon', plugin.icon)
            plugin.category = metadata.get('category', plugin.category)
            plugin.install_path = metadata.get('install_path', plugin.install_path)
            plugin.is_installed = True

        # Update menu configuration
        menu_config = metadata.get('menu', {})
        if menu_config:
            plugin.menu_label = menu_config.get('label', metadata.get('name', plugin_id))
            plugin.menu_icon = menu_config.get('icon', metadata.get('icon', 'cube-outline'))
            plugin.menu_order = menu_config.get('order', 100)
            plugin.show_in_menu = menu_config.get('show', True)

            # Process menu items (multiple submenu items)
            menu_items = menu_config.get('items', [])
            if menu_items:
                plugin.menu_items = menu_items

        plugin.main_url = metadata.get('main_url', '')
        plugin.save()

        return plugin

    def sync_plugins(self) -> tuple:
        """
        Sync plugins from filesystem to database
        Returns (installed_count, updated_count)
        """
        discovered = self.discover_plugins()
        installed_count = 0
        updated_count = 0

        for metadata in discovered:
            plugin = self.install_plugin_from_metadata(metadata)
            if plugin:
                if plugin.pk:
                    updated_count += 1
                else:
                    installed_count += 1

        return (installed_count, updated_count)

    def get_menu_items(self) -> List[Dict]:
        """
        Get all active plugin menu items for sidebar
        Returns list of menu items sorted by order

        Structure:
        - If plugin has menu_items (submenu), returns it with 'items' key
        - If plugin has no menu_items, returns simple menu item
        """
        from django.apps import apps as django_apps
        Plugin = django_apps.get_model("plugins_admin", "Plugin")

        plugins = Plugin.objects.filter(
            is_active=True,
            is_installed=True,
            show_in_menu=True
        ).order_by('menu_order', 'name')

        menu_items = []
        for plugin in plugins:
            menu_item = {
                'plugin_id': plugin.plugin_id,
                'label': plugin.menu_label or plugin.name,
                'icon': plugin.menu_icon or 'cube-outline',
                'order': plugin.menu_order,
            }

            # If plugin has multiple menu items (submenu), add them
            if plugin.menu_items and len(plugin.menu_items) > 0:
                menu_item['items'] = plugin.menu_items
                menu_item['has_submenu'] = True
            else:
                # Single menu item, use main_url
                menu_item['url'] = plugin.main_url or f'#'
                menu_item['has_submenu'] = False

            menu_items.append(menu_item)

        return menu_items


# Global plugin loader instance
plugin_loader = PluginLoader()
