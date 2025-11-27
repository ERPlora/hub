# ERPlora Hub - Sistema de Paths Dinámicos

Sistema inteligente de gestión de rutas que se adapta automáticamente al entorno de ejecución.

---

## 🎯 Problema Resuelto

El Hub necesita persistir datos (SQLite, media files, plugins) en ubicaciones diferentes según el entorno:

- **Desktop (PyInstaller):** Carpeta del usuario en el sistema operativo
- **Cloud (Docker):** Volúmenes Docker montados fuera del contenedor

El sistema detecta automáticamente el entorno y configura las rutas apropiadas.

---

## 🔍 Detección de Entorno

### Orden de Detección

```python
def is_docker_environment() -> bool:
    # 1. Variable de entorno DEPLOYMENT_MODE
    if config('DEPLOYMENT_MODE', default='local') == 'web':
        return True

    # 2. Archivo /.dockerenv (creado por Docker)
    if os.path.exists('/.dockerenv'):
        return True

    # 3. cgroup contiene 'docker' (Linux containers)
    with open('/proc/1/cgroup', 'r') as f:
        if 'docker' in f.read():
            return True

    return False  # Desktop
```

### Variables de Entorno

```bash
# Desktop (default)
DEPLOYMENT_MODE=local

# Docker
DEPLOYMENT_MODE=web
```

---

## 📁 Rutas por Entorno

### DOCKER (Cloud Hub)

```
/app/                          # Base (volumen montado)
├── db/
│   └── db.sqlite3            # Base de datos
├── media/                     # Archivos subidos
│   ├── logos/
│   ├── products/
│   └── plugins/
├── plugins/                   # Plugins instalados
│   ├── products/
│   ├── sales/
│   └── ...
├── logs/                      # Logs de aplicación
├── backups/                   # Backups automáticos
├── reports/                   # Reportes generados
└── temp/                      # Archivos temporales
```

**Docker run command:**
```bash
docker run -d \
  -v hub_db:/app/db \
  -v hub_media:/app/media \
  -v hub_plugins:/app/plugins \
  -e DEPLOYMENT_MODE=web \
  erplora/hub:latest
```

### DESKTOP (PyInstaller)

#### Windows

```
C:\Users\<usuario>\AppData\Local\ERPloraHub\
├── db\
│   └── db.sqlite3
├── media\
├── plugins\
├── logs\
├── backups\
├── reports\
└── temp\
```

#### macOS

```
/Users/<usuario>/Library/Application Support/ERPloraHub/
├── db/
│   └── db.sqlite3
├── media/
├── plugins/
├── logs/
├── backups/
├── reports/
└── temp/
```

#### Linux

```
/home/<usuario>/.cpos-hub/     # Carpeta oculta
├── db/
│   └── db.sqlite3
├── media/
├── plugins/
├── logs/
├── backups/
├── reports/
└── temp/
```

---

## 🔧 Uso en Código

### En Settings (Django)

```python
# hub/config/settings.py
from config.paths import get_data_paths

DATA_PATHS = get_data_paths()

# Base de datos
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DATA_PATHS.database_path,
    }
}

# Media files
MEDIA_ROOT = DATA_PATHS.media_dir
MEDIA_URL = 'media/'

# Plugins
PLUGINS_DIR = DATA_PATHS.plugins_dir
```

### En Código de Aplicación

```python
from config.paths import get_data_paths

data_paths = get_data_paths()

# Obtener rutas
db_path = data_paths.database_path
media_dir = data_paths.media_dir
plugins_dir = data_paths.plugins_dir

# Path de plugin específico
plugin_data = data_paths.get_plugin_data_dir('products')
plugin_media = data_paths.get_plugin_media_dir('products')

# Todas las rutas
all_paths = data_paths.get_all_paths()
for name, path in all_paths.items():
    print(f"{name}: {path}")
```

### API Simplificada

```python
# Helpers para uso rápido
from config.paths import (
    get_database_path,
    get_media_dir,
    get_plugins_dir,
    get_logs_dir,
    get_backups_dir,
)

db_path = get_database_path()
media = get_media_dir()
```

---

## 🧪 Testing y Debugging

### Verificar Configuración

```bash
cd hub

# Mostrar paths configurados
python -m config.paths
```

