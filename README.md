# ERPlora Hub

Sistema POS (Point of Sale) modular basado en Django.

## Caracteristicas

- Aplicacion empaquetada con **PyInstaller**
- **100% GRATUITA** - sin costo de licencia
- SQLite local
- **Funciona 100% offline** despues de setup inicial
- Extensible con modules (gratuitos o de pago)

---

## Requisitos (Desarrollo Local)

- Python 3.11+
- SQLite 3+ (incluido con Python)
- uv (gestor de paquetes Python)

## Instalacion (Desarrollo)

```bash
cd hub

# Crear entorno virtual con uv
uv venv
source .venv/bin/activate  # Linux/macOS

# Instalar dependencias
uv pip install -e ".[dev]"

# Aplicar migraciones
python manage.py migrate

# Servidor de desarrollo
python manage.py runserver 8001
```

---

## Estructura del Proyecto

```
hub/
├── apps/                      # Aplicaciones Django
│   ├── accounts/             # LocalUser, autenticacion con PIN
│   ├── configuration/        # HubConfig, StoreConfig (singleton)
│   ├── modules/              # Module model, runtime manager
│   ├── sync/                 # Sincronizacion con Cloud
│   └── core/                 # Utilidades compartidas
│
├── config/                   # Configuracion Django
│   ├── settings.py
│   ├── urls.py
│   └── module_allowed_deps.py
│
├── modules/                  # Modules instalados
│   ├── .template/           # Template base para nuevos modules
│   └── ...                  # Modules activos
│
├── templates/               # Django templates (Ionic + HTMX)
├── static/                  # CSS/JS
├── main.py                  # Entry point para PyInstaller
├── main.spec                # Configuracion PyInstaller
├── build.py                 # Script de build
└── pyproject.toml           # Dependencias (uv)
```

---

## Build (PyInstaller)

```bash
cd hub
python build.py
```

### Ejecutables Generados

- **Windows:** `dist/ERPlora Hub/ERPlora Hub.exe`
- **macOS:** `dist/ERPlora Hub.app`
- **Linux:** `dist/ERPlora Hub/ERPlora Hub`

---

## Sistema de Modules

El Hub soporta modules dinamicos con dependencias pre-aprobadas.

**Dependencias permitidas**:
- `Pillow` - Imagenes
- `qrcode` - QR codes
- `python-barcode` - Codigos de barras
- `openpyxl` - Excel
- `reportlab` - PDFs
- Y mas...

Ver lista completa en [config/module_allowed_deps.py](config/module_allowed_deps.py).

**Gestion de modules**:
- Activar: mover de `_module_name/` a `module_name/`
- Desactivar: mover de `module_name/` a `_module_name/`
- Ocultar: prefijar con `.` (`.module_name/`)

---

## Testing

```bash
pytest
pytest tests/unit
pytest tests/integration
pytest --cov=apps --cov-report=html
```

---

## Stack Tecnologico

| Componente | Tecnologia |
|------------|------------|
| Backend | Django 5.1 |
| Database | SQLite |
| Frontend | Ionic 8 (iOS mode) + Alpine.js + HTMX |
| Autenticacion | LocalUser con PIN |
| Build | PyInstaller |

---

**Ultima actualizacion:** 2025-12-26
