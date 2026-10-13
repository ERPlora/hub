"""``manage.py register_apps [--check] [--force]``: the Hub's modules into the SaaS's ``shared`` schema.

Round 16 (PLAN §21; spec §4.2 and §4.3). The worker runs the same function before its loop (with
its tranche); until then, by hand. ``--check`` validates the registry without any database or
network (the image's build runs it); ``--force`` writes over a newer release, only for a
deliberate rollback. Any failure exits non-zero with the reason, and nothing is written.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from base import catalog


class Command(BaseCommand):
    help = "Register the Hub's modules (metadata, icon and documentation) in the SaaS's shared schema."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Validate the registry from the code alone (no database, no network) and stop.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Write even when a newer release registered its apps (a deliberate rollback only).",
        )

    def handle(self, *args, check: bool = False, force: bool = False, **options):
        if check:
            try:
                entries = catalog.build_registry()
            except catalog.CatalogError as error:
                raise CommandError(str(error)) from error
            labels = ", ".join(entry.id for entry in entries)
            self.stdout.write(f"{len(entries)} app(s) ready to register: {labels}")
            return
        try:
            result = catalog.register_apps(force=force)
        except (catalog.CatalogError, DatabaseError) as error:
            raise CommandError(f"register_apps: nothing written: {error}") from error
        if result.skipped:
            self.stdout.write(
                "A newer release already registered its apps: nothing written."
            )
            return
        self.stdout.write(
            f"{result.written} app(s) written ({', '.join(result.apps)}), {result.retired} retired, "
            f"{result.docs_changed} document(s) changed."
        )
