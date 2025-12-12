"""
Plugin Loader for ERPlora Hub
Dynamically loads and manages plugins from filesystem.

Plugins are stored in:
- Development: ./plugins/ (project directory)
- Production: Platform-specific external directory

Plugin naming convention:
- Active plugins: plugin_name/ (no prefix)
- Inactive plugins: _plugin_name/ (underscore prefix)

This loader discovers ALL plugins (active and inactive) and reports their status.
"""
import os
import sys
import json
import shutil
import importlib
from pathlib import Path
from typing import List, Dict, Optional
from django.conf import settings
from django.core.management import call_command


class PluginLoader:
    """
    Loads and manages plugins dynamically from filesystem.

    Plugins are Django apps stored in the plugins directory.
    - Active plugins: directory name without underscore prefix
    - Inactive plugins: directory name starts with underscore (_)
    """

    def __init__(self):
        # Use plugins directory from settings
        self.plugins_dir = Path(settings.PLUGINS_DIR)
        self.loaded_plugins = {}

        # Ensure plugins directory exists
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

        # Add plugins directory to Python path for dynamic imports
        if str(self.plugins_dir) not in sys.path:
            sys.path.insert(0, str(self.plugins_dir))

        print(f"[INFO] Plugin loader initialized")
        print(f"[INFO] Plugins directory: {self.plugins_dir}")

    def discover_plugins(self, include_inactive: bool = True) -> List[Dict]:
        """
        Discover all plugins in the plugins directory.

        Args:
            include_inactive: If True, include plugins with _ prefix (inactive)

        Returns:
            List of plugin metadata dictionaries
        """
        discovered = []

        if not self.plugins_dir.exists():
            return discovered

        # Iterate through plugin directories
        for plugin_dir in self.plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue

            # Skip hidden directories (start with .)
            if plugin_dir.name.startswith('.'):
                continue

            # Determine if plugin is active based on underscore prefix
            is_active = not plugin_dir.name.startswith('_')

            # Skip inactive plugins if not requested
            if not include_inactive and not is_active:
                continue

            # Get the actual plugin name (without underscore prefix)
            plugin_name = plugin_dir.name.lstrip('_')

            # Check for plugin.json
            plugin_json = plugin_dir / 'plugin.json'
            if not plugin_json.exists():
                # Create basic metadata for plugins without plugin.json
                metadata = {
                    'plugin_id': plugin_name,
                    'name': plugin_name.replace('_', ' ').title(),
                    'description': '',
                    'version': '1.0.0',
                    'author': '',
                    'icon': 'cube-outline',
                    'category': 'general',
                    'install_path': str(plugin_dir),
                    'dir_name': plugin_dir.name,
                    'is_active': is_active,
                }
                discovered.append(metadata)
                continue

            try:
                with open(plugin_json, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    metadata['install_path'] = str(plugin_dir)
                    metadata['dir_name'] = plugin_dir.name
                    metadata['is_active'] = is_active
                    # Ensure plugin_id matches directory name
                    if 'plugin_id' not in metadata:
                        metadata['plugin_id'] = plugin_name
                    # Get icon from root or menu.icon, fallback to default
                    if 'icon' not in metadata:
                        menu_config = metadata.get('menu', {})
                        metadata['icon'] = menu_config.get('icon', 'cube-outline')
                    discovered.append(metadata)
            except (json.JSONDecodeError, Exception) as e:
                print(f"[WARNING] Error loading plugin {plugin_dir.name}: {e}")
                # Still include it with basic metadata
                metadata = {
                    'plugin_id': plugin_name,
                    'name': plugin_name.replace('_', ' ').title(),
                    'description': f'Error loading: {e}',
                    'version': '1.0.0',
                    'author': '',
                    'icon': 'alert-circle-outline',
                    'category': 'general',
                    'install_path': str(plugin_dir),
                    'dir_name': plugin_dir.name,
                    'is_active': is_active,
                    'has_error': True,
                }
                discovered.append(metadata)

        return discovered

    def get_active_plugins(self) -> List[Dict]:
        """Get only active plugins (without underscore prefix)."""
        return self.discover_plugins(include_inactive=False)

    def activate_plugin(self, plugin_id: str) -> Dict:
        """
        Activate a plugin by removing underscore prefix from directory name.

        Args:
            plugin_id: The plugin identifier

        Returns:
            Dict with success status and message
        """
        # Find the plugin directory (with underscore prefix)
        inactive_dir = self.plugins_dir / f'_{plugin_id}'
        active_dir = self.plugins_dir / plugin_id

        if active_dir.exists():
            return {'success': True, 'message': 'Plugin already active'}

        if not inactive_dir.exists():
            return {'success': False, 'error': f'Plugin {plugin_id} not found'}

        try:
            # Rename directory to remove underscore prefix
            inactive_dir.rename(active_dir)
            return {
                'success': True,
                'message': f'Plugin {plugin_id} activated. Restart required to load.',
                'requires_restart': True
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def deactivate_plugin(self, plugin_id: str) -> Dict:
        """
        Deactivate a plugin by adding underscore prefix to directory name.

        Args:
            plugin_id: The plugin identifier

        Returns:
            Dict with success status and message
        """
        active_dir = self.plugins_dir / plugin_id
        inactive_dir = self.plugins_dir / f'_{plugin_id}'

        if inactive_dir.exists():
            return {'success': True, 'message': 'Plugin already inactive'}

        if not active_dir.exists():
            return {'success': False, 'error': f'Plugin {plugin_id} not found'}

        try:
            # Remove from loaded plugins
            if plugin_id in self.loaded_plugins:
                del self.loaded_plugins[plugin_id]

            # Rename directory to add underscore prefix
            active_dir.rename(inactive_dir)
            return {
                'success': True,
                'message': f'Plugin {plugin_id} deactivated. Restart required.',
                'requires_restart': True
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def delete_plugin(self, plugin_id: str) -> Dict:
        """
        Delete a plugin completely from filesystem.

        Args:
            plugin_id: The plugin identifier

        Returns:
            Dict with success status and message
        """
        # Try both active and inactive directories
        active_dir = self.plugins_dir / plugin_id
        inactive_dir = self.plugins_dir / f'_{plugin_id}'

        plugin_dir = None
        if active_dir.exists():
            plugin_dir = active_dir
        elif inactive_dir.exists():
            plugin_dir = inactive_dir
        else:
            return {'success': False, 'error': f'Plugin {plugin_id} not found'}

        try:
            # Remove from loaded plugins
            if plugin_id in self.loaded_plugins:
                del self.loaded_plugins[plugin_id]

            # Delete directory
            shutil.rmtree(plugin_dir)
            return {'success': True, 'message': f'Plugin {plugin_id} deleted'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def load_plugin(self, plugin_id: str) -> bool:
        """
        Load a plugin into Django runtime.

        Args:
            plugin_id: The plugin identifier (directory name without underscore)

        Returns:
            True if successful
        """
        plugin_path = self.plugins_dir / plugin_id

        if not plugin_path.exists():
            print(f"[ERROR] Plugin directory not found: {plugin_path}")
            return False

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
            }

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
        Load all active plugins (those without underscore prefix).

        Returns:
            Count of successfully loaded plugins
        """
        active_plugins = self.get_active_plugins()
        loaded_count = 0

        for plugin_meta in active_plugins:
            plugin_id = plugin_meta.get('plugin_id')
            if plugin_id and self.load_plugin(plugin_id):
                loaded_count += 1

        return loaded_count

    def get_menu_items(self) -> List[Dict]:
        """
        Get menu items for active plugins.

        Returns:
            List of menu items sorted by order
        """
        menu_items = []
        active_plugins = self.get_active_plugins()

        for plugin in active_plugins:
            menu_config = plugin.get('menu', {})
            if menu_config:
                menu_items.append({
                    'plugin_id': plugin.get('plugin_id'),
                    'label': menu_config.get('label', plugin.get('name', '')),
                    'icon': menu_config.get('icon', plugin.get('icon', 'cube-outline')),
                    'url': menu_config.get('url', f"/plugins/{plugin.get('plugin_id')}/"),
                    'order': menu_config.get('order', 100),
                })

        # Sort by order
        menu_items.sort(key=lambda x: x.get('order', 100))
        return menu_items


# Global plugin loader instance
plugin_loader = PluginLoader()
