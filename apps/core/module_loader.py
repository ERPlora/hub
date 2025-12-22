"""
Module Loader for ERPlora Hub
Dynamically loads and manages modules from filesystem.

Modules are stored in:
- Development: ./modules/ (project directory)
- Production: Platform-specific external directory

Module naming convention:
- Active modules: module_name/ (no prefix)
- Inactive modules: _module_name/ (underscore prefix)

This loader discovers ALL modules (active and inactive) and reports their status.
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


class ModuleLoader:
    """
    Loads and manages modules dynamically from filesystem.

    Modules are Django apps stored in the modules directory.
    - Active modules: directory name without underscore prefix
    - Inactive modules: directory name starts with underscore (_)
    """

    def __init__(self):
        # Use modules directory from settings
        self.modules_dir = Path(settings.MODULES_DIR)
        self.loaded_modules = {}

        # Ensure modules directory exists
        self.modules_dir.mkdir(parents=True, exist_ok=True)

        # Add modules directory to Python path for dynamic imports
        if str(self.modules_dir) not in sys.path:
            sys.path.insert(0, str(self.modules_dir))

        print(f"[INFO] Module loader initialized")
        print(f"[INFO] Modules directory: {self.modules_dir}")

    def discover_modules(self, include_inactive: bool = True) -> List[Dict]:
        """
        Discover all modules in the modules directory.

        Args:
            include_inactive: If True, include modules with _ prefix (inactive)

        Returns:
            List of module metadata dictionaries
        """
        discovered = []

        if not self.modules_dir.exists():
            return discovered

        # Iterate through module directories
        for module_dir in self.modules_dir.iterdir():
            if not module_dir.is_dir():
                continue

            # Skip hidden directories (start with .)
            if module_dir.name.startswith('.'):
                continue

            # Determine if module is active based on underscore prefix
            is_active = not module_dir.name.startswith('_')

            # Skip inactive modules if not requested
            if not include_inactive and not is_active:
                continue

            # Get the actual module name (without underscore prefix)
            module_name = module_dir.name.lstrip('_')

            # Check for module.json
            module_json = module_dir / 'module.json'
            if not module_json.exists():
                # Create basic metadata for modules without module.json
                metadata = {
                    'module_id': module_name,
                    'name': module_name.replace('_', ' ').title(),
                    'description': '',
                    'version': '1.0.0',
                    'author': '',
                    'icon': 'cube-outline',
                    'category': 'general',
                    'install_path': str(module_dir),
                    'dir_name': module_dir.name,
                    'is_active': is_active,
                }
                discovered.append(metadata)
                continue

            try:
                with open(module_json, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    metadata['install_path'] = str(module_dir)
                    metadata['dir_name'] = module_dir.name
                    metadata['is_active'] = is_active
                    # Ensure module_id matches directory name
                    if 'module_id' not in metadata:
                        metadata['module_id'] = module_name
                    # Get icon from root or menu.icon, fallback to default
                    if 'icon' not in metadata:
                        menu_config = metadata.get('menu', {})
                        metadata['icon'] = menu_config.get('icon', 'cube-outline')
                    discovered.append(metadata)
            except (json.JSONDecodeError, Exception) as e:
                print(f"[WARNING] Error loading module {module_dir.name}: {e}")
                # Still include it with basic metadata
                metadata = {
                    'module_id': module_name,
                    'name': module_name.replace('_', ' ').title(),
                    'description': f'Error loading: {e}',
                    'version': '1.0.0',
                    'author': '',
                    'icon': 'alert-circle-outline',
                    'category': 'general',
                    'install_path': str(module_dir),
                    'dir_name': module_dir.name,
                    'is_active': is_active,
                    'has_error': True,
                }
                discovered.append(metadata)

        return discovered

    def get_active_modules(self) -> List[Dict]:
        """Get only active modules (without underscore prefix)."""
        return self.discover_modules(include_inactive=False)

    def activate_module(self, module_id: str) -> Dict:
        """
        Activate a module by removing underscore prefix from directory name.

        Args:
            module_id: The module identifier

        Returns:
            Dict with success status and message
        """
        # Find the module directory (with underscore prefix)
        inactive_dir = self.modules_dir / f'_{module_id}'
        active_dir = self.modules_dir / module_id

        if active_dir.exists():
            return {'success': True, 'message': 'Module already active'}

        if not inactive_dir.exists():
            return {'success': False, 'error': f'Module {module_id} not found'}

        try:
            # Rename directory to remove underscore prefix
            inactive_dir.rename(active_dir)
            return {
                'success': True,
                'message': f'Module {module_id} activated. Restart required to load.',
                'requires_restart': True
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def deactivate_module(self, module_id: str) -> Dict:
        """
        Deactivate a module by adding underscore prefix to directory name.

        Args:
            module_id: The module identifier

        Returns:
            Dict with success status and message
        """
        active_dir = self.modules_dir / module_id
        inactive_dir = self.modules_dir / f'_{module_id}'

        if inactive_dir.exists():
            return {'success': True, 'message': 'Module already inactive'}

        if not active_dir.exists():
            return {'success': False, 'error': f'Module {module_id} not found'}

        try:
            # Remove from loaded modules
            if module_id in self.loaded_modules:
                del self.loaded_modules[module_id]

            # Rename directory to add underscore prefix
            active_dir.rename(inactive_dir)
            return {
                'success': True,
                'message': f'Module {module_id} deactivated. Restart required.',
                'requires_restart': True
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def delete_module(self, module_id: str) -> Dict:
        """
        Delete a module completely from filesystem.

        Args:
            module_id: The module identifier

        Returns:
            Dict with success status and message
        """
        # Try both active and inactive directories
        active_dir = self.modules_dir / module_id
        inactive_dir = self.modules_dir / f'_{module_id}'

        module_dir = None
        if active_dir.exists():
            module_dir = active_dir
        elif inactive_dir.exists():
            module_dir = inactive_dir
        else:
            return {'success': False, 'error': f'Module {module_id} not found'}

        try:
            # Remove from loaded modules
            if module_id in self.loaded_modules:
                del self.loaded_modules[module_id]

            # Delete directory
            shutil.rmtree(module_dir)
            return {'success': True, 'message': f'Module {module_id} deleted'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def load_module(self, module_id: str) -> bool:
        """
        Load a module into Django runtime.

        Args:
            module_id: The module identifier (directory name without underscore)

        Returns:
            True if successful
        """
        module_path = self.modules_dir / module_id

        if not module_path.exists():
            print(f"[ERROR] Module directory not found: {module_path}")
            return False

        # Check if already loaded
        if module_id in self.loaded_modules:
            print(f"[INFO] Module {module_id} already loaded")
            return True

        try:
            # Import the module
            print(f"[INFO] Importing module: {module_id}")
            module_obj = importlib.import_module(module_id)

            # Add to Django INSTALLED_APPS if not already there
            if module_id not in settings.INSTALLED_APPS:
                settings.INSTALLED_APPS = list(settings.INSTALLED_APPS) + [module_id]
                print(f"[OK] Added {module_id} to INSTALLED_APPS")

            # Store in loaded modules
            self.loaded_modules[module_id] = {
                'module': module_obj,
                'path': str(module_path),
            }

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
        Load all active modules (those without underscore prefix).

        Returns:
            Count of successfully loaded modules
        """
        active_modules = self.get_active_modules()
        loaded_count = 0

        for module_meta in active_modules:
            module_id = module_meta.get('module_id')
            if module_id and self.load_module(module_id):
                loaded_count += 1

        return loaded_count

    def get_menu_items(self) -> List[Dict]:
        """
        Get menu items for active modules.

        Returns:
            List of menu items sorted by order
        """
        menu_items = []
        active_modules = self.get_active_modules()

        for module in active_modules:
            menu_config = module.get('menu', {})
            if menu_config:
                menu_items.append({
                    'module_id': module.get('module_id'),
                    'label': menu_config.get('label', module.get('name', '')),
                    'icon': menu_config.get('icon', module.get('icon', 'cube-outline')),
                    'url': menu_config.get('url', f"/modules/{module.get('module_id')}/"),
                    'order': menu_config.get('order', 100),
                })

        # Sort by order
        menu_items.sort(key=lambda x: x.get('order', 100))
        return menu_items


# Global module loader instance
module_loader = ModuleLoader()
