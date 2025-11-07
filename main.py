#!/usr/bin/env python3
"""
CPOS Hub - Launcher para macOS
Este script inicia Django embebido y abre pywebview con la interfaz

Copyright (c) 2025 CPOS Team
Licensed under the Business Source License 1.1 (BUSL-1.1)
See LICENSE file for details.
"""
import threading
import time
import sys
import os
from pathlib import Path
import webview

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
    - Windows: C:\\Users\\<user>\\AppData\\Local\\CPOSHub\\
    - macOS: ~/Library/Application Support/CPOSHub/
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
        print(f"[INFO] Plugins: {paths.plugins_dir}")
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

        # Migrar plugins legacy si existe
        legacy_plugins = hub_dir / 'plugins'
        if legacy_plugins.exists() and legacy_plugins.is_dir():
            print(f"\n[INFO] Migrating legacy plugins from {legacy_plugins}")
            for item in legacy_plugins.rglob('*'):
                if item.is_file():
                    rel_path = item.relative_to(legacy_plugins)
                    dest = paths.plugins_dir / rel_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if not dest.exists():
                        shutil.copy2(item, dest)
            print(f"[OK] Plugins migrated to {paths.plugins_dir}")

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

# Abrir pywebview
print("Opening webview...")
try:
    # Crear ventana de pywebview con el navegador nativo de macOS
    window = webview.create_window(
        'CPOS Hub',
        'http://localhost:8001',
        width=1200,
        height=800,
        resizable=True,
        fullscreen=False
    )

    print("[OK] App is running. Close the window to exit.")

    # Iniciar webview (esto bloquea hasta que se cierra la ventana)
    webview.start()

    print("Window closed, shutting down...")

except Exception as e:
    print(f"ERROR opening webview: {e}")
    import traceback
    traceback.print_exc()

finally:
    print("Shutdown complete")
