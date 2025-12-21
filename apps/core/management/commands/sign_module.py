"""
Management command para firmar digitalmente un module.

Crea firma RSA-SHA256 del module para verificación en producción.

Uso:
    python manage.py sign_module <module_id> [--key-file path/to/private.pem]

Ejemplos:
    python manage.py sign_module products
    python manage.py sign_module restaurant-pos --key-file ~/.cpos-dev/signing-key.pem

Notas:
    - En desarrollo, la firma es opcional (REQUIRE_MODULE_SIGNATURE=False)
    - En producción, la firma es obligatoria
    - La clave privada debe mantenerse segura y NO incluirse en el module
    - La firma se guarda en el module como .signature
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
    help = 'Firma digitalmente un module para distribución'

    def add_arguments(self, parser):
        parser.add_argument(
            'module_id',
            type=str,
            help='ID del module a firmar'
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
        module_id = options['module_id']
        key_file = options['key_file']
        force = options['force']

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

        signature_file = module_dir / '.signature'

        if signature_file.exists() and not force:
            raise CommandError(
                f'Module ya tiene firma. Usa --force para re-firmar\n'
                f'   Archivo: {signature_file}'
            )

        self.stdout.write(self.style.SUCCESS(f'\n🔐 Firmando module: {module_id}'))
        self.stdout.write(f'   Ubicación: {module_dir}\n')

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
                    key_size=settings.MODULE_SIGNATURE_KEY_SIZE,
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
                self.stdout.write(self.style.WARNING('   - NO incluyas la clave privada en el module'))
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

        # 2. Calcular hash del module
        self.stdout.write('🔐 Calculando hash del module...')

        files_to_hash = []
        exclude_patterns = ['.signature', '__pycache__', '.pyc', '.git', '.DS_Store', 'Thumbs.db']

        for file_path in sorted(module_dir.rglob('*')):
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

                rel_path = file_path.relative_to(module_dir)
                self.stdout.write(f'   ✓ {rel_path} ({len(file_data)} bytes)')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'   ⚠️  Error leyendo {file_path}: {e}'))

        module_hash = hasher.hexdigest()
        self.stdout.write(f'\n   📝 Hash del module: {module_hash}\n')

        # 3. Firmar hash
        self.stdout.write('✍️  Firmando hash...')

        try:
            signature = private_key.sign(
                module_hash.encode('utf-8'),
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

        # Leer module.json para metadata
        with open(module_dir / 'module.json', 'r') as f:
            module_data = json.load(f)

        signature_data = {
            'module_id': module_id,
            'version': module_data.get('version', '0.0.0'),
            'hash': module_hash,
            'algorithm': settings.MODULE_SIGNATURE_ALGORITHM,
            'signature': signature_b64,
            'public_key': public_key_pem,
            'signed_at': None  # Se llena al empaquetar
        }

        with open(signature_file, 'w') as f:
            json.dump(signature_data, f, indent=2)

        self.stdout.write(f'   ✓ Firma guardada en {signature_file}\n')

        # Resumen
        self.stdout.write('='*60)
        self.stdout.write(self.style.SUCCESS('✅ MODULE FIRMADO EXITOSAMENTE\n'))
        self.stdout.write(f'   Module: {module_id} v{module_data.get("version")}')
        self.stdout.write(f'   Hash: {module_hash[:32]}...')
        self.stdout.write(f'   Algoritmo: {settings.MODULE_SIGNATURE_ALGORITHM}')
        self.stdout.write(f'   Archivos firmados: {len(files_to_hash)}')
        self.stdout.write(f'   Firma: {signature_file}')
        self.stdout.write('')
        self.stdout.write('📋 Próximos pasos:')
        self.stdout.write(f'   1. python manage.py package_module {module_id}')
        self.stdout.write('   2. Sube el ZIP a Cloud o GitHub')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('⚠️  Recuerda:'))
        self.stdout.write(self.style.WARNING(f'   - NO incluyas {key_path} en el repositorio'))
        self.stdout.write(self.style.WARNING('   - La clave pública está en la firma (.signature)'))
        self.stdout.write('')
