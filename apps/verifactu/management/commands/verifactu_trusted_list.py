"""``manage.py verifactu_trusted_list [--file TSL.xml]``: renews the recognised authorities the app keeps
(``apps/verifactu/trusted_authorities.json``) from Spain's trusted list, downloaded from the Ministry
(``trusted_list.TSL_URL``) or read from a copy saved by hand. A person runs it and the new file goes in a reviewed
change; it never goes back to a list older than the one kept.
"""

import datetime as dt
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.verifactu import trust, trusted_list


class Command(BaseCommand):
    help = "Renews the recognised certification authorities from Spain's trusted list."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--file", default="", help="A trusted list saved by hand, instead of downloading it.")

    def handle(self, *args, **options) -> None:
        source = options["file"]
        try:
            xml = Path(source).read_bytes() if source else trusted_list.download(trusted_list.TSL_URL)
            read = trusted_list.read(xml, dt.datetime.now(dt.UTC))
        except (OSError, trusted_list.TrustedListInvalid) as failure:
            raise CommandError(f"The trusted list cannot be used: {failure}") from None
        kept = trust.kept().sequence
        if read["sequence"] < kept:
            raise CommandError(f"The trusted list nº {read['sequence']} is older than the one kept, nº {kept}.")
        trust.LIST_FILE.write_text(json.dumps(read, indent=1, ensure_ascii=False) + "\n")
        trust.kept.cache_clear()
        self.stdout.write(
            f"{len(read['authorities'])} recognised authorities from Spain's trusted list nº {read['sequence']} "
            f"(issued {read['issued_at']}, next update {read['next_update']})."
        )
