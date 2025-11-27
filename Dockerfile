# ERPlora Hub - Dockerfile
# Single-stage optimizado para Cloud Hub deployments (Docker containers)
# Mismo código Django que Desktop Hub (PyInstaller)

FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build dependencies
    build-essential \
    # Para impresoras térmicas USB/Serial
    libusb-1.0-0 \
    # Para python-escpos
    cups \
    && rm -rf /var/lib/apt/lists/*

# Instalar uv (gestor de paquetes rápido)
RUN pip install --no-cache-dir uv

# Copiar archivos de dependencias
COPY pyproject.toml ./

# Instalar dependencias directamente (sin venv, Docker ya es un entorno aislado)
RUN uv pip install --system --no-cache -e .

# Copiar código de la aplicación
COPY . .

# Crear directorios necesarios (montados como volúmenes)
RUN mkdir -p \
    /app/db \
    /app/media \
    /app/static \
    /app/logs \
    /app/plugins

# Variables de entorno por defecto (pueden ser sobreescritas)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBUG=False \
    DEPLOYMENT_MODE=web \
    HUB_LOCAL_PORT=8000 \
    ALLOWED_HOSTS=* \
    LOG_LEVEL=INFO

# Exponer puerto
EXPOSE 8000

# Healthcheck para monitoreo del contenedor
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health/', timeout=2)" || exit 1

# Comando de inicio con migraciones automáticas
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && python manage.py runserver 0.0.0.0:8000"]
