from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = _('Core')

    def ready(self):
        """Initialize core app when Django is ready."""
        self._setup_sqlite_pragmas()
        self._setup_module_icons()

    def _setup_sqlite_pragmas(self):
        """Optimize SQLite connections with PRAGMAs. Skipped for PostgreSQL."""
        from django.db.backends.signals import connection_created

        def _apply_pragmas(cursor):
            cursor.execute('PRAGMA journal_mode=WAL;')
            cursor.execute('PRAGMA synchronous=NORMAL;')
            cursor.execute('PRAGMA temp_store=MEMORY;')
            cursor.execute('PRAGMA cache_size=-20000;')
            cursor.execute('PRAGMA mmap_size=268435456;')

        def _on_connection(sender, connection, **kwargs):
            if connection.vendor != 'sqlite':
                return
            _apply_pragmas(connection.cursor())

        connection_created.connect(_on_connection)

        # Apply to any already-open connection
        from django.db import connection
        if connection.vendor == 'sqlite':
            _apply_pragmas(connection.cursor())

    def _setup_module_icons(self):
        """Register custom icons from installed modules."""
        from django.conf import settings

        try:
            from djicons.contrib.erplora import discover_module_icons
        except ImportError:
            return

        # Discover and register icons from modules
        modules_dir = getattr(settings, 'MODULES_DIR', None)
        if modules_dir and modules_dir.exists():
            discover_module_icons(modules_dir)
