# ERPlora Hub - Docker Deployment

Guía para despliegue de Cloud Hubs usando Docker.

---

## 🎯 Build y Run

### Desarrollo Local

```bash
# Build imagen
docker build -t erplora/hub:dev .

# Run container
docker run -d \
  --name erplora-hub-dev \
  -p 8001:8000 \
  -v hub_dev_db:/app/db \
  -v hub_dev_media:/app/media \
  -v hub_dev_modules:/app/modules \
  -v $(pwd):/app \
  -e DEBUG=True \
  -e SECRET_KEY=docker-dev-secret-key \
  -e CLOUD_API_URL=https://int.erplora.com \
  -e DEPLOYMENT_MODE=web \
  -e ERPlora_DEV_MODE=true \
  erplora/hub:dev

# Ver logs
docker logs -f erplora-hub-dev

# Acceder
open http://localhost:8001
```

### Producción (Cloud Hub)

```bash
# Build imagen
docker build -t erplora/hub:latest .

# Run container
docker run -d \
  --name hub-{hub-id} \
  -p 7001:8000 \
  -v hub_{hub-id}_db:/app/db \
  -v hub_{hub-id}_media:/app/media \
  -v hub_{hub-id}_modules:/app/modules \
  -e DEBUG=False \
  -e SECRET_KEY=your-random-secret-key \
  -e CLOUD_API_URL=https://erplora.com \
  -e HUB_ID=your-hub-id \
  -e CLOUD_API_TOKEN=your-cloud-api-token \
  -e ALLOWED_HOSTS=erplora.com \
  erplora/hub:latest

# Ver logs
docker logs -f hub-{hub-id}

# Detener
docker stop hub-{hub-id}
docker rm hub-{hub-id}
```

---

## 📦 Volúmenes

| Volumen | Propósito | Crítico |
|---------|-----------|---------|
| `/app/db` | Base de datos SQLite | ✅ SÍ - Persistir datos |
| `/app/media` | Archivos subidos (logos, imágenes) | ✅ SÍ - Persistir archivos |
| `/app/modules` | Modules instalados | ✅ SÍ - Persistir modules |
| `/app/logs` | Logs de la aplicación | ⚠️ Opcional - Debugging |

**IMPORTANTE:** En producción (Dokploy), estos volúmenes deben ser persistentes.

---

## 🔧 Variables de Entorno

### Requeridas

```bash
# Django
SECRET_KEY=your-random-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com

# Cloud API
CLOUD_API_URL=https://erplora.com

# Hub credentials (se configuran después del primer login)
HUB_ID=uuid-del-hub
CLOUD_API_TOKEN=token-de-autenticacion-del-hub
```

### Opcionales

```bash
# Debug mode
DEBUG=False

# Deployment mode
DEPLOYMENT_MODE=web

# Logging
LOG_LEVEL=INFO

# Development features
ERPlora_DEV_MODE=false
MODULE_AUTO_RELOAD=false
```

---

## 🏥 Health Check

El contenedor expone un endpoint de health check:

```bash
# Desde dentro del contenedor
curl http://localhost:8000/health/

# Desde fuera
curl http://your-domain.com/health/
```

**Respuesta esperada:**
```json
{
  "status": "ok",
  "database": "ok",
  "version": "0.12.1"
}
```

---

## 🚀 Deployment con Dokploy

### 1. Preparar imagen

```bash
# Build y tag
docker build -t registry.erplora.com/hub:latest .

# Push a registry
docker push registry.erplora.com/hub:latest
```

### 2. Crear Cloud Hub via API

```python
# Cloud API endpoint
POST /api/hubs/deploy/

{
  "name": "Mi Tienda",
  "owner_id": "user-uuid",
  "plan": "starter",  # starter, business, enterprise
  "deployment_type": "cloud"
}

# Respuesta
{
  "hub_id": "abc-123-def",
  "docker_container_id": "container_xyz",
  "assigned_port": 7001,
  "url": "https://mi-tienda.erplora.com",
  "credentials": {
    "cloud_api_token": "token-secret"
  }
}
```

