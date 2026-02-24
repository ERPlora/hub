# ERPlora Hub

Sistema POS (Point of Sale) modular Django desplegado como **web application**.

## Modos de Despliegue

### 1. Local (Desarrollo)
- Django runserver con SQLite local
- Datos persisten en `~/Library/Application Support/ERPloraHub/` (macOS)
- Extensible con modules (gratuitos o de pago)

### 2. Cloud Hub (SaaS)
- Contenedor Docker
- SQLite en volumen persistente
- Acceso via subdominio: `{subdomain}.erplora.com`
- Planes de suscripcion

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
python manage.py runserver
```

El Hub corre en puerto **8000** por defecto (Cloud Portal usa 8001).

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
│   ├── settings/
│   │   ├── local.py         # Desarrollo local
│   │   └── web.py           # Docker/Cloud
│   ├── urls.py
│   └── module_allowed_deps.py
│
├── modules/                  # Modules instalados
│   ├── .template/           # Template base para nuevos modules
│   └── ...                  # Modules activos
│
├── templates/               # Django templates (@erplora/ux + HTMX)
├── static/                  # CSS/JS
├── Dockerfile               # Build para Cloud Hub
└── pyproject.toml           # Dependencias (uv)
```

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
docker run -d -p 8000:8000 -e HUB_ID=test-hub-123 erplora/hub:latest
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
| Backend | Django 5.2 |
| Database | SQLite |
| Frontend | UX CSS + Alpine.js + HTMX |
| Autenticacion | LocalUser con PIN + JWT (Cloud API) |
| Deployment | Docker |

---

## Licencia

ERPlora Hub esta licenciado bajo **Business Source License 1.1 (BUSL-1.1)**.

**Usos Permitidos (gratis):**
- Uso interno en negocios
- Uso personal y educativo
- Crear modules para el ecosistema
- Servicios de consultoria

**Usos Prohibidos:**
- Ofrecer como SaaS/PaaS
- Crear plataforma POS competidora
- Revender o sublicenciar

Despues del **2036-01-02**, se convierte en **Apache License 2.0**.
