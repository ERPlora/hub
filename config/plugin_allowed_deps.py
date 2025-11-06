"""
Librerías permitidas para plugins de CPOS Hub

Este archivo define las dependencias Python que los plugins pueden usar.
Las librerías están pre-empaquetadas en la aplicación PyInstaller.

Arquitectura: Opción 2 (Pre-bundled Dependencies)
- Plugins solo pueden usar estas librerías
- Validación estricta en plugin.json
- Instalación instantánea (sin pip)
- Bundle total: ~245MB
"""

# === CRÍTICAS (13) - Funcionalidad esencial ===
CRITICAL_DEPENDENCIES = {
    # Imágenes & Media
    'Pillow': '>=10.0.0',          # Manipulación de imágenes (productos, categorías)
    'qrcode': '>=7.4.0',           # QR codes (mesas, productos, pagos)
    'python-barcode': '>=0.15.0',  # Códigos de barras (EAN, UPC, Code128)

    # Office & Reports
    'openpyxl': '>=3.1.0',         # Excel (import/export productos, inventarios)
    'reportlab': '>=4.0.0',        # PDFs (tickets, reportes, facturas)

    # Impresión
    'python-escpos': '>=3.0',      # Impresoras térmicas (tickets POS 58mm/80mm)

    # XML & Facturación Electrónica
    'lxml': '>=5.0.0',             # XML parsing/generation (rápido y robusto)
    'xmltodict': '>=0.13.0',       # XML a dict Python (fácil manejo)
    'signxml': '>=3.2.0',          # Firmas digitales XML (facturas electrónicas)
    'cryptography': '>=42.0.0',    # Cifrado, certificados digitales
    'zeep': '>=4.2.0',             # SOAP web services (APIs de Hacienda/SAT/AFIP)

    # Network
    'requests': '>=2.31.0',        # HTTP requests (APIs, webhooks)
    'websockets': '>=12.0',        # WebSocket cliente (notificaciones Cloud)
}

# === IMPORTANTES (10) - Funcionalidad muy útil ===
IMPORTANT_DEPENDENCIES = {
    # Fechas & Localización
    'python-dateutil': '>=2.8.2',  # Parsing de fechas flexible
    'pytz': '>=2024.1',            # Timezones (importante para multi-país)
    'phonenumbers': '>=8.13.0',    # Validar teléfonos internacionales

    # Pagos
    'stripe': '>=7.0.0',           # Stripe payments (plugins, suscripciones)

    # Data & Analysis
    'pandas': '>=2.1.0',           # Análisis de datos (reportes avanzados)
    'numpy': '>=1.26.0',           # Cálculos numéricos (márgenes, inventarios)

    # Hardware
    'pyserial': '>=3.5',           # Puerto serial (básculas, cajones, displays)

    # Email & Validation
    'email-validator': '>=2.1.0',  # Validar emails

    # Utils
    'python-slugify': '>=8.0.0',   # URLs amigables (slug de productos)
    'pydantic': '>=2.5.0',         # Validación de datos (mejor que forms Django)
}

# === ÚTILES (2) - Nice to have ===
USEFUL_DEPENDENCIES = {
    # Scraping & Parsing
    'beautifulsoup4': '>=4.12.0',  # HTML parsing (importar catálogos web)

    # PDF avanzado
    'PyPDF2': '>=3.0.0',           # Manipular PDFs existentes
}

# === TODAS LAS DEPENDENCIAS PERMITIDAS (25 total) ===
PLUGIN_ALLOWED_DEPENDENCIES = {
    **CRITICAL_DEPENDENCIES,
    **IMPORTANT_DEPENDENCIES,
    **USEFUL_DEPENDENCIES,
}

# === NOMBRES NORMALIZADOS (PyPI → Python module) ===
PACKAGE_NAME_MAP = {
    # PyPI package name → Python import name
    'Pillow': 'PIL',
    'python-barcode': 'barcode',
    'python-escpos': 'escpos',
    'python-dateutil': 'dateutil',
    'python-slugify': 'slugify',
    'beautifulsoup4': 'bs4',
    'PyPDF2': 'PyPDF2',
}


def normalize_package_name(pypi_name: str) -> str:
    """
    Convierte nombre de PyPI a nombre de módulo Python

    Ejemplos:
        'Pillow>=10.0.0' → 'PIL'
        'python-barcode>=0.15.0' → 'barcode'
        'requests>=2.31.0' → 'requests'
    """
    # Extraer solo el nombre del paquete (sin versión)
    pkg_name = pypi_name.split('>=')[0].split('==')[0].split('[')[0].strip()

    # Usar mapeo si existe, sino devolver el mismo nombre
    return PACKAGE_NAME_MAP.get(pkg_name, pkg_name)


def get_pyinstaller_imports() -> list[str]:
    """
    Retorna lista de nombres de módulos para hiddenimports de PyInstaller

    Returns:
        list: ['PIL', 'qrcode', 'barcode', 'openpyxl', ...]
    """
    return [
        normalize_package_name(pkg)
        for pkg in PLUGIN_ALLOWED_DEPENDENCIES.keys()
    ]


def is_dependency_allowed(package_name: str) -> bool:
    """
    Verifica si una dependencia está permitida

    Args:
        package_name: Nombre del paquete (con o sin versión)

    Returns:
        bool: True si está permitida

    Examples:
        >>> is_dependency_allowed('Pillow>=10.0.0')
        True
        >>> is_dependency_allowed('malicious-pkg')
        False
    """
    # Extraer nombre sin versión
    pkg_name = package_name.split('>=')[0].split('==')[0].split('[')[0].strip()
    return pkg_name in PLUGIN_ALLOWED_DEPENDENCIES


def get_allowed_dependencies_list() -> list[str]:
    """
    Retorna lista de dependencias permitidas en formato human-readable

    Returns:
        list: ['Pillow>=10.0.0', 'qrcode>=7.4.0', ...]
    """
    return [f"{pkg}{version}" for pkg, version in PLUGIN_ALLOWED_DEPENDENCIES.items()]


def get_dependencies_by_category() -> dict:
    """
    Retorna dependencias agrupadas por categoría

    Returns:
        dict: {'critical': {...}, 'important': {...}, 'useful': {...}}
    """
    return {
        'critical': CRITICAL_DEPENDENCIES,
        'important': IMPORTANT_DEPENDENCIES,
        'useful': USEFUL_DEPENDENCIES,
    }


# === METADATA ===
TOTAL_DEPENDENCIES = len(PLUGIN_ALLOWED_DEPENDENCIES)
ESTIMATED_BUNDLE_SIZE_MB = 245


if __name__ == '__main__':
    print(f"📦 CPOS Hub - Plugin Allowed Dependencies")
    print(f"Total: {TOTAL_DEPENDENCIES} librerías")
    print(f"Bundle estimado: ~{ESTIMATED_BUNDLE_SIZE_MB}MB")
    print()

    print("🔴 CRÍTICAS (13):")
    for pkg, version in CRITICAL_DEPENDENCIES.items():
        print(f"  - {pkg}{version}")

    print()
    print("🟡 IMPORTANTES (10):")
    for pkg, version in IMPORTANT_DEPENDENCIES.items():
        print(f"  - {pkg}{version}")

    print()
    print("🟢 ÚTILES (2):")
    for pkg, version in USEFUL_DEPENDENCIES.items():
        print(f"  - {pkg}{version}")

    print()
    print("📋 PyInstaller imports:")
    for module in get_pyinstaller_imports():
        print(f"  - {module}")
