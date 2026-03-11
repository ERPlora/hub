"""
MediaFile — tracks uploaded images for the media picker.

Stores metadata about images uploaded by users. The actual files are stored
via Django's storage backend (local filesystem or S3 depending on deployment).

Shared images from blueprint assets are NOT stored here — they're served
directly from Cloud API and referenced by URL.
"""
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


def media_upload_to(instance, filename):
    """Organize uploads by folder: media/{folder}/{filename}"""
    folder = instance.folder or 'general'
    return f'media/{folder}/{filename}'


class MediaFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.ImageField(upload_to=media_upload_to)
    name = models.CharField(max_length=255, blank=True)
    folder = models.CharField(
        max_length=100, blank=True, default='',
        db_index=True,
        help_text=_('Folder for organization (e.g., "products", "staff")'),
    )
    mime_type = models.CharField(max_length=100, blank=True, default='')
    size = models.PositiveIntegerField(default=0, help_text=_('File size in bytes'))
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'core_mediafile'
        ordering = ['-created_at']

    def __str__(self):
        return self.name or self.file.name

    def save(self, *args, **kwargs):
        if not self.name and self.file:
            self.name = self.file.name.split('/')[-1]
        super().save(*args, **kwargs)

    @property
    def url(self):
        return self.file.url if self.file else ''

    @property
    def is_image(self):
        return self.mime_type.startswith('image/') if self.mime_type else True
