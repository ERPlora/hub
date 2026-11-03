"""``manage.py export_assistant_catalog --role <owner|admin|manager|employee> --language <en|es> [--apps a,b]``: the
assistant's tools a role holds, as JSON (``live.assistant_qa.export_catalog``), for layer 2 of the assistant's QA (docs
plan 2026-10-31, the assistant's knowledge and QA, §1.5): the QA with the real model reads it to write its own phrases
and to check which tool the model calls, which card a write shows and what the role is refused.

It names no business: the catalogue is a member's of a business with every app on (the e2e business ``a``), as a
chat turn builds it (``base.assistant.catalog``, with the role's permissions); ``--apps`` narrows it to those apps.
"""

import json

from django.core.management.base import BaseCommand, CommandError
from live.assistant_qa import export_catalog
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs
from live.operations import ASK_LANGUAGES

from base import assistant
from base.models import Membership
from base.permissions import permissions_of_role

ROLES = {
    "owner": Membership.Role.OWNER,
    "admin": Membership.Role.ADMIN,
    "manager": Membership.Role.MANAGER,
    "employee": Membership.Role.EMPLOYEE,
}
#: No business's: the catalogue is given its apps (``--apps`` or every one), so its scope is never read.
EXPORT_SCOPE = Scope("host", "export")


class Command(BaseCommand):
    help = "Prints the assistant's tools a role holds (every app on, or --apps), in a language, as JSON."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--role", required=True, choices=list(ROLES), help="The role whose tools are exported.")
        parser.add_argument(
            "--language", required=True, choices=list(ASK_LANGUAGES), help="The language of the asks exported."
        )
        parser.add_argument("--apps", default="", help="Comma-separated app labels (default: every app).")

    def handle(self, *args, role: str, language: str, apps: str, **options) -> None:
        labels = {config.label for config in all_live_app_configs()}
        chosen = {label.strip() for label in apps.split(",") if label.strip()}
        if unknown := sorted(chosen - labels):
            raise CommandError(f"Unknown app(s): {', '.join(unknown)}. The apps are: {', '.join(sorted(labels))}.")
        ctx = OperationContext(scope=EXPORT_SCOPE, actor=None, permissions=permissions_of_role(ROLES[role]),
                               language=language)
        tools = assistant.catalog(ctx, active_labels=chosen or labels)
        self.stdout.write(json.dumps(export_catalog(tools, language), ensure_ascii=False, indent=2))
