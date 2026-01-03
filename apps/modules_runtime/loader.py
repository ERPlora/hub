"""
Module Loader for CPOS Hub
Dynamically loads and manages modules from external data directory

Modules are stored in platform-specific locations:
- Windows: C:\\Users\\<user>\\AppData\\Local\\ERPloraHub\\modules\\
- macOS: ~/Library/Application Support/ERPloraHub/modules/
- Linux: ~/.cpos-hub/modules/

This allows modules to persist across app updates and reinstalls.
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


class ModuleLoader:
    """
    Loads and manages modules dynamically from external data directory.

    Modules are Django apps that live outside the main application bundle
    to ensure persistence across updates.
    """

    def __init__(self):
        # Use external modules directory from settings
        self.modules_dir = Path(settings.MODULES_DIR)
        self.loaded_modules = {}

        # Ensure modules directory exists
        self.modules_dir.mkdir(parents=True, exist_ok=True)

        # Add modules directory to Python path for dynamic imports
        modules_parent = str(self.modules_dir.parent)
        if modules_parent not in sys.path:
            sys.path.insert(0, modules_parent)

        print(f"[INFO] Module loader initialized")
        print(f"[INFO] Modules directory: {self.modules_dir}")


    def load_module(self, module_id: str) -> bool:
        """
        Load a module directly from filesystem (no DB check).

        Simply checks if folder exists and doesn't start with _.

        Returns True if successful
        """
        try:
            # Build module path directly from module_id
            module_path = self.modules_dir / module_id

            # Check if module directory exists
            if not module_path.exists():
                print(f"[ERROR] Module directory not found: {module_path}")
                return False

            # Check if disabled (starts with _)
            if module_id.startswith('_'):
                print(f"[INFO] Module {module_id} is disabled (starts with _)")
                return False

            # Ensure parent directory (modules/) is in Python path
            module_parent = str(module_path.parent)
            if module_parent not in sys.path:
                sys.path.insert(0, module_parent)
                print(f"[INFO] Added to PYTHONPATH: {module_parent}")

            # Check if already loaded
            if module_id in self.loaded_modules:
                print(f"[INFO] Module {module_id} already loaded")
                return True

            try:
                # Import the module
                print(f"[INFO] Importing module: {module_id}")
                module_pkg = importlib.import_module(module_id)

                # Add to Django INSTALLED_APPS if not already there
                if module_id not in settings.INSTALLED_APPS:
                    settings.INSTALLED_APPS = list(settings.INSTALLED_APPS) + [module_id]
                    print(f"[OK] Added {module_id} to INSTALLED_APPS")

                # Store in loaded modules
                self.loaded_modules[module_id] = {
                    'module': module_pkg,
                    'path': str(module_path),
                    'app_label': module_id
                }

                # Note: Migrations must be run manually via:
                # python manage.py migrate
                # (Cannot run migrations during app initialization)

                print(f"[OK] Module {module_id} loaded successfully")
                return True

            except ImportError as e:
                print(f"[ERROR] Failed to import module {module_id}: {e}")
                import traceback
                traceback.print_exc()
                return False

        except Exception as e:
            print(f"[ERROR] Failed to load module {module_id}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def load_all_active_modules(self) -> int:
        """
        Load all active modules from filesystem (folders without _)
        Returns count of successfully loaded modules
        """
        loaded_count = 0

        # Scan filesystem for active modules
        for module_dir in self.modules_dir.iterdir():
            if not module_dir.is_dir():
                continue

            # Skip disabled modules (start with _ or .)
            if module_dir.name.startswith('.') or module_dir.name.startswith('_'):
                continue

            module_id = module_dir.name

            if self.load_module(module_id):
                loaded_count += 1

        return loaded_count

    def unload_module(self, module_id: str) -> bool:
        """
        Unload a module (just remove from memory).
        To disable permanently: rename folder to _{module_id}
        """
        # Remove from loaded modules
        if module_id in self.loaded_modules:
            del self.loaded_modules[module_id]
            print(f"[INFO] Module {module_id} unloaded from memory")
            return True

        print(f"[WARNING] Module {module_id} was not loaded")
        return False


    def get_menu_items(self) -> List[Dict]:
        """
        Get all active module menu items from module.py configuration.
        Scans modules directory and imports module.py for each active module.

        Uses module.py instead of module.json to support Django translations.

        Returns list of menu items sorted by order
        """
        menu_items = []

        if not self.modules_dir.exists():
            return menu_items

        # Scan filesystem for active modules
        for module_dir in self.modules_dir.iterdir():
            if not module_dir.is_dir():
                continue

            # Skip disabled modules (start with _ or .)
            if module_dir.name.startswith('.') or module_dir.name.startswith('_'):
                continue

            module_id = module_dir.name

            # Import module.py to get configuration with translations
            try:
                module_py = importlib.import_module(f"{module_id}.module")

                # Get MENU configuration from module.py
                menu_config = getattr(module_py, 'MENU', {})

                # Get module name (translated via gettext_lazy)
                module_name = getattr(module_py, 'MODULE_NAME', module_id.title())
                module_icon = getattr(module_py, 'MODULE_ICON', 'cube-outline')

                # Check if module has custom SVG icon
                # Django static structure: static/{module_id}/icons/icon.svg
                svg_icon_path = module_dir / 'static' / module_id / 'icons' / 'icon.svg'
                has_svg = svg_icon_path.exists()

                # Build menu item - use str() to evaluate lazy translations
                menu_item = {
                    'module_id': module_id,
                    'label': str(menu_config.get('label', module_name)),
                    'icon': menu_config.get('icon', module_icon),
                    'order': menu_config.get('order', 100),
                    'url': f'/m/{module_id}/',
                    'has_submenu': False,
                    'has_svg': has_svg,
                    'svg_path': f'/static/{module_id}/icons/icon.svg' if has_svg else '',
                }

                # Only add if show is not explicitly False
                if menu_config.get('show', True):
                    menu_items.append(menu_item)

            except ImportError as e:
                # Fallback to module.json if module.py doesn't exist
                module_json_path = module_dir / 'module.json'
                if module_json_path.exists():
                    try:
                        with open(module_json_path, 'r', encoding='utf-8') as f:
                            module_data = json.load(f)
                            menu_config = module_data.get('menu', {})

                        menu_item = {
                            'module_id': module_id,
                            'label': menu_config.get('label', module_id.title()),
                            'icon': menu_config.get('icon', 'cube-outline'),
                            'order': menu_config.get('order', 100),
                            'url': f'/m/{module_id}/',
                            'has_submenu': False,
                        }

                        if menu_config.get('show', True):
                            menu_items.append(menu_item)
                    except Exception as json_error:
                        print(f"[WARNING] Error reading module.json for {module_id}: {json_error}")
                else:
                    print(f"[WARNING] No module.py or module.json found for {module_id}: {e}")

            except Exception as e:
                print(f"[WARNING] Error loading menu config for {module_id}: {e}")

        # Sort by order, then by label
        menu_items.sort(key=lambda x: (x['order'], x['label']))

        return menu_items


# Global module loader instance
module_loader = ModuleLoader()


def get_module_py(module_id: str):
    """
    Import and return the module.py configuration file for a module.

    Args:
        module_id: The module identifier (e.g., 'inventory', 'sections')

    Returns:
        The imported module.py module object, or None if not found

    Usage:
        module_py = get_module_py('inventory')
        navigation = module_py.NAVIGATION  # List of nav items
        module_name = module_py.MODULE_NAME  # Translated name
    """
    try:
        # Try to import {module_id}.module (e.g., inventory.module)
        module_config = importlib.import_module(f"{module_id}.module")
        return module_config
    except ImportError:
        # Fallback: return empty module-like object
        print(f"[WARNING] No module.py found for {module_id}")
        return type('EmptyModule', (), {
            'MODULE_ID': module_id,
            'MODULE_NAME': module_id.title(),
            'NAVIGATION': [],
            'MENU': {},
        })()


def get_module_navigation(module_id: str) -> list:
    """
    Get navigation items for a module with URLs resolved.

    Args:
        module_id: The module identifier

    Returns:
        List of navigation items with 'url' field populated
    """
    module_py = get_module_py(module_id)
    navigation = getattr(module_py, 'NAVIGATION', [])

    # Build navigation with resolved URLs
    nav_items = []
    for nav in navigation:
        item = dict(nav)  # Copy to avoid modifying original
        # Generate URL from view name
        view_name = item.get('view', item.get('id', ''))
        item['url'] = f"/m/{module_id}/{view_name}/" if view_name else f"/m/{module_id}/"
        # Convert lazy strings to str for JSON serialization
        if hasattr(item.get('label'), '__str__'):
            item['label'] = str(item['label'])
        nav_items.append(item)

    return nav_items
