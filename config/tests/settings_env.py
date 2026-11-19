"""The environments the settings tests import config.settings with, and every variable it reads."""

from pathlib import Path


SETTINGS_PACKAGE = "config.settings"
BASE_DIR = Path(__file__).resolve().parents[2]
ENV_KEYS = (
    "ASSISTANT_SERVER_VOICE",
    "DEBUG",
    "SECRET_KEY",
    "ALLOWED_HOSTS",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_MIGRATOR_USER",
    "DB_MIGRATOR_PASSWORD",
    "DB_HOST",
    "DB_PORT",
    "SAAS_URL",
    "SAAS_INTERNAL_URL",
    "INTERNAL_SHARED_SECRET",
    "DB_SSLMODE",
    "DB_SSLROOTCERT",
    "DB_APPLICATION_NAME",
    "PGBOUNCER_HOST",
    "PGBOUNCER_PORT",
    "DB_CONNECT_TIMEOUT",
    "SECURE_HSTS_SECONDS",
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    "SECURE_HSTS_PRELOAD",
    "VALKEY_URL",
    "LOG_LEVEL",
    "SES_REGION",
    "EMAIL_BACKEND",
    "EMAIL_HOST",
    "EMAIL_PORT",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
    "EMAIL_USE_TLS",
    "DEFAULT_FROM_EMAIL",
    "SHARED_DB_USER",
    "SHARED_DB_PASSWORD",
    "SHARED_DB_NAME",
    "APP_VERSION",
    "APP_RELEASED_AT",
    "WORKBOOK_TRANSLATION_MODEL",
    "TEST_DB_NAME",
    "ERPLORA_ENVIRONMENT",
    "HUB_BASE_DOMAIN",
    "FISCAL_CERTIFICATE_KEY",
    "FLOW_SECRETS_KEY",
    "VITE_DEV_PORT",
    "AWS_STORAGE_BUCKET_NAME",
    "AWS_REGION",
    "MEDIA_ROOT",
    "METRICS_ENABLED",
    "METER_ENABLED",
    "PGBOUNCER_MAX_DB_CONNECTIONS",
    "DB_CUT_WAIT_SECONDS",
)
# Local development opts in with DEBUG=True (the .env of a checkout); nothing else turns it on.
DEVELOPMENT_ENV = {"DEBUG": "True"}
PRODUCTION_ENV = {
    "DEBUG": "False",
    "SECRET_KEY": "from-the-environment",
    "SAAS_URL": "https://erplora.com",
    "INTERNAL_SHARED_SECRET": "shared-with-the-saas",
}
