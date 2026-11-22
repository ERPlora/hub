"""The loads of a blueprint: what each brought and the rows it made, so that undoing it removes them."""

from django.db import models
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel


class ImportBatch(UUIDModel):
    """One load of a blueprint: what it was, its report and the rows it created, by dataset, so that undoing it
    removes exactly those.

    A hub's model, in the hub's own database like the business it loads. ``apps`` are the
    apps chosen to load (all the blueprint's when the person chose none); a retry names the load it retries.
    """

    class Source(models.TextChoices):
        CATALOG = "catalog", pgettext_lazy("blueprint source", "Template")
        FILE = "file", pgettext_lazy("blueprint source", "File")

    class Status(models.TextChoices):
        COMPLETE = "complete", pgettext_lazy("import status", "Complete")
        PARTIAL = "partial", pgettext_lazy("import status", "Partly loaded")
        FAILED = "failed", pgettext_lazy("import status", "Failed")

    name = models.CharField(pgettext_lazy("blueprint load", "name"), max_length=120)
    source = models.CharField(pgettext_lazy("blueprint load", "source"), max_length=16, choices=Source.choices)
    template_key = models.CharField(pgettext_lazy("blueprint load", "template"), max_length=80, blank=True)
    template_version = models.CharField(pgettext_lazy("blueprint load", "template version"), max_length=32, blank=True)
    purpose = models.CharField(pgettext_lazy("blueprint load", "purpose"), max_length=16)
    apps = models.JSONField(pgettext_lazy("blueprint load", "apps"), default=list, blank=True)
    status = models.CharField(pgettext_lazy("blueprint load", "status"), max_length=16, choices=Status.choices)
    report = models.JSONField(pgettext_lazy("blueprint load", "report"), default=dict, blank=True)
    created_rows = models.JSONField(pgettext_lazy("blueprint load", "rows created"), default=dict, blank=True)
    created_by = models.CharField(pgettext_lazy("blueprint load", "loaded by"), max_length=150, blank=True)
    created_at = models.DateTimeField(pgettext_lazy("blueprint load", "loaded at"), auto_now_add=True)
    undone_at = models.DateTimeField(pgettext_lazy("blueprint load", "undone at"), null=True, blank=True)
    retry_of = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=pgettext_lazy("blueprint load", "retry of")
    )

    class Meta:
        verbose_name = pgettext_lazy("blueprint load", "blueprint load")
        verbose_name_plural = pgettext_lazy("blueprint load", "blueprint loads")
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_status_display()})"
