"""
Plugin Loader for CPOS Hub
Dynamically loads and manages plugins
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
    Loads and manages plugins dynamically
    """

    def __init__(self):
        self.plugins_dir = Path(settings.BASE_DIR) / 'plugins'
        self.loaded_plugins = {}

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
        Load a plugin into Django INSTALLED_APPS
        Returns True if successful
        """
        from apps.core.models import Plugin

        try:
            # Get plugin from database
            plugin = Plugin.objects.get(plugin_id=plugin_id, is_active=True)

            if not plugin.install_path:
                return False

            plugin_path = Path(plugin.install_path)

            # Check if plugin directory exists
            if not plugin_path.exists():
                return False

            # Add plugin directory to Python path if not already there
            plugin_parent = str(plugin_path.parent)
            if plugin_parent not in sys.path:
                sys.path.insert(0, plugin_parent)

            # Import plugin module
            plugin_module_name = plugin_path.name

            # Check if already loaded
            if plugin_module_name in self.loaded_plugins:
                return True

            try:
                # Import the plugin module
                plugin_module = importlib.import_module(plugin_module_name)

                # Add to Django INSTALLED_APPS if not already there
                app_label = f'plugins.{plugin_module_name}'
                if app_label not in settings.INSTALLED_APPS:
                    settings.INSTALLED_APPS = list(settings.INSTALLED_APPS) + [app_label]

                # Store in loaded plugins
                self.loaded_plugins[plugin_id] = {
                    'module': plugin_module,
                    'path': str(plugin_path),
                    'app_label': app_label
                }

                # Apply migrations if any
                try:
                    call_command('migrate', plugin_module_name, '--noinput')
                except Exception as e:
                    print(f"Migration warning for {plugin_id}: {e}")

                return True

            except ImportError as e:
                print(f"Error importing plugin {plugin_id}: {e}")
                return False

        except Plugin.DoesNotExist:
            return False
        except Exception as e:
            print(f"Error loading plugin {plugin_id}: {e}")
            return False

    def load_all_active_plugins(self) -> int:
        """
        Load all active plugins from database
        Returns count of successfully loaded plugins
        """
        from apps.core.models import Plugin

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
        from apps.core.models import Plugin

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
        from apps.core.models import Plugin

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
        """
        from apps.core.models import Plugin

        plugins = Plugin.objects.filter(
            is_active=True,
            is_installed=True,
            show_in_menu=True
        ).order_by('menu_order', 'name')

        menu_items = []
        for plugin in plugins:
            menu_items.append({
                'plugin_id': plugin.plugin_id,
                'label': plugin.menu_label or plugin.name,
                'icon': plugin.menu_icon or 'cube-outline',
                'url': plugin.main_url or f'#',
                'order': plugin.menu_order,
            })

        return menu_items


# Global plugin loader instance
plugin_loader = PluginLoader()
