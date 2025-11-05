"""
Plugin Runtime Manager for CPOS Hub
Handles plugin installation, dependency management, and lifecycle in PyInstaller environment
"""
import os
import sys
import json
import shutil
import zipfile
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional, List
from django.conf import settings
from django.core.management import call_command


class PluginRuntimeManager:
    """
    Manages plugin installation and dependencies in the Hub runtime environment.
    Designed to work in PyInstaller bundled apps across Windows, macOS, and Linux.
    """

    def __init__(self):
        self.plugins_dir = Path(settings.BASE_DIR) / 'plugins'
        self.plugins_dir.mkdir(exist_ok=True)

    def install_plugin_from_zip(self, zip_path: str) -> Dict:
        """
        Install a plugin from a ZIP file.

        Steps:
        1. Extract ZIP to plugins directory
        2. Read plugin.json metadata
        3. Install Python dependencies from requirements.txt
        4. Run migrations
        5. Compile translations
        6. Register plugin in database

        Returns:
            Dict with installation result and messages
        """
        result = {
            'success': False,
            'plugin_id': None,
            'messages': [],
            'errors': []
        }

        try:
            # Step 1: Extract ZIP
            result['messages'].append('Extracting plugin ZIP...')
            plugin_data = self._extract_plugin(zip_path)

            if not plugin_data:
                result['errors'].append('Failed to extract plugin or read plugin.json')
                return result

            plugin_id = plugin_data.get('plugin_id')
            plugin_path = self.plugins_dir / plugin_id
            result['plugin_id'] = plugin_id
            result['messages'].append(f'Plugin extracted: {plugin_id}')

            # Step 1.5: Validate database conflicts
            result['messages'].append('Validating database conflicts...')
            conflict_check = self._validate_database_conflicts(plugin_id, plugin_path)
            result['messages'].extend(conflict_check.get('messages', []))

            if not conflict_check['valid']:
                result['errors'].extend(conflict_check.get('errors', []))
                result['errors'].append('Plugin validation failed - database conflicts detected')
                # Clean up extracted files
                if plugin_path.exists():
                    shutil.rmtree(plugin_path)
                return result

            # Step 2: Install Python dependencies
            result['messages'].append('Installing Python dependencies...')
            deps_result = self._install_python_dependencies(plugin_path)
            result['messages'].extend(deps_result.get('messages', []))

            if not deps_result['success']:
                result['errors'].extend(deps_result.get('errors', []))
                result['errors'].append('Dependency installation failed')
                return result

            # Step 3: Run migrations
            result['messages'].append('Running database migrations...')
            migration_result = self._run_migrations(plugin_id)
            result['messages'].extend(migration_result.get('messages', []))

            if not migration_result['success']:
                result['errors'].extend(migration_result.get('errors', []))
                # Continue even if migrations fail (might not have any)

            # Step 4: Compile translations
            result['messages'].append('Compiling translations...')
            translation_result = self._compile_translations(plugin_path, plugin_id)
            result['messages'].extend(translation_result.get('messages', []))

            # Step 5: Register plugin in database
            result['messages'].append('Registering plugin in database...')
            from apps.core.plugin_loader import plugin_loader
            plugin = plugin_loader.install_plugin_from_metadata(plugin_data)

            if plugin:
                result['success'] = True
                result['messages'].append(f'Plugin {plugin_id} installed successfully!')
            else:
                result['errors'].append('Failed to register plugin in database')

        except Exception as e:
            result['errors'].append(f'Installation error: {str(e)}')

        return result

    def _extract_plugin(self, zip_path: str) -> Optional[Dict]:
        """
        Extract plugin ZIP file to plugins directory.

        Expected ZIP structure:
        cpos-plugin-products.zip
        └── products/
            ├── plugin.json
            ├── models.py
            ├── views.py
            └── ...

        Returns:
            plugin.json data or None if failed
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Get root folder name from ZIP
                zip_contents = zip_ref.namelist()

                # Find plugin.json to determine plugin_id
                plugin_json_path = None
                for file in zip_contents:
                    if file.endswith('plugin.json') and '/' in file:
                        plugin_json_path = file
                        break

                if not plugin_json_path:
                    return None

                # Extract plugin.json to read metadata
                plugin_json_content = zip_ref.read(plugin_json_path)
                plugin_data = json.loads(plugin_json_content)
                plugin_id = plugin_data.get('plugin_id')

                if not plugin_id:
                    return None

                # Extract to plugins/{plugin_id}/
                plugin_dir = self.plugins_dir / plugin_id

                # Remove existing if present
                if plugin_dir.exists():
                    shutil.rmtree(plugin_dir)

                # Extract all files
                for file in zip_contents:
                    # Skip the root folder prefix (e.g., "products/" -> "")
                    if file.startswith(plugin_id + '/'):
                        target_path = self.plugins_dir / file
                        target_path.parent.mkdir(parents=True, exist_ok=True)

                        if not file.endswith('/'):
                            with zip_ref.open(file) as source, open(target_path, 'wb') as target:
                                target.write(source.read())

                # Add install_path to metadata
                plugin_data['install_path'] = str(plugin_dir)

                return plugin_data

        except Exception as e:
            print(f"Error extracting plugin: {e}")
            return None

    def _install_python_dependencies(self, plugin_path: Path) -> Dict:
        """
        Install Python dependencies from requirements.txt using pip.

        Works in PyInstaller environment by detecting the correct pip location.
        """
        result = {
            'success': False,
            'messages': [],
            'errors': []
        }

        requirements_file = plugin_path / 'requirements.txt'

        if not requirements_file.exists():
            result['success'] = True
            result['messages'].append('No requirements.txt found - skipping')
            return result

        try:
            # Get pip command based on environment
            pip_cmd = self._get_pip_command()

            # Build pip install command
            cmd = [
                pip_cmd, 'install',
                '-r', str(requirements_file),
                '--upgrade',
                '--quiet'
            ]

            # Run pip install
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )

            if process.returncode == 0:
                result['success'] = True
                result['messages'].append('Dependencies installed successfully')
            else:
                result['errors'].append(f'pip install failed: {process.stderr}')
                result['success'] = False

        except subprocess.TimeoutExpired:
            result['errors'].append('Dependency installation timeout (>5 minutes)')
        except Exception as e:
            result['errors'].append(f'Error installing dependencies: {str(e)}')

        return result

    def _get_pip_command(self) -> str:
        """
        Get the correct pip command based on OS and PyInstaller environment.

        Returns:
            Path to pip executable
        """
        # Check if running in PyInstaller bundle
        if getattr(sys, 'frozen', False):
            # Running in PyInstaller bundle
            bundle_dir = Path(sys._MEIPASS)

            if sys.platform == 'win32':
                # Windows
                pip_path = bundle_dir / 'Scripts' / 'pip.exe'
                if pip_path.exists():
                    return str(pip_path)
                return 'pip.exe'
            else:
                # macOS / Linux
                pip_path = bundle_dir / 'bin' / 'pip'
                if pip_path.exists():
                    return str(pip_path)
                return 'pip'
        else:
            # Running in normal Python environment
            return f'{sys.executable} -m pip'

    def _run_migrations(self, plugin_id: str) -> Dict:
        """
        Run Django migrations for the plugin.
        """
        result = {
            'success': False,
            'messages': [],
            'errors': []
        }

        try:
            # Run makemigrations first (in case plugin has new migrations)
            call_command('makemigrations', plugin_id, '--noinput')
            result['messages'].append(f'Migrations created for {plugin_id}')

            # Run migrate
            call_command('migrate', plugin_id, '--noinput')
            result['messages'].append(f'Migrations applied for {plugin_id}')
            result['success'] = True

        except Exception as e:
            # Migrations might fail if plugin has no models or migrations
            # This is not critical, so we log but don't fail
            result['messages'].append(f'Migration note: {str(e)}')
            result['success'] = True  # Don't fail installation

        return result

    def _compile_translations(self, plugin_path: Path, plugin_id: str) -> Dict:
        """
        Compile .po translation files to .mo files.
        """
        result = {
            'success': False,
            'messages': [],
            'errors': []
        }

        locale_dir = plugin_path / plugin_id / 'locale'

        if not locale_dir.exists():
            result['success'] = True
            result['messages'].append('No translations found - skipping')
            return result

        try:
            # Compile messages for all locales
            call_command('compilemessages', '--locale=en', '--locale=es')
            result['messages'].append('Translations compiled successfully')
            result['success'] = True

        except Exception as e:
            # Translation compilation is optional
            result['messages'].append(f'Translation note: {str(e)}')
            result['success'] = True  # Don't fail installation

        return result

    def uninstall_plugin(self, plugin_id: str) -> Dict:
        """
        Uninstall a plugin (remove files and database entry).
        """
        result = {
            'success': False,
            'messages': [],
            'errors': []
        }

        try:
            plugin_path = self.plugins_dir / plugin_id

            # Mark as inactive in database
            from apps.core.plugin_loader import plugin_loader
            if plugin_loader.unload_plugin(plugin_id):
                result['messages'].append(f'Plugin {plugin_id} deactivated')

            # Remove plugin files
            if plugin_path.exists():
                shutil.rmtree(plugin_path)
                result['messages'].append(f'Plugin files removed')

            result['success'] = True
            result['messages'].append(f'Plugin {plugin_id} uninstalled successfully')

        except Exception as e:
            result['errors'].append(f'Uninstall error: {str(e)}')

        return result

    def validate_plugin_dependencies(self, plugin_path: Path) -> Dict:
        """
        Validate that plugin dependencies are satisfied before installation.

        Checks:
        - Python version requirements
        - Python package dependencies
        - System dependencies
        - Other plugin dependencies
        """
        result = {
            'valid': True,
            'errors': [],
            'warnings': []
        }

        # Read plugin.json
        plugin_json = plugin_path / 'plugin.json'
        if not plugin_json.exists():
            result['valid'] = False
            result['errors'].append('plugin.json not found')
            return result

        try:
            with open(plugin_json, 'r') as f:
                plugin_data = json.load(f)
        except Exception as e:
            result['valid'] = False
            result['errors'].append(f'Invalid plugin.json: {str(e)}')
            return result

        # Check dependencies
        dependencies = plugin_data.get('dependencies', {})

        # Python packages (we'll install these, so just validate format)
        python_deps = dependencies.get('python', [])
        for dep in python_deps:
            if not dep or not isinstance(dep, str):
                result['warnings'].append(f'Invalid Python dependency format: {dep}')

        # Plugin dependencies
        plugin_deps = dependencies.get('plugins', [])
        for dep in plugin_deps:
            # Check if required plugin is installed
            dep_id = dep.split('>=')[0].replace('cpos-plugin-', '')
            dep_path = self.plugins_dir / dep_id

            if not dep_path.exists():
                result['valid'] = False
                result['errors'].append(f'Required plugin not installed: {dep_id}')

        return result

    def _validate_database_conflicts(self, plugin_id: str, plugin_path: Path) -> Dict:
        """
        Validate that plugin models won't conflict with existing database tables.

        This prevents two plugins from creating the same table, which would cause
        migration errors and data conflicts.

        Checks:
        1. Table name conflicts (db_table in Meta)
        2. App label conflicts (app_label in Meta)
        3. Model name conflicts in same app
        """
        result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'messages': []
        }

        try:
            from django.db import connection
            from django.apps import apps

            # Get all existing tables in database
            with connection.cursor() as cursor:
                existing_tables = set(connection.introspection.table_names(cursor))

            result['messages'].append(f'Found {len(existing_tables)} existing tables in database')

            # Get all registered app labels
            existing_app_labels = set(app.label for app in apps.get_app_configs())

            # Check if plugin_id conflicts with existing app label
            if plugin_id in existing_app_labels:
                result['valid'] = False
                result['errors'].append(
                    f"Plugin ID '{plugin_id}' conflicts with existing Django app. "
                    f"This plugin may already be installed or conflicts with a core app."
                )

            # Parse models.py to detect potential table names
            models_file = plugin_path / plugin_id / 'models.py'

            if models_file.exists():
                result['messages'].append('Analyzing models.py for table conflicts...')

                with open(models_file, 'r') as f:
                    content = f.read()

                # Simple regex to find model classes
                import re

                # Find all Model class definitions
                model_pattern = r'class\s+(\w+)\s*\([^)]*Model[^)]*\):'
                models_found = re.findall(model_pattern, content)

                result['messages'].append(f'Found {len(models_found)} model(s): {", ".join(models_found)}')

                # Check for explicit db_table definitions
                db_table_pattern = r'db_table\s*=\s*[\'"]([^\'"]+)[\'"]'
                explicit_tables = re.findall(db_table_pattern, content)

                if explicit_tables:
                    result['messages'].append(f'Explicit db_table definitions: {", ".join(explicit_tables)}')

                    for table_name in explicit_tables:
                        if table_name in existing_tables:
                            result['valid'] = False
                            result['errors'].append(
                                f"Table '{table_name}' already exists in database. "
                                f"This plugin conflicts with an existing plugin or app."
                            )

                # Check default table names (app_label_modelname)
                for model_name in models_found:
                    # Skip abstract models and non-table models
                    if 'Abstract' in model_name or model_name.startswith('_'):
                        continue

                    # Default Django table name format
                    default_table_name = f"{plugin_id}_{model_name.lower()}"

                    # Only check if not explicitly defined
                    if default_table_name not in explicit_tables:
                        if default_table_name in existing_tables:
                            result['valid'] = False
                            result['errors'].append(
                                f"Table '{default_table_name}' (from model '{model_name}') already exists. "
                                f"Plugin conflicts with existing data."
                            )

            else:
                result['messages'].append('No models.py found - skipping table validation')

            # Check migrations directory for CreateModel operations
            migrations_dir = plugin_path / plugin_id / 'migrations'

            if migrations_dir.exists():
                result['messages'].append('Checking migration files...')

                migration_files = list(migrations_dir.glob('*.py'))
                migration_files = [f for f in migration_files if f.name != '__init__.py']

                result['messages'].append(f'Found {len(migration_files)} migration file(s)')

                for migration_file in migration_files:
                    with open(migration_file, 'r') as f:
                        migration_content = f.read()

                    # Look for CreateModel operations
                    create_model_pattern = r'migrations\.CreateModel\s*\(\s*name\s*=\s*[\'"](\w+)[\'"]'
                    models_in_migration = re.findall(create_model_pattern, migration_content)

                    for model_name in models_in_migration:
                        # Check for db_table in options
                        options_pattern = rf'name\s*=\s*[\'"]{model_name}[\'"].*?options\s*=\s*\{{[^}}]*[\'"]db_table[\'"]\s*:\s*[\'"]([^\'"]+)[\'"]'
                        table_match = re.search(options_pattern, migration_content, re.DOTALL)

                        if table_match:
                            table_name = table_match.group(1)
                        else:
                            table_name = f"{plugin_id}_{model_name.lower()}"

                        if table_name in existing_tables:
                            result['valid'] = False
                            result['errors'].append(
                                f"Migration creates table '{table_name}' which already exists"
                            )

            if result['valid']:
                result['messages'].append('No database conflicts detected')

        except Exception as e:
            result['warnings'].append(f'Could not validate database conflicts: {str(e)}')
            # Don't fail installation on validation errors, just warn
            result['messages'].append('Skipping database conflict validation due to error')

        return result


# Global instance
plugin_runtime_manager = PluginRuntimeManager()
