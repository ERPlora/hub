# -*- mode: python ; coding: utf-8 -*-


import sys
import tomllib
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Determinar la ruta del proyecto hub (ahora desde el root)
hub_root = Path('.').resolve()  # Estamos en el root del proyecto

# Importar dependencias permitidas de plugins
sys.path.insert(0, str(hub_root))
try:
    from config.plugin_allowed_deps import get_pyinstaller_imports, TOTAL_DEPENDENCIES
    plugin_imports = get_pyinstaller_imports()
    print(f"[INFO] Cargadas {TOTAL_DEPENDENCIES} librerias para plugins")
except ImportError as e:
    print(f"[WARNING] No se pudo cargar plugin_allowed_deps: {e}")
    plugin_imports = []

# Leer dependencias del pyproject.toml automáticamente
def get_dependencies_from_pyproject():
    """Lee las dependencias del pyproject.toml y retorna lista de paquetes"""
    pyproject_path = hub_root / 'pyproject.toml'
    if not pyproject_path.exists():
        return []

    with open(pyproject_path, 'rb') as f:
        pyproject = tomllib.load(f)

    dependencies = pyproject.get('project', {}).get('dependencies', [])

    # Extraer solo el nombre del paquete (sin versión)
    packages = []
    for dep in dependencies:
        # Formato: "Django>=5.2.7" -> "django"
        # Formato: "python-decouple>=3.8" -> "decouple"
        pkg_name = dep.split('>=')[0].split('==')[0].split('[')[0].strip()

        # Normalizar nombres (PyPI usa guiones, Python usa guiones bajos)
        if pkg_name == 'python-decouple':
            pkg_name = 'decouple'
        elif pkg_name == 'Django':
            pkg_name = 'django'

        packages.append(pkg_name)

    return packages

# Obtener paquetes del pyproject.toml
pyproject_packages = get_dependencies_from_pyproject()
print(f"[INFO] Dependencias encontradas en pyproject.toml: {pyproject_packages}")

# Incluir todo el proyecto Django como data files
datas = [
    # Proyecto Django completo
    (str(hub_root / 'manage.py'), 'hub'),
    (str(hub_root / 'config'), 'hub/config'),
    (str(hub_root / 'apps'), 'hub/apps'),
    (str(hub_root / 'static'), 'hub/static'),
    (str(hub_root / 'locale'), 'hub/locale'),
    # NOTA: db.sqlite3 YA NO se incluye - ahora está en ubicación externa
    # - Windows: C:\Users\<user>\AppData\Local\ERPloraHub\db\
    # - macOS: ~/Library/Application Support/ERPloraHub/db/
    # - Linux: ~/.cpos-hub/db/
    # NOTA: plugins/ NO se incluye - se cargan desde ubicaciones externas:
    # - Development: ./plugins/ (repo local)
    # - Production: ~/.cpos-hub/plugins/ (instalados por usuario)
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # === DJANGO ===
        # Collect ALL Django submodules automatically
        *collect_submodules('django'),

        # === DEPENDENCIAS DEL HUB (pyproject.toml) ===
        # Auto-collect submodules from pyproject.toml dependencies (excepto django que ya está)
        *[submod for pkg in pyproject_packages if pkg != 'django' for submod in collect_submodules(pkg)],

        # === LIBRERÍAS PARA PLUGINS (25 librerías) ===
        # Collect submodules para cada librería permitida
        *[submod for pkg in plugin_imports for submod in collect_submodules(pkg)],

        # === PLATFORM-SPECIFIC ===
        'webview.platforms.cocoa',  # macOS
        'pyobjc',  # macOS

        # === STANDARD LIBRARY ===
        'threading',
        'socket',
    ],
    hookspath=['pyi_hooks'],  # Hook personalizado necesario para evitar errores con Django
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],  # No incluir binaries aquí (onedir mode)
    exclude_binaries=True,  # Cambio clave: no incluir binarios en el EXE
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Cambiado a False para modo producción
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app_icon.ico' if sys.platform == 'win32' else ('assets/app_icon.icns' if sys.platform == 'darwin' else None),
)

# COLLECT crea el directorio con todos los archivos
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='main',
)

# macOS App Bundle (solo en macOS)
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='ERPlora Hub.app',
        icon='assets/app_icon.icns' if Path('assets/app_icon.icns').exists() else None,
        bundle_identifier='com.cpos.hub',
        info_plist={
            'CFBundleName': 'ERPlora Hub',
            'CFBundleDisplayName': 'ERPlora Hub',
            'CFBundleShortVersionString': '1.0.0',
            'CFBundleVersion': '1.0.0',
            'NSHighResolutionCapable': 'True',
            'LSMinimumSystemVersion': '10.13',
        },
    )
