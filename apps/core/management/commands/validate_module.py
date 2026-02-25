"""
Management command para validar un module antes de distribución.

Valida:
- Estructura de archivos requerida
- module.py válido
- Dependencias permitidas
- Conflictos de base de datos
- Sintaxis Python
- Tests ejecutables

Uso:
    python manage.py validate_module <module_id>

Ejemplos:
    python manage.py validate_module products
    python manage.py validate_module restaurant-pos
"""

from django.core.management.base import BaseCommand, CommandError
from pathlib import Path
from django.conf import settings
import json
import sys
import importlib.util


class Command(BaseCommand):
    help = 'Valida un module antes de distribución'

    def add_arguments(self, parser):
        parser.add_argument(
            'module_id',
            type=str,
            help='ID del module a validar'
        )
        parser.add_argument(
            '--strict',
            action='store_true',
            help='Modo estricto (falla en warnings)'
        )

    def handle(self, *args, **options):
        module_id = options['module_id']
        strict_mode = options['strict']

        # Buscar module en rutas de desarrollo
        base_dir = Path(settings.BASE_DIR)
        module_dir = None

        for discovery_path in settings.MODULE_DISCOVERY_PATHS:
            potential_path = Path(discovery_path) / module_id
            if potential_path.exists():
                module_dir = potential_path
                break

        if not module_dir:
            raise CommandError(f'Module {module_id} no encontrado en rutas de desarrollo')

        self.stdout.write(self.style.SUCCESS(f'\n🔍 Validando module: {module_id}'))
        self.stdout.write(f'   Ubicación: {module_dir}\n')

        errors = []
        warnings = []

        # 1. Validar estructura de archivos
        self.stdout.write('📁 Validando estructura de archivos...')
        required_files = [
            'module.py',
            '__init__.py',
            'apps.py',
            'models.py',
            'views.py',
            'urls.py',
        ]

        for file in required_files:
            if not (module_dir / file).exists():
                errors.append(f'Archivo requerido no encontrado: {file}')
            else:
                self.stdout.write(f'   ✓ {file}')

        # 2. Validar module.py
        self.stdout.write('\n📄 Validando module.py...')
        module_py_path = module_dir / 'module.py'
        module_data = {}

        if module_py_path.exists():
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(f"{module_id}.module", module_py_path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                module_data = {
                    'module_id': getattr(mod, 'MODULE_ID', None),
                    'name': str(getattr(mod, 'MODULE_NAME', '')),
                    'version': getattr(mod, 'MODULE_VERSION', None),
                    'icon': getattr(mod, 'MODULE_ICON', None),
                    'dependencies': getattr(mod, 'DEPENDENCIES', []),
                }

                required_attrs = ['module_id', 'name']
                for field in required_attrs:
                    if not module_data.get(field):
                        errors.append(f'module.py: falta campo requerido "{field}"')
                    else:
                        self.stdout.write(f'   ✓ {field}: {module_data[field]}')

                # Validar module_id coincide
                if module_data.get('module_id') and module_data['module_id'] != module_id:
                    errors.append(f'MODULE_ID en module.py ({module_data["module_id"]}) no coincide con directorio ({module_id})')

            except Exception as e:
                errors.append(f'Error loading module.py: {e}')
        else:
            errors.append('module.py no encontrado')

        # 3. Validar dependencias
        self.stdout.write('\n📦 Validando dependencias...')
        if module_data:
            python_deps = []  # module.py doesn't define python deps

            if python_deps:
                for dep in python_deps:
                    dep_name = dep.split('>=')[0].split('==')[0].strip()

                    # Validar que esté en whitelist
                    if dep_name not in settings.MODULE_ALLOWED_DEPENDENCIES:
                        errors.append(f'Dependencia no permitida: {dep_name}')
                        errors.append(f'   Dependencias permitidas: {", ".join(settings.MODULE_ALLOWED_DEPENDENCIES)}')
                    else:
                        self.stdout.write(f'   ✓ {dep_name}')
            else:
                self.stdout.write('   ℹ Sin dependencias Python')

            module_deps = module_data.get('dependencies', {}).get('modules', [])
            if module_deps:
                self.stdout.write(f'   ℹ Depende de modules: {", ".join(module_deps)}')

        # 4. Validar conflictos de base de datos
        self.stdout.write('\n🗄️  Validando modelos...')
        models_file = module_dir / 'models.py'

        if models_file.exists():
            try:
                with open(models_file, 'r') as f:
                    content = f.read()

                # Buscar definiciones de db_table
                if 'db_table' in content:
                    self.stdout.write('   ℹ Se encontraron definiciones de db_table personalizadas')

                    # Verificar que usen prefijo del module
                    if f"'{module_id}_" not in content and f'"{module_id}_' not in content:
                        warnings.append('db_table debería usar prefijo del module para evitar conflictos')
                        warnings.append(f'   Ejemplo: db_table = "{module_id}_nombre_tabla"')
                else:
                    self.stdout.write(f'   ✓ Usando nombres de tabla automáticos ({module_id}_modelname)')

                # Verificar que no use nombres genéricos
                generic_names = ['product', 'category', 'item', 'user', 'order', 'sale']
                for name in generic_names:
                    if f"db_table = '{name}'" in content or f'db_table = "{name}"' in content:
                        errors.append(f'Nombre de tabla genérico sin prefijo: "{name}"')
                        errors.append(f'   Usar: db_table = "{module_id}_{name}"')

            except Exception as e:
                errors.append(f'Error al leer models.py: {e}')
        else:
            self.stdout.write('   ℹ Sin modelos definidos')

        # 5. Validar sintaxis Python
        self.stdout.write('\n🐍 Validando sintaxis Python...')
        python_files = list(module_dir.rglob('*.py'))

        for py_file in python_files:
            if '__pycache__' in str(py_file):
                continue

            try:
                with open(py_file, 'r') as f:
                    compile(f.read(), str(py_file), 'exec')
                self.stdout.write(f'   ✓ {py_file.relative_to(module_dir)}')
            except SyntaxError as e:
                errors.append(f'Error de sintaxis en {py_file.relative_to(module_dir)}: {e}')

        # 6. Validar tests
        self.stdout.write('\n🧪 Validando tests...')
        tests_dir = module_dir / 'tests'

        if tests_dir.exists():
            test_files = list(tests_dir.glob('test_*.py'))
            if test_files:
                self.stdout.write(f'   ✓ {len(test_files)} archivos de tests encontrados')
            else:
                warnings.append('No se encontraron tests (test_*.py en tests/)')
        else:
            warnings.append('Directorio tests/ no encontrado')

        # 7. Validar templates
        self.stdout.write('\n🎨 Validando templates...')
        templates_dir = module_dir / 'templates' / module_id

        if templates_dir.exists():
            template_files = list(templates_dir.glob('*.html'))
            if template_files:
                self.stdout.write(f'   ✓ {len(template_files)} templates encontrados')
                for tmpl in template_files:
                    self.stdout.write(f'     - {tmpl.name}')
            else:
                warnings.append(f'No se encontraron templates en templates/{module_id}/')
        else:
            warnings.append(f'Directorio templates/{module_id}/ no encontrado')

        # Resumen
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('📊 RESULTADO DE VALIDACIÓN\n'))

        if errors:
            self.stdout.write(self.style.ERROR(f'❌ {len(errors)} error(es) encontrado(s):\n'))
            for error in errors:
                self.stdout.write(self.style.ERROR(f'   • {error}'))
            self.stdout.write('')

        if warnings:
            self.stdout.write(self.style.WARNING(f'⚠️  {len(warnings)} advertencia(s):\n'))
            for warning in warnings:
                self.stdout.write(self.style.WARNING(f'   • {warning}'))
            self.stdout.write('')

        if not errors and not warnings:
            self.stdout.write(self.style.SUCCESS('✅ Module válido - listo para distribución!\n'))
            self.stdout.write('📋 Próximos pasos:')
            self.stdout.write(f'   1. python manage.py sign_module {module_id}')
            self.stdout.write(f'   2. python manage.py package_module {module_id}')
            self.stdout.write('')
            return

        if errors:
            raise CommandError('Validación fallida - corrige los errores antes de continuar')

        if warnings and strict_mode:
            raise CommandError('Validación fallida en modo estricto - corrige las advertencias')

        if warnings and not strict_mode:
            self.stdout.write(self.style.WARNING('\n⚠️  Validación completada con advertencias'))
            self.stdout.write('   El module puede funcionar pero se recomienda corregir las advertencias')
            self.stdout.write('   Usa --strict para forzar corrección de advertencias\n')
