"""The shell's icon registry as text, for the tests that check an icon is registered before an app names it."""

from pathlib import Path

from django.conf import settings

# The Ionicons are registered in icons.ts; the other Iconify sets (lucide:, mdi:…) in set-icons.ts.
REGISTRY = ("icons.ts", "set-icons.ts")


def shell_icon_registry() -> str:
    shell = Path(settings.BASE_DIR) / "packages/ui/src/shell"
    return "\n".join((shell / name).read_text() for name in REGISTRY)
