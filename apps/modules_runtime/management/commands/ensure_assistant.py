"""
Ensure the AI assistant module is installed.

Runs on every hub startup. If the assistant module directory doesn't exist,
downloads and installs it from the Cloud marketplace (free module).
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Ensure the AI assistant module is installed (auto-install if missing)'

    def handle(self, *args, **options):
        modules_dir = Path(getattr(settings, 'MODULES_DIR', ''))
        if not modules_dir.exists():
            self.stdout.write('MODULES_DIR does not exist, skipping')
            return

        assistant_dir = modules_dir / 'assistant'
        if assistant_dir.exists():
            self.stdout.write('Assistant module already installed')
            return

        self.stdout.write('Assistant module not found, installing...')

        try:
            from apps.core.services.module_install_service import ModuleInstallService

            cloud_url = getattr(settings, 'CLOUD_API_URL', 'https://erplora.com')
            hub_token = ModuleInstallService.get_hub_token()

            modules_to_install = [{
                'slug': 'assistant',
                'name': 'AI Assistant',
                'download_url': f'{cloud_url}/api/marketplace/modules/assistant/download/',
            }]

            result = ModuleInstallService.bulk_download_and_install(
                modules_to_install, hub_token,
            )

            if result.installed > 0:
                self.stdout.write(self.style.SUCCESS('Assistant module installed successfully'))
                # Run migrations for the new module
                ModuleInstallService.run_post_install(
                    load_all=True, run_migrations=True, schedule_restart=False,
                )
            else:
                errors = result.errors or ['Unknown error']
                self.stdout.write(self.style.WARNING(f'Failed to install assistant: {errors}'))

        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Could not install assistant module: {e}'))
