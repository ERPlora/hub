"""
Download vendor assets (CSS/JS) from CDN to local static files.

Reads VENDOR_ASSETS from settings and downloads each file to the
configured path under STATICFILES_DIRS[0]. Run before collectstatic
so that vendor files are included in the static root.

Usage:
    python manage.py vendor_fetch
"""

import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Download vendor CSS/JS assets from CDN to local static files'

    def handle(self, *args, **options):
        assets = getattr(settings, 'VENDOR_ASSETS', [])
        if not assets:
            self.stdout.write(self.style.WARNING('No VENDOR_ASSETS defined in settings.'))
            return

        # First entry in STATICFILES_DIRS is the base static dir
        static_dir = Path(settings.STATICFILES_DIRS[0])
        if isinstance(settings.STATICFILES_DIRS[0], (list, tuple)):
            static_dir = Path(settings.STATICFILES_DIRS[0][1])

        downloaded = 0
        for asset in assets:
            url = asset['url']
            dest = static_dir / asset['path']
            dest.parent.mkdir(parents=True, exist_ok=True)

            self.stdout.write(f'  Downloading {url}')
            try:
                urllib.request.urlretrieve(url, dest)
                size_kb = dest.stat().st_size / 1024
                self.stdout.write(self.style.SUCCESS(f'  → {asset["path"]} ({size_kb:.0f} KB)'))
                downloaded += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'  ✗ Failed: {e}'))

        self.stdout.write(self.style.SUCCESS(f'\nDone: {downloaded}/{len(assets)} assets downloaded.'))
