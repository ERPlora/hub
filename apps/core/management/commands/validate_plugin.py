"""
Management command para validar un plugin antes de distribución.

Valida:
- Estructura de archivos requerida
- plugin.json válido
- Dependencias permitidas
- Conflictos de base de datos
- Sintaxis Python
- Tests ejecutables

Uso:
    python manage.py validate_plugin <plugin_id>

Ejemplos:
    python manage.py validate_plugin products
    python manage.py validate_plugin restaurant-pos
"""

from django.core.management.base import BaseCommand, CommandError
from pathlib import Path
from django.conf import settings
import json
import sys
import importlib.util


class Command(BaseCommand):
    help = 'Valida un plugin antes de distribución'

    def add_arguments(self, parser):
        parser.add_argument(
            'plugin_id',
            type=str,
            help='ID del plugin a validar'
        )
        parser.add_argument(
            '--strict',
            action='store_true',
            help='Modo estricto (falla en warnings)'
        )

    def handle(self, *args, **options):
        plugin_id = options['plugin_id']
        strict_mode = options['strict']

        # Buscar plugin en rutas de desarrollo
        base_dir = Path(settings.BASE_DIR)
        plugin_dir = None

        for discovery_path in settings.PLUGIN_DISCOVERY_PATHS:
            potential_path = Path(discovery_path) / plugin_id
            if potential_path.exists():
                plugin_dir = potential_path
                break

        if not plugin_dir:
            raise CommandError(f'Plugin {plugin_id} no encontrado en rutas de desarrollo')

        self.stdout.write(self.style.SUCCESS(f'\n🔍 Validando plugin: {plugin_id}'))
        self.stdout.write(f'   Ubicación: {plugin_dir}\n')

        errors = []
        warnings = []

        # 1. Validar estructura de archivos
        self.stdout.write('📁 Validando estructura de archivos...')
        required_files = [
            'plugin.json',
            '__init__.py',
            'apps.py',
            'models.py',
            'views.py',
            'urls.py',
            'README.md'
        ]

        for file in required_files:
            if not (plugin_dir / file).exists():
                errors.append(f'Archivo requerido no encontrado: {file}')
            else:
                self.stdout.write(f'   ✓ {file}')

        # 2. Validar plugin.json
        self.stdout.write('\n📄 Validando plugin.json...')
        plugin_json_path = plugin_dir / 'plugin.json'

        if plugin_json_path.exists():
            try:
                with open(plugin_json_path, 'r') as f:
                    plugin_data = json.load(f)

                # Campos requeridos
                required_fields = ['plugin_id', 'name', 'version', 'description', 'author']
                for field in required_fields:
                    if field not in plugin_data:
                        errors.append(f'plugin.json: falta campo requerido "{field}"')
                    else:
                        self.stdout.write(f'   ✓ {field}: {plugin_data[field]}')

                # Validar plugin_id coincide
                if plugin_data.get('plugin_id') != plugin_id:
                    errors.append(f'plugin_id en plugin.json ({plugin_data.get("plugin_id")}) no coincide con directorio ({plugin_id})')

                # Validar versión
                version = plugin_data.get('version', '')
                if not version or len(version.split('.')) != 3:
                    errors.append('Versión debe tener formato X.Y.Z (ej: 1.0.0)')

            except json.JSONDecodeError as e:
                errors.append(f'plugin.json inválido: {e}')
        else:
            errors.append('plugin.json no encontrado')

        # 3. Validar dependencias
        self.stdout.write('\n📦 Validando dependencias...')
        if plugin_json_path.exists() and 'plugin_data' in locals():
            python_deps = plugin_data.get('dependencies', {}).get('python', [])

            if python_deps:
                for dep in python_deps:
                    dep_name = dep.split('>=')[0].split('==')[0].strip()

                    # Validar que esté en whitelist
                    if dep_name not in settings.PLUGIN_ALLOWED_DEPENDENCIES:
                        errors.append(f'Dependencia no permitida: {dep_name}')
                        errors.append(f'   Dependencias permitidas: {", ".join(settings.PLUGIN_ALLOWED_DEPENDENCIES)}')
                    else:
                        self.stdout.write(f'   ✓ {dep_name}')
            else:
                self.stdout.write('   ℹ Sin dependencias Python')

            plugin_deps = plugin_data.get('dependencies', {}).get('plugins', [])
            if plugin_deps:
                self.stdout.write(f'   ℹ Depende de plugins: {", ".join(plugin_deps)}')

        # 4. Validar conflictos de base de datos
        self.stdout.write('\n🗄️  Validando modelos...')
        models_file = plugin_dir / 'models.py'

        if models_file.exists():
            try:
                with open(models_file, 'r') as f:
                    content = f.read()

                # Buscar definiciones de db_table
                if 'db_table' in content:
                    self.stdout.write('   ℹ Se encontraron definiciones de db_table personalizadas')

                    # Verificar que usen prefijo del plugin
                    if f"'{plugin_id}_" not in content and f'"{plugin_id}_' not in content:
                        warnings.append('db_table debería usar prefijo del plugin para evitar conflictos')
                        warnings.append(f'   Ejemplo: db_table = "{plugin_id}_nombre_tabla"')
                else:
                    self.stdout.write(f'   ✓ Usando nombres de tabla automáticos ({plugin_id}_modelname)')

                # Verificar que no use nombres genéricos
                generic_names = ['product', 'category', 'item', 'user', 'order', 'sale']
                for name in generic_names:
                    if f"db_table = '{name}'" in content or f'db_table = "{name}"' in content:
                        errors.append(f'Nombre de tabla genérico sin prefijo: "{name}"')
                        errors.append(f'   Usar: db_table = "{plugin_id}_{name}"')

            except Exception as e:
                errors.append(f'Error al leer models.py: {e}')
        else:
            self.stdout.write('   ℹ Sin modelos definidos')

        # 5. Validar sintaxis Python
        self.stdout.write('\n🐍 Validando sintaxis Python...')
        python_files = list(plugin_dir.rglob('*.py'))

        for py_file in python_files:
            if '__pycache__' in str(py_file):
                continue

            try:
                with open(py_file, 'r') as f:
                    compile(f.read(), str(py_file), 'exec')
                self.stdout.write(f'   ✓ {py_file.relative_to(plugin_dir)}')
            except SyntaxError as e:
                errors.append(f'Error de sintaxis en {py_file.relative_to(plugin_dir)}: {e}')

        # 6. Validar tests
        self.stdout.write('\n🧪 Validando tests...')
        tests_dir = plugin_dir / 'tests'

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
        templates_dir = plugin_dir / 'templates' / plugin_id

        if templates_dir.exists():
            template_files = list(templates_dir.glob('*.html'))
            if template_files:
                self.stdout.write(f'   ✓ {len(template_files)} templates encontrados')
                for tmpl in template_files:
                    self.stdout.write(f'     - {tmpl.name}')
            else:
                warnings.append(f'No se encontraron templates en templates/{plugin_id}/')
        else:
            warnings.append(f'Directorio templates/{plugin_id}/ no encontrado')

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
            self.stdout.write(self.style.SUCCESS('✅ Plugin válido - listo para distribución!\n'))
            self.stdout.write('📋 Próximos pasos:')
            self.stdout.write(f'   1. python manage.py sign_plugin {plugin_id}')
            self.stdout.write(f'   2. python manage.py package_plugin {plugin_id}')
            self.stdout.write('')
            return

        if errors:
            raise CommandError('Validación fallida - corrige los errores antes de continuar')

        if warnings and strict_mode:
            raise CommandError('Validación fallida en modo estricto - corrige las advertencias')

        if warnings and not strict_mode:
            self.stdout.write(self.style.WARNING('\n⚠️  Validación completada con advertencias'))
            self.stdout.write('   El plugin puede funcionar pero se recomienda corregir las advertencias')
            self.stdout.write('   Usa --strict para forzar corrección de advertencias\n')
