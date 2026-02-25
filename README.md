# ERPlora Hub

Modular POS (Point of Sale) system built with Django, deployed as a **web application**.

## Deployment Modes

### 1. Local (Development)
- Django runserver with local SQLite
- Data persists in `~/Library/Application Support/ERPloraHub/` (macOS)
- Extensible with modules (free or paid)

### 2. Cloud Hub (SaaS)
- Docker container
- SQLite on persistent volume
- Access via subdomain: `{subdomain}.erplora.com`
- Subscription plans

---

## Requirements (Local Development)

- Python 3.11+
- SQLite 3+ (included with Python)
- uv (Python package manager)

## Installation (Development)

```bash
cd hub

# Create virtual environment with uv
uv venv
source .venv/bin/activate  # Linux/macOS

# Install dependencies
uv pip install -e ".[dev]"

# Apply migrations
python manage.py migrate

# Development server
python manage.py runserver
```

The Hub runs on port **8000** by default (Cloud Portal uses 8001).

---

## Configuration

The Hub works **without any `.env` file** — all settings have sensible defaults.

Optionally, create a `hub/.env` to override specific variables. See `.env.example` for all available options.

### Key Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HUB_ENV` | `local` | Environment: `local`, `sandbox`, `web` |
| `CLOUD_API_URL` | `https://erplora.com` | Cloud URL (marketplace, sync) |
| `DATABASE_PATH` | auto (DataPaths) | Path to SQLite file |
| `MODULES_DIR` | auto (DataPaths) | Installed modules directory |
| `ERPLORA_DEV_MODE` | `true` | Relaxes module validation |
| `DEBUG_TOOLBAR` | `false` | Enables Django Debug Toolbar |
| `SECRET_KEY` | auto-generated | Django secret key |

### Default Paths (auto-detected per platform)

| Platform | Base Directory |
|----------|---------------|
| macOS | `~/Library/Application Support/ERPloraHub/` |
| Linux | `~/.erplora-hub/` |
| Docker | `/app/data/` |

Subdirectories: `db/`, `modules/`, `media/`, `logs/`, `backups/`, `reports/`

---

## Sandbox (Clean Environment)

For testing the setup wizard, module installation, or any flow that requires starting from scratch **without touching your development data**.

The sandbox uses a dedicated settings file (`config/settings/sandbox.py`) with isolated paths in `ERPloraHub-sandbox/`.

### How to use

```bash
cd hub
source .venv/bin/activate

# Start sandbox (wipes DB + modules, runs migrate, starts server)
HUB_ENV=sandbox python manage.py sandbox

# Custom port
HUB_ENV=sandbox python manage.py sandbox 8080

# Wipe + migrate only (no server)
HUB_ENV=sandbox python manage.py sandbox --no-run
```

### Behavior

- **First launch**: wipes DB and modules, runs migrate, starts server with auto-reload
- **Reloader restart** (after module install via setup wizard): runs migrate, loads new modules — NO wipe
- **Manual restart** (Ctrl+C + run `sandbox` again): wipes everything, starts fresh

Console output:

```
[SANDBOX] Wiped .../ERPloraHub-sandbox/db
[SANDBOX] Wiped .../ERPloraHub-sandbox/modules
[SANDBOX] Clean environment ready
[SANDBOX] Running migrations...
[SANDBOX] Migrations applied
[SANDBOX] Starting server on :8000
```

Your development data in `ERPloraHub/` is never touched.

---

## Project Structure

```
hub/
├── apps/                      # Django applications
│   ├── accounts/             # LocalUser, PIN authentication
│   ├── configuration/        # HubConfig, StoreConfig (singleton)
│   ├── modules_runtime/      # Dynamic module loading
│   ├── sync/                 # Cloud synchronization
│   └── core/                 # Shared utilities
│
├── config/                   # Django configuration
│   ├── settings/
│   │   ├── __init__.py      # Environment selector (HUB_ENV)
│   │   ├── base.py          # Common settings
│   │   ├── local.py         # Local development
│   │   ├── sandbox.py       # Sandbox (isolated testing)
│   │   └── web.py           # Docker/Cloud
│   ├── paths.py             # DataPaths (cross-platform paths)
│   └── urls.py
│
├── templates/               # Django templates (UX + HTMX)
├── static/                  # CSS/JS
├── .env                     # Local overrides (git-ignored, optional)
├── .env.example             # Variable reference
├── Dockerfile               # Build for Cloud Hub
└── pyproject.toml           # Dependencies (uv)
```

---

## Cloud Hub (Docker)

### Environment Variables (injected by Dokploy)

```bash
# Identification
HUB_ID=a1b2c3d4-e5f6-7890-abcd-ef1234567890
HUB_NAME=tienda-de-maria
DEPLOYMENT_MODE=web

# Cloud
CLOUD_BASE_URL=https://erplora.com
HUB_JWT=hub_jwt_token
PARENT_DOMAIN=erplora.com

# S3 Storage
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_STORAGE_BUCKET_NAME=erplora
AWS_S3_ENDPOINT_URL=https://fsn1.your-objectstorage.com

# Database (PostgreSQL for Hub plan, empty = SQLite)
DATABASE_URL=
```

### Local Docker Build

```bash
docker build -t erplora/hub:latest .
docker run -d -p 8000:8000 -e HUB_ID=test-hub-123 erplora/hub:latest
```

### Persistent Volumes

```
Host: ${VOLUME_PATH}/${HUB_ID}/ → Container: /app/data/
├── db/
│   └── db.sqlite3        # Database
└── modules/              # Installed modules
```

---

## Testing

```bash
pytest                              # All tests
pytest tests/unit                   # Unit tests only
pytest tests/integration            # Integration tests only
pytest --cov=apps --cov-report=html # With coverage
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Django 5.2 |
| Database | SQLite |
| Frontend | UX CSS + Alpine.js + HTMX |
| Icons | djicons |
| Auth | LocalUser with PIN + JWT (Cloud API) |
| Deployment | Docker (Dokploy) |

---

## License

ERPlora Hub is licensed under **Business Source License 1.1 (BUSL-1.1)**.

**Permitted uses (free):**
- Internal business use
- Personal and educational use
- Building modules for the ecosystem
- Consulting services

**Prohibited uses:**
- Offering as SaaS/PaaS
- Creating a competing POS platform
- Reselling or sublicensing

After **2036-01-02**, it converts to **Apache License 2.0**.