### 3. Dokploy crea contenedor

Dokploy ejecuta automáticamente:

```bash
docker run -d \
  --name hub-abc-123-def \
  -p 7001:8000 \
  -v hub_abc_123_def_db:/app/db \
  -v hub_abc_123_def_media:/app/media \
  -v hub_abc_123_def_modules:/app/modules \
  -e DEBUG=False \
  -e SECRET_KEY=auto-generated \
  -e CLOUD_API_URL=https://erplora.com \
  -e HUB_ID=abc-123-def \
  -e CLOUD_API_TOKEN=token-secret \
  -e ALLOWED_HOSTS=erplora.com \
  registry.erplora.com/hub:latest
```

### 4. Traefik enruta tráfico

```toml
# traefik.toml
[http.routers.hub-abc-123-def]
  rule = "Host(`erplora.com`) && PathPrefix(`/hubs/abc-123-def`)"
  service = "hub-abc-123-def"

[http.services.hub-abc-123-def.loadBalancer]
  [[http.services.hub-abc-123-def.loadBalancer.servers]]
    url = "http://localhost:7001"
```

---

## 🔍 Troubleshooting

### Container no arranca

```bash
# Ver logs detallados
docker logs erplora-hub

# Verificar healthcheck
docker inspect erplora-hub | grep -A 10 Health

# Entrar al container
docker exec -it erplora-hub bash

# Verificar base de datos
ls -lh /app/db/
```

### Migraciones no aplicadas

```bash
# Ejecutar manualmente
docker exec erplora-hub python manage.py migrate

# Ver estado de migraciones
docker exec erplora-hub python manage.py showmigrations
```

### Modules no cargan

```bash
# Listar modules instalados
docker exec erplora-hub ls -la /app/modules/

# Verificar permisos
docker exec erplora-hub chown -R 1000:1000 /app/modules/

# Logs de modules
docker exec erplora-hub python manage.py shell -c "from apps.core.runtime_manager import ModuleRuntimeManager; print(ModuleRuntimeManager().list_modules())"
```

### Puerto ya en uso

```bash
# Encontrar proceso usando el puerto
lsof -i :8001

# Usar otro puerto
docker run -p 8002:8000 ...
```

---

## 📊 Monitoreo

### Logs en tiempo real

```bash
docker logs -f erplora-hub
```

### Métricas del contenedor

```bash
# Stats en tiempo real
docker stats erplora-hub

# Uso de disco de volúmenes
docker system df -v
```

### Backup de datos

```bash
# Backup SQLite
docker exec erplora-hub python manage.py dumpdata > backup.json

# Backup volumen completo
docker run --rm -v hub_db:/data -v $(pwd):/backup alpine tar czf /backup/hub_db_backup.tar.gz /data
```

---

## 🔐 Seguridad

### Best Practices

1. **Nunca usar DEBUG=True en producción**
2. **SECRET_KEY único y random** (mínimo 50 caracteres)
3. **ALLOWED_HOSTS configurado correctamente** (no usar `*` en producción)
4. **Volúmenes con permisos restrictivos**
5. **Logs rotan automáticamente** (configurar logrotate)
6. **Health checks configurados** para auto-restart
7. **Backups automáticos** de SQLite diarios

### Generar SECRET_KEY

```python
# En local
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## 📚 Referencias

- **Dockerfile:** Single-stage optimizado con uv (sin venv, Docker ya es entorno aislado)
- **.dockerignore:** Optimización de build
- **docs/hub.md:** Arquitectura Hub
- **docs/cloud.md:** Cloud API y deployment
- **docs/PATHS.md:** Sistema de paths dinámicos Desktop/Docker

---

**Última actualización:** 2025-01-22
