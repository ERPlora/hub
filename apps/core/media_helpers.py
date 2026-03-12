"""
Media helpers — handle image assignment from media picker or file upload.

The media picker submits two fields:
- {field_name}_url: URL of a selected image (from library or shared)
- {field_name}: traditional file upload (if user uploaded directly)

Usage in views:
    from apps.core.media_helpers import handle_image_field

    handle_image_field(request, product, 'image')
"""
from django.core.files.base import ContentFile


def handle_image_field(request, instance, field_name):
    """
    Assign an image to a model instance from either:
    1. A direct file upload (request.FILES[field_name])
    2. A URL from the media picker (request.POST[field_name + '_url'])

    Returns True if the field was updated, False otherwise.
    """
    # Priority 1: direct file upload
    if field_name in request.FILES:
        setattr(instance, field_name, request.FILES[field_name])
        return True

    # Priority 2: URL from media picker
    url_field = f'{field_name}_url'
    url = request.POST.get(url_field, '').strip()

    if not url:
        return False

    # If it's a local media URL (same server), just store it
    # If it's an external URL (shared assets), download and store
    field = getattr(instance, field_name)

    if url.startswith(('http://', 'https://')):
        # External URL — download the image
        try:
            import requests as http_requests
            resp = http_requests.get(url, timeout=15)
            if resp.status_code == 200:
                filename = url.split('/')[-1].split('?')[0]
                if not filename:
                    filename = 'image.webp'
                field.save(filename, ContentFile(resp.content), save=False)
                return True
        except Exception:
            return False
    elif url.startswith('/media/') or url.startswith('media/'):
        # Local media URL — extract the relative path
        # The file already exists in storage, just update the field
        relative_path = url.lstrip('/')
        if relative_path.startswith('media/'):
            relative_path = relative_path[6:]  # strip 'media/'
        setattr(instance, field_name, relative_path)
        return True

    return False
