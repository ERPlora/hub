"""
Module Runtime Manager for ERPlora Hub
Handles module installation, dependency management, and lifecycle.
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


class ModuleRuntimeManager:
    """
    Manages module installation and dependencies in the Hub runtime environment.
    """

    def __init__(self):
        self.modules_dir = Path(settings.BASE_DIR) / 'modules'
        self.modules_dir.mkdir(exist_ok=True)

        # Create temp directory for module uploads
        self.temp_dir = Path(tempfile.gettempdir()) / 'cpos_hub_modules'
        self.temp_dir.mkdir(exist_ok=True)

    def install_module_from_zip(self, zip_path: str) -> Dict:
        """
        Install a module from a ZIP file.

        Steps:
        1. Extract ZIP to modules directory
        2. Read module.json metadata
        3. Install Python dependencies from requirements.txt
        4. Run migrations
        5. Compile translations
        6. Register module in database

        Returns:
            Dict with installation result and messages
        """
        result = {
            'success': False,
            'module_id': None,
            'messages': [],
            'errors': []
        }

        zip_path_obj = None
        try:
            # Step 1: Extract ZIP
            result['messages'].append('Extracting module ZIP...')
            module_data = self._extract_module(zip_path)

            if not module_data:
                result['errors'].append('Failed to extract module or read module.json')
                return result

            module_id = module_data.get('module_id')
            module_path = self.modules_dir / module_id
            result['module_id'] = module_id
            result['messages'].append(f'Module extracted: {module_id}')

            # Delete ZIP file immediately after extraction
            zip_path_obj = Path(zip_path)
            if zip_path_obj.exists():
                zip_path_obj.unlink()
                result['messages'].append('Cleaned up temporary ZIP file')

            # Step 1.5: Validate database conflicts
            result['messages'].append('Validating database conflicts...')
            conflict_check = self._validate_database_conflicts(module_id, module_path)
            result['messages'].extend(conflict_check.get('messages', []))

            if not conflict_check['valid']:
                result['errors'].extend(conflict_check.get('errors', []))
                result['errors'].append('Module validation failed - database conflicts detected')
                # Clean up extracted files
                if module_path.exists():
                    shutil.rmtree(module_path)
                return result

            # Step 2: Install Python dependencies
            result['messages'].append('Installing Python dependencies...')
            deps_result = self._install_python_dependencies(module_path)
            result['messages'].extend(deps_result.get('messages', []))

            if not deps_result['success']:
                result['errors'].extend(deps_result.get('errors', []))
                result['errors'].append('Dependency installation failed')
                return result

            # Step 3: Run migrations
            result['messages'].append('Running database migrations...')
            migration_result = self._run_migrations(module_id)
            result['messages'].extend(migration_result.get('messages', []))

            if not migration_result['success']:
                result['errors'].extend(migration_result.get('errors', []))
                # Continue even if migrations fail (might not have any)

            # Step 4: Compile translations
            result['messages'].append('Compiling translations...')
            translation_result = self._compile_translations(module_path, module_id)
            result['messages'].extend(translation_result.get('messages', []))

            # Step 5: Register module in database
            result['messages'].append('Registering module in database...')
            from apps.modules_runtime.loader import module_loader
            module = module_loader.install_module_from_metadata(module_data)

            if module:
                result['success'] = True
                result['messages'].append(f'Module {module_id} installed successfully!')
            else:
                result['errors'].append('Failed to register module in database')

        except Exception as e:
            result['errors'].append(f'Installation error: {str(e)}')

        return result

    def _extract_module(self, zip_path: str) -> Optional[Dict]:
        """
        Extract module ZIP file to modules directory.

        Expected ZIP structure:
        cpos-module-products.zip
        └── products/
            ├── module.json
            ├── models.py
            ├── views.py
            └── ...

        Returns:
            module.json data or None if failed
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Get root folder name from ZIP
                zip_contents = zip_ref.namelist()

                # Find module.json to determine module_id
                module_json_path = None
                for file in zip_contents:
                    if file.endswith('module.json') and '/' in file:
                        module_json_path = file
                        break

                if not module_json_path:
                    return None

                # Extract module.json to read metadata
                module_json_content = zip_ref.read(module_json_path)
                module_data = json.loads(module_json_content)
                module_id = module_data.get('module_id')

                if not module_id:
                    return None

                # Extract to modules/{module_id}/
                module_dir = self.modules_dir / module_id

                # Remove existing if present
                if module_dir.exists():
                    shutil.rmtree(module_dir)

                # Extract all files
                for file in zip_contents:
                    # Skip the root folder prefix (e.g., "products/" -> "")
                    if file.startswith(module_id + '/'):
                        target_path = self.modules_dir / file
                        target_path.parent.mkdir(parents=True, exist_ok=True)

                        if not file.endswith('/'):
                            with zip_ref.open(file) as source, open(target_path, 'wb') as target:
                                target.write(source.read())

                # Add install_path to metadata
                module_data['install_path'] = str(module_dir)

                return module_data

        except Exception as e:
            print(f"Error extracting module: {e}")
            return None

    def _install_python_dependencies(self, module_path: Path) -> Dict:
        """
        Install Python dependencies from requirements.txt using pip.
        """
        result = {
            'success': False,
            'messages': [],
            'errors': []
        }

        requirements_file = module_path / 'requirements.txt'

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
        Get the correct pip command for the current Python environment.

        Returns:
            pip command string
        """
        return f'{sys.executable} -m pip'

    def _run_migrations(self, module_id: str) -> Dict:
        """
        Run Django migrations for the module.
        """
        result = {
            'success': False,
            'messages': [],
            'errors': []
        }

        try:
            # Run makemigrations first (in case module has new migrations)
            call_command('makemigrations', module_id, '--noinput')
            result['messages'].append(f'Migrations created for {module_id}')

            # Run migrate
            call_command('migrate', module_id, '--noinput')
            result['messages'].append(f'Migrations applied for {module_id}')
            result['success'] = True

        except Exception as e:
            # Migrations might fail if module has no models or migrations
            # This is not critical, so we log but don't fail
            result['messages'].append(f'Migration note: {str(e)}')
            result['success'] = True  # Don't fail installation

        return result

    def _compile_translations(self, module_path: Path, module_id: str) -> Dict:
        """
        Compile .po translation files to .mo files.
        """
        result = {
            'success': False,
            'messages': [],
            'errors': []
        }

        locale_dir = module_path / module_id / 'locale'

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

    def uninstall_module(self, module_id: str) -> Dict:
        """
        Uninstall a module (remove files and database entry).
        """
        result = {
            'success': False,
            'messages': [],
            'errors': []
        }

        try:
            module_path = self.modules_dir / module_id

            # Mark as inactive in database
            from apps.modules_runtime.loader import module_loader
            if module_loader.unload_module(module_id):
                result['messages'].append(f'Module {module_id} deactivated')

            # Remove module files
            if module_path.exists():
                shutil.rmtree(module_path)
                result['messages'].append(f'Module files removed')

            result['success'] = True
            result['messages'].append(f'Module {module_id} uninstalled successfully')

        except Exception as e:
            result['errors'].append(f'Uninstall error: {str(e)}')

        return result

    def validate_module_dependencies(self, module_path: Path) -> Dict:
        """
        Validate that module dependencies are satisfied before installation.

        Checks:
        - Python version requirements
        - Python package dependencies
        - System dependencies
        - Other module dependencies
        """
        result = {
            'valid': True,
            'errors': [],
            'warnings': []
        }

        # Read module.json
        module_json = module_path / 'module.json'
        if not module_json.exists():
            result['valid'] = False
            result['errors'].append('module.json not found')
            return result

        try:
            with open(module_json, 'r') as f:
                module_data = json.load(f)
        except Exception as e:
            result['valid'] = False
            result['errors'].append(f'Invalid module.json: {str(e)}')
            return result

        # Check dependencies
        dependencies = module_data.get('dependencies', {})

        # Python packages (we'll install these, so just validate format)
        python_deps = dependencies.get('python', [])
        for dep in python_deps:
            if not dep or not isinstance(dep, str):
                result['warnings'].append(f'Invalid Python dependency format: {dep}')

        # Module dependencies
        module_deps = dependencies.get('modules', [])
        for dep in module_deps:
            # Check if required module is installed
            dep_id = dep.split('>=')[0].replace('cpos-module-', '')
            dep_path = self.modules_dir / dep_id

            if not dep_path.exists():
                result['valid'] = False
                result['errors'].append(f'Required module not installed: {dep_id}')

        return result

    def _validate_database_conflicts(self, module_id: str, module_path: Path) -> Dict:
        """
        Validate that module models won't conflict with existing database tables.

        This prevents two modules from creating the same table, which would cause
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

            # Check if module_id conflicts with existing app label
            if module_id in existing_app_labels:
                result['valid'] = False
                result['errors'].append(
                    f"Module ID '{module_id}' conflicts with existing Django app. "
                    f"This module may already be installed or conflicts with a core app."
                )

            # Parse models.py to detect potential table names
            models_file = module_path / module_id / 'models.py'

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
                                f"This module conflicts with an existing module or app."
                            )

                # Check default table names (app_label_modelname)
                for model_name in models_found:
                    # Skip abstract models and non-table models
                    if 'Abstract' in model_name or model_name.startswith('_'):
                        continue

                    # Default Django table name format
                    default_table_name = f"{module_id}_{model_name.lower()}"

                    # Only check if not explicitly defined
                    if default_table_name not in explicit_tables:
                        if default_table_name in existing_tables:
                            result['valid'] = False
                            result['errors'].append(
                                f"Table '{default_table_name}' (from model '{model_name}') already exists. "
                                f"Module conflicts with existing data."
                            )

            else:
                result['messages'].append('No models.py found - skipping table validation')

            # Check migrations directory for CreateModel operations
            migrations_dir = module_path / module_id / 'migrations'

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
                            table_name = f"{module_id}_{model_name.lower()}"

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

    def get_temp_file_path(self, filename: str) -> Path:
        """
        Get a temporary file path for module operations.

        Args:
            filename: Name of the temporary file

        Returns:
            Path object pointing to temp file location
        """
        return self.temp_dir / filename


# Global instance
module_runtime_manager = ModuleRuntimeManager()
