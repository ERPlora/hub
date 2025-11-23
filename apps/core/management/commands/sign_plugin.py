"""
Management command para firmar digitalmente un plugin.

Crea firma RSA-SHA256 del plugin para verificación en producción.

Uso:
    python manage.py sign_plugin <plugin_id> [--key-file path/to/private.pem]

Ejemplos:
    python manage.py sign_plugin products
    python manage.py sign_plugin restaurant-pos --key-file ~/.cpos-dev/signing-key.pem

Notas:
    - En desarrollo, la firma es opcional (REQUIRE_PLUGIN_SIGNATURE=False)
    - En producción, la firma es obligatoria
    - La clave privada debe mantenerse segura y NO incluirse en el plugin
    - La firma se guarda en el plugin como .signature
"""

from django.core.management.base import BaseCommand, CommandError
from pathlib import Path
from django.conf import settings
import hashlib
import json
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
import base64


class Command(BaseCommand):
    help = 'Firma digitalmente un plugin para distribución'

    def add_arguments(self, parser):
        parser.add_argument(
            'plugin_id',
            type=str,
            help='ID del plugin a firmar'
        )
        parser.add_argument(
            '--key-file',
            type=str,
            default=None,
            help='Ruta a la clave privada RSA (se genera una si no existe)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-firmar aunque ya tenga firma'
        )

    def handle(self, *args, **options):
        plugin_id = options['plugin_id']
        key_file = options['key_file']
        force = options['force']

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

        signature_file = plugin_dir / '.signature'

        if signature_file.exists() and not force:
            raise CommandError(
                f'Plugin ya tiene firma. Usa --force para re-firmar\n'
                f'   Archivo: {signature_file}'
            )

        self.stdout.write(self.style.SUCCESS(f'\n🔐 Firmando plugin: {plugin_id}'))
        self.stdout.write(f'   Ubicación: {plugin_dir}\n')

        # 1. Cargar o generar clave privada
        self.stdout.write('🔑 Cargando clave privada...')

        if key_file:
            key_path = Path(key_file)
            if not key_path.exists():
                raise CommandError(f'Archivo de clave no encontrado: {key_file}')
        else:
            # Usar ubicación por defecto (~/.cpos-dev/signing-key.pem)
            dev_dir = Path.home() / '.cpos-dev'
            dev_dir.mkdir(parents=True, exist_ok=True)
            key_path = dev_dir / 'signing-key.pem'

            if not key_path.exists():
                self.stdout.write(self.style.WARNING(f'   ⚠️  Clave privada no encontrada en {key_path}'))
                self.stdout.write('   📝 Generando nueva clave RSA-4096...')

                # Generar nueva clave privada
                private_key = rsa.generate_private_key(
                    public_exponent=65537,
                    key_size=settings.PLUGIN_SIGNATURE_KEY_SIZE,
                    backend=default_backend()
                )

                # Guardar clave privada
                with open(key_path, 'wb') as f:
                    f.write(private_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.PKCS8,
                        encryption_algorithm=serialization.NoEncryption()
                    ))

                # Guardar clave pública
                public_key = private_key.public_key()
                public_key_path = key_path.with_suffix('.pub')
                with open(public_key_path, 'wb') as f:
                    f.write(public_key.public_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo
                    ))

                self.stdout.write(self.style.SUCCESS(f'   ✅ Clave privada generada: {key_path}'))
                self.stdout.write(self.style.SUCCESS(f'   ✅ Clave pública guardada: {public_key_path}'))
                self.stdout.write(self.style.WARNING('\n   ⚠️  IMPORTANTE:'))
                self.stdout.write(self.style.WARNING('   - Guarda la clave privada en lugar seguro'))
                self.stdout.write(self.style.WARNING('   - NO incluyas la clave privada en el plugin'))
                self.stdout.write(self.style.WARNING('   - La clave pública se incluirá en la firma'))
                self.stdout.write('')

        # Cargar clave privada
        try:
            with open(key_path, 'rb') as f:
                private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None,
                    backend=default_backend()
                )
            public_key = private_key.public_key()
            self.stdout.write(f'   ✓ Clave cargada desde {key_path}\n')
        except Exception as e:
            raise CommandError(f'Error al cargar clave privada: {e}')

        # 2. Calcular hash del plugin
        self.stdout.write('🔐 Calculando hash del plugin...')

        files_to_hash = []
        exclude_patterns = ['.signature', '__pycache__', '.pyc', '.git', '.DS_Store', 'Thumbs.db']

        for file_path in sorted(plugin_dir.rglob('*')):
            if file_path.is_file():
                # Excluir archivos
                if any(pattern in str(file_path) for pattern in exclude_patterns):
                    continue

                files_to_hash.append(file_path)

        if not files_to_hash:
            raise CommandError('No se encontraron archivos para firmar')

        # Calcular hash SHA256 de todos los archivos
        hasher = hashlib.sha256()

        for file_path in files_to_hash:
            try:
                with open(file_path, 'rb') as f:
                    file_data = f.read()
                    hasher.update(file_data)

                rel_path = file_path.relative_to(plugin_dir)
                self.stdout.write(f'   ✓ {rel_path} ({len(file_data)} bytes)')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'   ⚠️  Error leyendo {file_path}: {e}'))

        plugin_hash = hasher.hexdigest()
        self.stdout.write(f'\n   📝 Hash del plugin: {plugin_hash}\n')

        # 3. Firmar hash
        self.stdout.write('✍️  Firmando hash...')

        try:
            signature = private_key.sign(
                plugin_hash.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )

            signature_b64 = base64.b64encode(signature).decode('utf-8')
            self.stdout.write(f'   ✓ Firma generada ({len(signature)} bytes)\n')
        except Exception as e:
            raise CommandError(f'Error al firmar: {e}')

        # 4. Guardar firma
        self.stdout.write('💾 Guardando firma...')

        # Obtener clave pública en formato PEM
        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')

        # Leer plugin.json para metadata
        with open(plugin_dir / 'plugin.json', 'r') as f:
            plugin_data = json.load(f)

        signature_data = {
            'plugin_id': plugin_id,
            'version': plugin_data.get('version', '0.0.0'),
            'hash': plugin_hash,
            'algorithm': settings.PLUGIN_SIGNATURE_ALGORITHM,
            'signature': signature_b64,
            'public_key': public_key_pem,
            'signed_at': None  # Se llena al empaquetar
        }

        with open(signature_file, 'w') as f:
            json.dump(signature_data, f, indent=2)

        self.stdout.write(f'   ✓ Firma guardada en {signature_file}\n')

        # Resumen
        self.stdout.write('='*60)
        self.stdout.write(self.style.SUCCESS('✅ PLUGIN FIRMADO EXITOSAMENTE\n'))
        self.stdout.write(f'   Plugin: {plugin_id} v{plugin_data.get("version")}')
        self.stdout.write(f'   Hash: {plugin_hash[:32]}...')
        self.stdout.write(f'   Algoritmo: {settings.PLUGIN_SIGNATURE_ALGORITHM}')
        self.stdout.write(f'   Archivos firmados: {len(files_to_hash)}')
        self.stdout.write(f'   Firma: {signature_file}')
        self.stdout.write('')
        self.stdout.write('📋 Próximos pasos:')
        self.stdout.write(f'   1. python manage.py package_plugin {plugin_id}')
        self.stdout.write(f'   2. Sube el ZIP a Cloud o GitHub')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('⚠️  Recuerda:'))
        self.stdout.write(self.style.WARNING(f'   - NO incluyas {key_path} en el repositorio'))
        self.stdout.write(self.style.WARNING('   - La clave pública está en la firma (.signature)'))
        self.stdout.write('')
