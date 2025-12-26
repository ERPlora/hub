# ERPlora Hub

Sistema POS (Point of Sale) modular Django con **dos modos de despliegue**.

## Modos de Despliegue

### 1. Desktop Hub (On-Premise) - GRATIS
- Aplicacion empaquetada con **PyInstaller**
- **100% GRATUITA** - sin costo de licencia
- SQLite local en la maquina del cliente
- **Funciona 100% offline** despues de setup inicial
- Extensible con modules (gratuitos o de pago)

### 2. Cloud Hub (SaaS)
- Contenedor Docker
- SQLite en volumen persistente
- Acceso via subdominio: `{subdomain}.erplora.com`
- Planes de suscripcion

**Nota:** Ambos modos usan el mismo codigo Django. La unica diferencia es el metodo de despliegue.

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

El Hub corre en puerto **8001** por defecto (Cloud Portal usa 8000).

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
├── Dockerfile               # Build para Cloud Hub
├── main.py                  # Entry point para Desktop Hub (PyInstaller)
├── main.spec                # Configuracion PyInstaller
├── build.py                 # Script de build Desktop
└── pyproject.toml           # Dependencias (uv)
```

---

## Desktop Hub (PyInstaller)

### Build

```bash
cd hub
python build.py
```

### Ejecutables Generados

- **Windows:** `dist/ERPlora Hub/ERPlora Hub.exe`
- **macOS:** `dist/ERPlora Hub.app`
- **Linux:** `dist/ERPlora Hub/ERPlora Hub`

### GitHub Actions

- Push a `staging` → build automatico de RC
- Merge a `main` → build de release final

---

## Cloud Hub (Docker)

### Variables de Entorno

```bash
# Identificacion
HUB_ID=a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Conexion con Cloud
CLOUD_API_URL=https://erplora.com/api
CLOUD_API_TOKEN=jwt_token_del_hub

# Django
DEBUG=false
SECRET_KEY=auto_generated_or_from_env
ALLOWED_HOSTS=erplora.com
```

### Build Local (Docker)

```bash
docker build -t erplora/hub:latest .
docker run -d -p 8001:8000 -e HUB_ID=test-hub-123 erplora/hub:latest
```

### Volumenes Persistentes

```
/app/data/{HUB_ID}/
├── db/
│   └── db.sqlite3        # Base de datos
├── media/                # Archivos subidos
├── logs/                 # Logs
├── backups/              # Backups automaticos
└── temp/                 # Archivos temporales
```

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
| Autenticacion | LocalUser con PIN + JWT (Cloud API) |
| Deployment Cloud | Docker |
| Deployment Desktop | PyInstaller |

---

**Ultima actualizacion:** 2025-12-26
