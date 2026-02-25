"""
Management command: sandbox

Runs migrate and starts gunicorn with --reload (same server as production,
but with auto-reload so it survives wsgi.py touches after module installs).

The sandbox wipe happens in sandbox_run.py BEFORE Django loads (to avoid
SystemCheckErrors from partially-installed modules with missing deps).

Usage:
    HUB_ENV=sandbox python sandbox_run.py              # wipe + migrate + gunicorn (recommended)
    HUB_ENV=sandbox python sandbox_run.py 8080         # custom port
    HUB_ENV=sandbox python manage.py sandbox           # migrate + gunicorn (no wipe)
    HUB_ENV=sandbox python manage.py sandbox --no-run  # migrate only
"""

import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Migrate and start gunicorn for sandbox (requires HUB_ENV=sandbox)'

    def add_arguments(self, parser):
        parser.add_argument(
            'port', nargs='?', default='8000',
            help='Port for gunicorn (default: 8000)',
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

        # Migrate (DB was just wiped, needs fresh schema)
        self.stdout.write('[SANDBOX] Running migrations...')
        call_command('migrate', '--run-syncdb', verbosity=0)
        self.stdout.write(self.style.SUCCESS('[SANDBOX] Migrations applied'))

        if options['no_run']:
            return

        # Start gunicorn with --reload (same as production, survives file changes)
        port = options['port']
        self.stdout.write(f'[SANDBOX] Starting gunicorn on :{port} with --reload')

        gunicorn_bin = Path(sys.executable).parent / 'gunicorn'
        hub_dir = str(settings.BASE_DIR)

        cmd = [
            str(gunicorn_bin),
            'config.wsgi:application',
            '--bind', f'0.0.0.0:{port}',
            '--workers', '1',
            '--threads', '2',
            '--worker-class', 'gthread',
            '--timeout', '120',
            '--reload',
            '--reload-extra-file', str(Path(hub_dir) / 'config' / 'wsgi.py'),
            '--access-logfile', '-',
            '--error-logfile', '-',
        ]

        env = os.environ.copy()
        env['HUB_ENV'] = 'sandbox'
        env['DJANGO_SETTINGS_MODULE'] = 'config.settings'

        self.stdout.write(f'[SANDBOX] {" ".join(cmd)}')
        subprocess.run(cmd, cwd=hub_dir, env=env)
