"""
Management command: sandbox

Wipes the sandbox directories (DB + modules), runs migrate, and starts
the development server with auto-reload enabled.

- First launch: wipes DB + modules, runs migrate, starts server
- Reloader restart (after module install): runs migrate, starts server (NO wipe)
- Next manual launch (Ctrl+C + sandbox again): wipes everything again

Requires HUB_ENV=sandbox in .env (or as env var).

Usage:
    HUB_ENV=sandbox python manage.py sandbox           # wipe + migrate + runserver
    HUB_ENV=sandbox python manage.py sandbox 8080      # custom port
    HUB_ENV=sandbox python manage.py sandbox --no-run  # wipe + migrate only
"""

import os
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Wipe sandbox, migrate, and start dev server (requires HUB_ENV=sandbox)'

    def add_arguments(self, parser):
        parser.add_argument(
            'port', nargs='?', default='8000',
            help='Port for runserver (default: 8000)',
        )
        parser.add_argument(
            '--no-run', action='store_true',
            help='Only wipe and migrate, do not start the server',
        )

    def handle(self, *args, **options):
        if not getattr(settings, 'SANDBOX_MODE', False):
            self.stderr.write(self.style.ERROR(
                'Not in sandbox mode. Run with HUB_ENV=sandbox:\n'
                '  HUB_ENV=sandbox python manage.py sandbox'
            ))
            return

        # RUN_MAIN=true means this is a reloader restart (not a fresh launch)
        is_reloader = os.environ.get('RUN_MAIN') == 'true'

        if not is_reloader:
            # Fresh launch — wipe everything
            from django.db import connections
            for conn in connections.all():
                conn.close()

            db_path = Path(str(settings.DATABASES['default']['NAME']))
            db_dir = db_path.parent
            modules_dir = Path(str(settings.MODULES_DIR))

            for d in [db_dir, modules_dir]:
                if d.exists():
                    shutil.rmtree(d)
                    self.stdout.write(f'[SANDBOX] Wiped {d}')
                d.mkdir(parents=True, exist_ok=True)

            self.stdout.write(self.style.SUCCESS('[SANDBOX] Clean environment ready'))

        # Migrate (always — fresh DB or new module migrations)
        self.stdout.write('[SANDBOX] Running migrations...')
        call_command('migrate', '--run-syncdb', verbosity=0)
        self.stdout.write(self.style.SUCCESS('[SANDBOX] Migrations applied'))

        # Run server with reloader enabled
        if not options['no_run']:
            port = options['port']
            self.stdout.write(f'[SANDBOX] Starting server on :{port}')
            call_command('runserver', port)
