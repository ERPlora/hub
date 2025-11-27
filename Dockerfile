# ==============================================================================
# ERPlora Hub - Production Dockerfile
# ==============================================================================
# Single-stage optimized build for Cloud Hub deployments (Docker containers)
# Each Hub runs as an independent container with its own SQLite database
#
# VOLUMES (mount for persistence):
#   /app/db       - SQLite database
#   /app/media    - User uploads (images, logos)
#   /app/plugins  - Installed plugins
#   /app/logs     - Application logs
#   /app/backups  - Automatic backups
#
# ENVIRONMENT VARIABLES (injected by Coolify):
#   HUB_ID            - Unique Hub identifier (UUID)
#   CLOUD_API_URL     - Cloud API endpoint
#   CLOUD_API_TOKEN   - Hub authentication token
#   ALLOWED_HOSTS     - Comma-separated list of allowed hosts
#   SECRET_KEY        - Django secret key (auto-generated if not set)
#
# BUILD: docker build -t erplora/hub:latest .
# RUN:   docker run -p 8000:8000 -v hub_data:/app/db erplora/hub:latest
# ==============================================================================

FROM python:3.11-slim

# Labels for container metadata
LABEL org.opencontainers.image.title="ERPlora Hub"
LABEL org.opencontainers.image.description="Cloud Hub for ERPlora POS System"
LABEL org.opencontainers.image.vendor="ERPlora"
LABEL org.opencontainers.image.source="https://github.com/ERPlora/hub"

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Pip configuration
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # App configuration defaults
    DEPLOYMENT_MODE=web \
    DEBUG=False \
    ALLOWED_HOSTS=* \
    HUB_LOCAL_PORT=8000

WORKDIR /app

# Install system dependencies
# - build-essential: Required for compiling some Python packages
# - libusb-1.0-0: For USB device access (thermal printers, barcode scanners)
# - cups: For printing support (python-escpos)
# - curl: For healthcheck
# - libpq-dev: PostgreSQL client (future compatibility)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libusb-1.0-0 \
    cups \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install uv (fast Python package manager)
RUN pip install --no-cache-dir uv

# Copy only dependency files first (for better layer caching)
COPY pyproject.toml ./

# Install dependencies
# Note: We copy code after dependencies to leverage Docker layer caching
# Using --system to install directly (no venv needed in Docker)
# Note: Using sync instead of install for better reproducibility
RUN uv pip install --system --no-cache \
    Django>=5.2.7 \
    python-decouple>=3.8 \
    gunicorn>=21.0.0 \
    whitenoise>=6.6.0 \
    django-components>=0.123 \
    django-filter>=24.0 \
    djangorestframework>=3.15.0 \
    django-cors-headers>=4.0.0 \
    django-extensions>=3.2.0 \
    django-money>=3.0.0 \
    django-htmx>=1.17.0 \
    Pillow>=10.0.0 \
    qrcode>=7.4.0 \
    python-barcode>=0.15.0 \
    openpyxl>=3.1.0 \
    reportlab>=4.0.0 \
    PyPDF2>=3.0.0 \
    python-escpos>=3.0 \
    lxml>=5.0.0 \
    xmltodict>=0.13.0 \
    signxml>=3.2.0 \
    cryptography>=42.0.0 \
    zeep>=4.2.0 \
    requests>=2.31.0 \
    websockets>=12.0 \
    PyJWT>=2.8.0 \
    python-dateutil>=2.8.2 \
    pytz>=2024.1 \
    phonenumbers>=8.13.0 \
    stripe>=7.0.0 \
    pandas>=2.1.0 \
    numpy>=1.26.0 \
    pyserial>=3.5 \
    pyusb>=1.2.1 \
    email-validator>=2.1.0 \
    python-slugify>=8.0.0 \
    pydantic>=2.5.0 \
    beautifulsoup4>=4.12.0

# Copy application code
COPY . .

# Create necessary directories for volumes
# These will be mount points for persistent data
RUN mkdir -p /app/db /app/media /app/plugins /app/logs /app/backups /app/temp /app/staticfiles \
    && chmod -R 755 /app

# Collect static files
RUN python manage.py collectstatic --noinput --clear 2>/dev/null || true

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash hubuser \
    && chown -R hubuser:hubuser /app
USER hubuser

# Expose port
EXPOSE 8000

# Healthcheck using curl (more reliable than Python inline)
# Checks the /health/ endpoint every 30 seconds
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# Start script
# 1. Run migrations (create/update database schema)
# 2. Start gunicorn (production WSGI server)
CMD ["sh", "-c", "\
    echo '=== ERPlora Hub Starting ===' && \
    echo 'Running database migrations...' && \
    python manage.py migrate --noinput && \
    echo 'Starting Gunicorn server...' && \
    exec gunicorn config.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers 2 \
        --threads 4 \
        --worker-class gthread \
        --timeout 120 \
        --access-logfile - \
        --error-logfile - \
        --capture-output \
        --enable-stdio-inheritance \
    "]
