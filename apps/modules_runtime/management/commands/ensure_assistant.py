"""
Ensure the AI assistant module is installed.

Deprecated: use `ensure_modules` instead, which restores ALL modules
(including assistant) on container startup. This command is kept for
backward compatibility and delegates to ensure_modules.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Ensure the AI assistant module is installed (delegates to ensure_modules)'

    def handle(self, *args, **options):
        self.stdout.write('Delegating to ensure_modules...')
        call_command('ensure_modules')
