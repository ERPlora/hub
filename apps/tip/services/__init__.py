"""Write operations of the tips app, one module per entity; importing each registers its operations."""

from apps.tip.services import drawer, reactions, settings, tips

__all__ = ["drawer", "reactions", "settings", "tips"]