**Output ejemplo (Desktop macOS):**
```
======================================================================
ERPlora Hub - Path Configuration
======================================================================

Environment Detection:
  DEPLOYMENT_MODE:     local
  Is Docker:           False
  Platform:            darwin

Base directory:        /Users/ioan/Library/Application Support/ERPloraHub

All paths:
  ✓ EXISTS     base            -> /Users/ioan/Library/Application Support/ERPloraHub
  ✓ EXISTS     database_dir    -> /Users/ioan/Library/Application Support/ERPloraHub/db
  ✓ EXISTS     database        -> /Users/ioan/Library/Application Support/ERPloraHub/db/db.sqlite3
  ✓ EXISTS     media           -> /Users/ioan/Library/Application Support/ERPloraHub/media
  ✓ EXISTS     plugins         -> /Users/ioan/Library/Application Support/ERPloraHub/plugins
  ✗ MISSING    reports         -> /Users/ioan/Library/Application Support/ERPloraHub/reports
  ✓ EXISTS     logs            -> /Users/ioan/Library/Application Support/ERPloraHub/logs
  ✗ MISSING    backups         -> /Users/ioan/Library/Application Support/ERPloraHub/backups
  ✓ EXISTS     temp            -> /Users/ioan/Library/Application Support/ERPloraHub/temp

======================================================================
NOTES:
  Running on DESKTOP - using OS-specific user directory
  Data will persist in: /Users/ioan/Library/Application Support/ERPloraHub
======================================================================
```

**Output ejemplo (Docker):**
```
======================================================================
ERPlora Hub - Path Configuration
======================================================================

Environment Detection:
  DEPLOYMENT_MODE:     web
  Is Docker:           True
  Platform:            linux

Base directory:        /app

All paths:
  ✓ EXISTS     base            -> /app
  ✓ EXISTS     database_dir    -> /app/db
  ✓ EXISTS     database        -> /app/db/db.sqlite3
  ✓ EXISTS     media           -> /app/media
  ✓ EXISTS     plugins         -> /app/plugins
  ✓ EXISTS     reports         -> /app/reports
  ✓ EXISTS     logs            -> /app/logs
  ✓ EXISTS     backups         -> /app/backups
  ✓ EXISTS     temp            -> /app/temp

======================================================================
NOTES:
  Running in DOCKER - using /app as base
  Ensure volumes are mounted:
    -v hub_db:/app/db
    -v hub_media:/app/media
    -v hub_plugins:/app/plugins
======================================================================
```

---

## 🐳 Configuración Docker

### Dockerfile

El Dockerfile crea los directorios necesarios:

```dockerfile
# Crear directorios necesarios
RUN mkdir -p \
    /app/db \
    /app/media \
    /app/static \
    /app/logs \
    /app/plugins
```

### docker-compose.yml (ejemplo)

```yaml
services:
  hub:
    image: erplora/hub:latest
    volumes:
      - hub_db:/app/db
      - hub_media:/app/media
      - hub_plugins:/app/plugins
      - hub_logs:/app/logs
    environment:
      - DEPLOYMENT_MODE=web
      - HUB_ID=${HUB_ID}
      - CLOUD_API_TOKEN=${CLOUD_API_TOKEN}

volumes:
  hub_db:
    driver: local
  hub_media:
    driver: local
  hub_plugins:
    driver: local
  hub_logs:
    driver: local
```

---

## ⚠️ Consideraciones Importantes

### Persistencia en Docker

**CRÍTICO:** Los volúmenes Docker deben estar montados para que los datos persistan:

```bash
# ❌ SIN volúmenes - Los datos se pierden al recrear el contenedor
docker run erplora/hub:latest

# ✅ CON volúmenes - Los datos persisten
docker run \
  -v hub_db:/app/db \
  -v hub_media:/app/media \
  -v hub_plugins:/app/plugins \
  erplora/hub:latest
```

### Permisos en Docker

Los directorios se crean automáticamente con permisos correctos:

```python
def _ensure_directories(self):
    """Crea todos los directorios necesarios si no existen."""
    directories = [
        self.base_dir,
        self.database_dir,
        self.media_dir,
        self.plugins_dir,
        self.reports_dir,
        self.logs_dir,
        self.backups_dir,
        self.temp_dir,
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
```

### Migraciones entre Desktop y Cloud

**Los datos NO son compatibles directamente:**

- Desktop: SQLite en filesystem local
- Cloud: SQLite en volumen Docker

**Para migrar:**
1. Exportar datos: `python manage.py dumpdata > backup.json`
2. Subir a Cloud Hub
3. Importar datos: `python manage.py loaddata backup.json`

---

## 📚 Referencias

- **Código:** [hub/config/paths.py](../config/paths.py)
- **Settings:** [hub/config/settings.py](../config/settings.py)
- **Docker:** [hub/Dockerfile](../Dockerfile)
- **Documentación Docker:** [hub/DOCKER.md](DOCKER.md)

---

**Última actualización:** 2025-01-22
