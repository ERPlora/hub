#!/usr/bin/env python3
"""
CPOS Hub - Launcher para macOS
Este script inicia Django embebido y abre pywebview con la interfaz
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
