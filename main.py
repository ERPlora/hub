#!/usr/bin/env python3
"""
ERPlora Hub - Launcher para macOS
Este script inicia Django embebido y abre pywebview con la interfaz

Copyright (c) 2025 CPOS Team
Licensed under the Business Source License 1.1 (BUSL-1.1)
See LICENSE file for details.
"""
import threading
import time
import sys
import os
import argparse
from pathlib import Path
import webview


class WindowAPI:
    """API expuesta al frontend para controlar la ventana"""

    def __init__(self):
        self.window = None
        self._is_fullscreen = False
        self._print_service = None

    def set_window(self, window):
        """Establecer referencia a la ventana después de crearla"""
        self.window = window

    def _get_print_service(self):
        """Obtiene la instancia del servicio de impresión (lazy loading)"""
        if self._print_service is None:
            try:
                # Importar el servicio de impresión del module
                from modules.printers.print_service import print_service
                self._print_service = print_service
            except ImportError as e:
                print(f"[WARNING] Print service not available: {e}")
                return None
        return self._print_service

    def toggle_fullscreen(self):
        """Toggle entre fullscreen y normal"""
        if not self.window:
            return {'error': 'Window not initialized'}

        try:
            self.window.toggle_fullscreen()
            self._is_fullscreen = not self._is_fullscreen
            return {'fullscreen': self._is_fullscreen, 'message': f'Fullscreen {"activated" if self._is_fullscreen else "deactivated"}'}
        except Exception as e:
            return {'error': str(e)}

    def maximize(self):
        """Maximizar ventana"""
        if not self.window:
            return {'error': 'Window not initialized'}

        try:
            self.window.maximize()
            return {'maximized': True}
        except Exception as e:
            return {'error': str(e)}

    def minimize(self):
        """Minimizar ventana"""
        if not self.window:
            return {'error': 'Window not initialized'}

        try:
            self.window.minimize()
            return {'minimized': True}
        except Exception as e:
            return {'error': str(e)}

    def restore(self):
        """Restaurar tamaño normal"""
        if not self.window:
            return {'error': 'Window not initialized'}

        try:
            self.window.restore()
            return {'restored': True}
        except Exception as e:
            return {'error': str(e)}

    # =========================================================================
    # PRINT SERVICE METHODS
    # =========================================================================

    def print_receipt(self, receipt_data):
        """
        Imprime un recibo usando el servicio de impresión.

        Args:
            receipt_data (dict): Datos del recibo (ver print_service.py para formato)

        Returns:
            dict: {'success': bool, 'message': str}
        """
        print_service = self._get_print_service()
        if not print_service:
            return {
                'success': False,
                'message': 'Print service not available. Make sure printers module is installed.'
            }

        try:
            return print_service.print_receipt(receipt_data)
        except Exception as e:
            print(f"[ERROR] print_receipt failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }

    def get_system_printers(self):
        """
        Obtiene lista de impresoras del sistema.

        Returns:
            list: Lista de diccionarios con info de impresoras
        """
        print_service = self._get_print_service()
        if not print_service:
            return []

        try:
            return print_service.get_system_printers()
        except Exception as e:
            print(f"[ERROR] get_system_printers failed: {e}")
            return []

    def get_default_printer(self):
        """
        Obtiene el nombre de la impresora por defecto.

        Returns:
            str or None: Nombre de la impresora o None
        """
        print_service = self._get_print_service()
        if not print_service:
            return None

        try:
            return print_service.get_default_printer()
        except Exception as e:
            print(f"[ERROR] get_default_printer failed: {e}")
            return None

    def print_barcode(self, svg_content):
        """
        Imprime un código de barras usando el diálogo nativo del sistema.

        Args:
            svg_content (str): Contenido SVG del código de barras

        Returns:
            dict: {'success': bool, 'message': str}
        """
        import tempfile
        import subprocess

        try:
            # Crear archivo temporal HTML con el SVG
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <style>
                        body {{
                            margin: 0;
                            padding: 20px;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            min-height: 100vh;
                        }}
                        svg {{
                            max-width: 100%;
                            height: auto;
                        }}
                    </style>
                </head>
                <body>
                    {svg_content}
                </body>
                </html>
                """
                f.write(html_content)
                temp_path = f.name

            # Abrir diálogo de impresión nativo según el sistema operativo
            if sys.platform == 'darwin':
                # macOS: abrir con el comando open que muestra el diálogo de impresión
                subprocess.run(['open', '-a', 'Safari', temp_path])
                return {
                    'success': True,
                    'message': 'Barcode opened in Safari. Use Cmd+P to print.'
                }
            elif sys.platform == 'win32':
                # Windows: abrir con el navegador predeterminado
                os.startfile(temp_path)
                return {
                    'success': True,
                    'message': 'Barcode opened in default browser. Use Ctrl+P to print.'
                }
            else:
                # Linux: usar xdg-open
                subprocess.run(['xdg-open', temp_path])
                return {
                    'success': True,
                    'message': 'Barcode opened in default browser. Use Ctrl+P to print.'
                }

        except Exception as e:
            return {'success': False, 'error': str(e)}

# Detectar si estamos en PyInstaller bundle
if getattr(sys, 'frozen', False):
    # Running in PyInstaller bundle
    # En onedir mode, los archivos están en el mismo directorio que el ejecutable
    bundle_dir = Path(sys.executable).parent

    # En macOS, el ejecutable está en .app/Contents/MacOS/
    # En Windows/Linux, está en el directorio raíz del bundle
    if sys.platform == 'darwin':
        # macOS: .app/Contents/MacOS
        app_dir = bundle_dir.parent.parent  # -> .app
    else:
        # Windows/Linux: el directorio del bundle es el app_dir
        app_dir = bundle_dir
else:
    # Running in development
    bundle_dir = Path(__file__).parent
    app_dir = Path(__file__).parent.parent

print(f"Platform: {sys.platform}")
print(f"Bundle dir: {bundle_dir}")
print(f"App dir: {app_dir}")

# En onedir mode, los datas están en _internal/
# macOS: .app/Contents/MacOS/_internal/hub/
# Windows/Linux: ./_internal/hub/
if (bundle_dir / "_internal" / "hub").exists():
    hub_dir = bundle_dir / "_internal" / "hub"
else:
    hub_dir = bundle_dir / "hub"

if not hub_dir.exists():
    print(f"ERROR: Hub directory not found at {hub_dir}")
    print("Looking for manage.py...")
    # Try different locations
    for path in [
        bundle_dir / "hub",  # _MEIPASS/hub
        app_dir / "Contents" / "Resources" / "hub",  # macOS app bundle
        bundle_dir,  # _MEIPASS root
        Path.cwd(),  # Current directory
    ]:
        manage_py = path / "manage.py"
        print(f"Checking: {manage_py}")
        if manage_py.exists():
            hub_dir = path
            print(f"Found manage.py at {hub_dir}")
            break
    else:
        print("ERROR: Could not find Django project")
        print(f"Bundle dir contents: {list(bundle_dir.iterdir()) if bundle_dir.exists() else 'does not exist'}")
        sys.exit(1)

print(f"Using hub directory: {hub_dir}")

# Agregar el directorio del hub al PYTHONPATH
sys.path.insert(0, str(hub_dir))

# Configurar el settings module de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


def initialize_data_directories():
    """
    Inicializa los directorios de datos de usuario en ubicaciones externas.

    Crea directorios según la plataforma:
    - Windows: C:\\Users\\<user>\\AppData\\Local\\ERPloraHub\\
    - macOS: ~/Library/Application Support/ERPloraHub/
    - Linux: ~/.cpos-hub/

    También migra datos legacy si existen en el directorio de la app.
    """
    print("\n[INFO] Initializing data directories...")

    try:
        from config.paths import get_data_paths
        import shutil

        paths = get_data_paths()

        # Mostrar ubicaciones
        print(f"[INFO] Platform: {sys.platform}")
        print(f"[INFO] Base data directory: {paths.base_dir}")
        print(f"[INFO] Database: {paths.database_path}")
        print(f"[INFO] Media: {paths.media_dir}")
        print(f"[INFO] Modules: {paths.modules_dir}")
        print(f"[INFO] Reports: {paths.reports_dir}")
        print(f"[INFO] Logs: {paths.logs_dir}")
        print(f"[INFO] Backups: {paths.backups_dir}")

        # Los directorios ya se crean automáticamente en paths.py
        # Aquí solo verificamos y migramos datos legacy si existen

        # Migrar base de datos legacy si existe
        legacy_db = hub_dir / 'db.sqlite3'
        if legacy_db.exists() and not paths.database_path.exists():
            print(f"\n[INFO] Migrating legacy database from {legacy_db}")
            shutil.copy2(legacy_db, paths.database_path)
            print(f"[OK] Database migrated to {paths.database_path}")

            # Crear backup del legacy
            backup_path = hub_dir / 'db.sqlite3.legacy'
            shutil.move(legacy_db, backup_path)
            print(f"[OK] Legacy database backed up to {backup_path}")

        # Migrar media legacy si existe
        legacy_media = hub_dir / 'media'
        if legacy_media.exists() and legacy_media.is_dir():
            print(f"\n[INFO] Migrating legacy media from {legacy_media}")
            for item in legacy_media.rglob('*'):
                if item.is_file():
                    rel_path = item.relative_to(legacy_media)
                    dest = paths.media_dir / rel_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if not dest.exists():
                        shutil.copy2(item, dest)
            print(f"[OK] Media migrated to {paths.media_dir}")

        # Migrar modules legacy si existe
        legacy_modules = hub_dir / 'modules'
        if legacy_modules.exists() and legacy_modules.is_dir():
            print(f"\n[INFO] Migrating legacy modules from {legacy_modules}")
            for item in legacy_modules.rglob('*'):
                if item.is_file():
                    rel_path = item.relative_to(legacy_modules)
                    dest = paths.modules_dir / rel_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if not dest.exists():
                        shutil.copy2(item, dest)
            print(f"[OK] Modules migrated to {paths.modules_dir}")

        print("\n[OK] Data directories initialized successfully")

    except Exception as e:
        print(f"\n[ERROR] Failed to initialize data directories: {e}")
        import traceback
        traceback.print_exc()


# Inicializar directorios de datos
initialize_data_directories()


def run_django_server():
    """Ejecuta el servidor Django en un thread separado"""
    print("Starting Django server thread...")
    try:
        # Importar Django
        import django
        from django.core.management import execute_from_command_line

        # Setup Django
        django.setup()
        print("Django setup complete")

        # Ejecutar el servidor
        # Cambiar directorio de trabajo al hub
        original_cwd = os.getcwd()
        os.chdir(str(hub_dir))

        print("Starting Django runserver on 0.0.0.0:8001...")
        execute_from_command_line(['manage.py', 'runserver', '0.0.0.0:8001', '--noreload'])

        os.chdir(original_cwd)
    except Exception as e:
        print(f"ERROR starting Django: {e}")
        import traceback
        traceback.print_exc()


# Iniciar Django en un thread separado
django_thread = threading.Thread(target=run_django_server, daemon=True)
django_thread.start()

# Esperar a que Django esté listo
print("Waiting for Django to start...")
django_ready = False

for i in range(15):  # Intentar por 15 segundos
    time.sleep(1)

    # Intentar conectar al puerto para ver si Django está escuchando
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', 8001))
    sock.close()

    if result == 0:
        django_ready = True
        print(f"[OK] Django started successfully (took {i+1} seconds)")
        break
    else:
        print(f"  Waiting... ({i+1}/15)")

if not django_ready:
    print("ERROR: Django did not start in time")
    sys.exit(1)

# Parse command line arguments
parser = argparse.ArgumentParser(description='ERPlora Hub - Desktop Application')
parser.add_argument('--kiosk', action='store_true', help='Start in kiosk mode (fullscreen, no browser UI)')
parser.add_argument('--width', type=int, default=1200, help='Window width (default: 1200)')
parser.add_argument('--height', type=int, default=800, help='Window height (default: 800)')
args = parser.parse_args()

# Abrir pywebview
print("Opening webview...")
if args.kiosk:
    print("[INFO] Starting in KIOSK MODE (fullscreen)")

# Crear instancia global de la API
api = WindowAPI()

def on_shown():
    """Callback que se ejecuta cuando la ventana se muestra"""
    # Aquí la ventana ya existe y podemos obtener referencia
    windows = webview.windows
    if windows:
        api.set_window(windows[0])
        print("[INFO] WindowAPI initialized with window reference")

try:
    # Crear ventana de pywebview con el navegador nativo de macOS
    window = webview.create_window(
        'ERPlora Hub',
        'http://localhost:8001',
        width=args.width,
        height=args.height,
        resizable=not args.kiosk,  # No resizable en kiosk mode
        fullscreen=args.kiosk,     # Fullscreen en kiosk mode
        js_api=api  # Pasar la API aquí
    )

    print("[OK] App is running. Close the window to exit.")

    # Iniciar webview (esto bloquea hasta que se cierra la ventana)
    webview.start(on_shown, debug=False)

    print("Window closed, shutting down...")

except Exception as e:
    print(f"ERROR opening webview: {e}")
    import traceback
    traceback.print_exc()

finally:
    print("Shutdown complete")
