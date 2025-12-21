"""
Management command para empaquetar un module en ZIP para distribución.

Crea un archivo ZIP del module listo para subir al Cloud o distribuir.

Uso:
    python manage.py package_module <module_id> [--output-dir path/]

Ejemplos:
    python manage.py package_module products
    python manage.py package_module restaurant-pos --output-dir ~/Desktop/

Notas:
    - Valida el module antes de empaquetar
    - Incluye .signature si existe
    - Excluye archivos de desarrollo (.git, __pycache__, etc)
    - Genera ZIP: <module_id>-<version>.zip
"""

from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from pathlib import Path
from django.conf import settings
import json
import zipfile
import datetime
from io import StringIO


class Command(BaseCommand):
    help = 'Empaqueta un module en ZIP para distribución'

    def add_arguments(self, parser):
        parser.add_argument(
            'module_id',
            type=str,
            help='ID del module a empaquetar'
        )
        parser.add_argument(
            '--output-dir',
            type=str,
            default=None,
            help='Directorio de salida (por defecto: ~/Downloads/)'
        )
        parser.add_argument(
            '--skip-validation',
            action='store_true',
            help='Omitir validación antes de empaquetar'
        )

    def handle(self, *args, **options):
        module_id = options['module_id']
        output_dir = options['output_dir']
        skip_validation = options['skip_validation']

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

        # Leer module.json
        module_json_path = module_dir / 'module.json'
        if not module_json_path.exists():
            raise CommandError(f'module.json no encontrado en {module_dir}')

        with open(module_json_path, 'r') as f:
            module_data = json.load(f)

        module_version = module_data.get('version', '0.0.0')

        self.stdout.write(self.style.SUCCESS(f'\n📦 Empaquetando module: {module_id}'))
        self.stdout.write(f'   Versión: {module_version}')
        self.stdout.write(f'   Ubicación: {module_dir}\n')

        # 1. Validar module
        if not skip_validation:
            self.stdout.write('🔍 Validando module...')
            try:
                # Capturar output de validate_module
                out = StringIO()
                call_command('validate_module', module_id, stdout=out)
                self.stdout.write(self.style.SUCCESS('   ✓ Module validado\n'))
            except CommandError as e:
                raise CommandError(f'Validación fallida:\n{e}')

        # 2. Verificar firma
        signature_file = module_dir / '.signature'
        if signature_file.exists():
            self.stdout.write(self.style.SUCCESS('🔐 Firma encontrada - se incluirá en el paquete'))
        else:
            if settings.REQUIRE_MODULE_SIGNATURE:
                raise CommandError(
                    'Module sin firma digital.\n'
                    f'   Ejecuta: python manage.py sign_module {module_id}'
                )
            else:
                self.stdout.write(self.style.WARNING('⚠️  Module sin firma (OK en desarrollo)\n'))

        # 3. Determinar directorio de salida
        if output_dir:
            out_path = Path(output_dir)
        else:
            out_path = Path.home() / 'Downloads'

        out_path.mkdir(parents=True, exist_ok=True)

        # Nombre del ZIP: module-id-version.zip
        zip_filename = f'{module_id}-{module_version}.zip'
        zip_path = out_path / zip_filename

        # 4. Crear ZIP
        self.stdout.write(f'📦 Creando paquete: {zip_filename}...')

        # Patrones a excluir
        exclude_patterns = [
            '__pycache__',
            '.pyc',
            '.pyo',
            '.git',
            '.gitignore',
            '.DS_Store',
            'Thumbs.db',
            '.vscode',
            '.idea',
            '*.swp',
            '*.swo',
            '*~',
            '.pytest_cache',
            '.coverage',
            'htmlcov',
            '*.log',
            'db.sqlite3',
        ]

        files_added = []

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in module_dir.rglob('*'):
                if file_path.is_file():
                    # Verificar si debe excluirse
                    should_exclude = False
                    for pattern in exclude_patterns:
                        if pattern in str(file_path):
                            should_exclude = True
                            break

                    if should_exclude:
                        continue

                    # Agregar al ZIP
                    rel_path = file_path.relative_to(module_dir)
                    arcname = f'{module_id}/{rel_path}'
                    zipf.write(file_path, arcname)
                    files_added.append(str(rel_path))

            # Actualizar timestamp en .signature si existe
            if signature_file.exists():
                with open(signature_file, 'r') as f:
                    sig_data = json.load(f)

                sig_data['signed_at'] = datetime.datetime.utcnow().isoformat() + 'Z'

                # Escribir al ZIP
                zipf.writestr(
                    f'{module_id}/.signature',
                    json.dumps(sig_data, indent=2)
                )

        # Obtener tamaño del ZIP
        zip_size = zip_path.stat().st_size
        zip_size_mb = zip_size / (1024 * 1024)

        # Verificar tamaño máximo
        max_size_mb = settings.MODULE_MAX_SIZE_MB
        if zip_size_mb > max_size_mb:
            zip_path.unlink()  # Eliminar ZIP
            raise CommandError(
                f'Module demasiado grande: {zip_size_mb:.2f} MB\n'
                f'   Tamaño máximo permitido: {max_size_mb} MB'
            )

        self.stdout.write(f'   ✓ {len(files_added)} archivos agregados')
        self.stdout.write(f'   ✓ Tamaño: {zip_size_mb:.2f} MB\n')

        # Resumen
        self.stdout.write('='*60)
        self.stdout.write(self.style.SUCCESS('✅ MODULE EMPAQUETADO EXITOSAMENTE\n'))
        self.stdout.write(f'   Module: {module_id} v{module_version}')
        self.stdout.write(f'   Archivo: {zip_path}')
        self.stdout.write(f'   Tamaño: {zip_size_mb:.2f} MB ({zip_size:,} bytes)')
        self.stdout.write(f'   Archivos: {len(files_added)}')

        if signature_file.exists():
            self.stdout.write(self.style.SUCCESS('   ✓ Firmado digitalmente'))
        else:
            self.stdout.write(self.style.WARNING('   ⚠️  Sin firma digital'))

        self.stdout.write('')
        self.stdout.write('📋 Próximos pasos:')
        self.stdout.write('\n   OPCIÓN 1: Subir a Cloud (Privado)')
        self.stdout.write('   1. Inicia sesión en https://erplora.com')
        self.stdout.write('   2. Ve a "Modules" → "Mis Modules"')
        self.stdout.write(f'   3. Sube {zip_filename}')
        self.stdout.write('   4. Configura precio/visibilidad')
        self.stdout.write('')
        self.stdout.write('   OPCIÓN 2: GitHub Release (Público)')
        self.stdout.write(f'   1. cd modules/{module_id}')
        self.stdout.write(f'   2. git tag v{module_version}')
        self.stdout.write('   3. git push origin --tags')
        self.stdout.write(f'   4. Crea GitHub Release con {zip_filename}')
        self.stdout.write('')
        self.stdout.write('   OPCIÓN 3: Distribución directa')
        self.stdout.write(f'   1. Comparte {zip_path}')
        self.stdout.write('   2. Usuarios instalan desde Hub con URL del ZIP')
        self.stdout.write('')

        # Mostrar algunos archivos incluidos
        if files_added:
            self.stdout.write('📄 Archivos incluidos (primeros 10):')
            for f in files_added[:10]:
                self.stdout.write(f'   - {f}')
            if len(files_added) > 10:
                self.stdout.write(f'   ... y {len(files_added) - 10} más')
            self.stdout.write('')
