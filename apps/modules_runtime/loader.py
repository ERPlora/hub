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
        Get all active module menu items directly from filesystem.
        Scans modules directory and reads module.json for each active module.

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
            module_json_path = module_dir / 'module.json'

            # Read module.json if exists
            menu_config = {}
            if module_json_path.exists():
                try:
                    with open(module_json_path, 'r', encoding='utf-8') as f:
                        module_data = json.load(f)
                        menu_config = module_data.get('menu', {})
                except Exception as e:
                    print(f"[WARNING] Error reading module.json for {module_id}: {e}")

            # Build menu item
            menu_item = {
                'module_id': module_id,
                'label': menu_config.get('label', module_id.title()),
                'icon': menu_config.get('icon', 'cube-outline'),
                'order': menu_config.get('order', 100),
            }

            # Check if module has submenu items
            menu_items_config = menu_config.get('items', [])
            if menu_items_config:
                # Override URLs in submenu items to use /m/ prefix
                fixed_items = []
                for subitem in menu_items_config:
                    fixed_item = subitem.copy()
                    # Always use /m/ prefix, ignore module.json URL
                    if 'url' in fixed_item:
                        # Extract path after /modules/ or use as-is
                        url = fixed_item['url']
                        if url.startswith(f'/modules/{module_id}'):
                            url = url.replace(f'/modules/{module_id}', f'/m/{module_id}')
                        elif not url.startswith(f'/m/{module_id}'):
                            # Relative or other URL, prefix with /m/{module_id}
                            url = f'/m/{module_id}/' if url == '/' else f'/m/{module_id}{url}'
                        fixed_item['url'] = url
                    fixed_items.append(fixed_item)
                menu_item['items'] = fixed_items
                menu_item['has_submenu'] = True
            else:
                # Single menu item, always use /m/ prefix
                menu_item['url'] = f'/m/{module_id}/'
                menu_item['has_submenu'] = False

            # Only add if show_in_menu is not explicitly False
            if menu_config.get('show', True):
                menu_items.append(menu_item)

        # Sort by order, then by label
        menu_items.sort(key=lambda x: (x['order'], x['label']))

        return menu_items


# Global module loader instance
module_loader = ModuleLoader()
