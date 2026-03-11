"""
Media Library views — upload, list, and browse shared images.

Endpoints (mounted at /htmx/media/):
- GET  list/         — HTMX partial: grid of uploaded images (filterable by folder)
- POST upload/       — Upload image, return JSON {id, url, name}
- GET  shared/       — HTMX partial: grid of shared blueprint assets
- GET  shared/folders/ — JSON list of shared asset folders
"""
import mimetypes

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import login_required
from apps.core.models import MediaFile


@login_required
def media_list(request):
    """Return grid of uploaded media files, optionally filtered by folder."""
    folder = request.GET.get('folder', '')
    search = request.GET.get('q', '')

    qs = MediaFile.objects.all()
    if folder:
        qs = qs.filter(folder=folder)
    if search:
        qs = qs.filter(name__icontains=search)

    files = qs[:60]
    folders = list(
        MediaFile.objects.exclude(folder='')
        .values_list('folder', flat=True)
        .distinct()
        .order_by('folder')
    )

    return render(request, 'core/media/grid.html', {
        'files': files,
        'folders': folders,
        'current_folder': folder,
        'search': search,
    })


@login_required
@require_POST
def media_upload(request):
    """Upload one or more images. Returns JSON with file info."""
    uploaded = request.FILES.getlist('file')
    if not uploaded:
        return JsonResponse({'error': 'No file provided'}, status=400)

    folder = request.POST.get('folder', '')
    results = []

    for f in uploaded:
        mime = f.content_type or mimetypes.guess_type(f.name)[0] or 'image/jpeg'

        # Get image dimensions
        width, height = 0, 0
        try:
            from PIL import Image
            img = Image.open(f)
            width, height = img.size
            f.seek(0)
        except Exception:
            pass

        media = MediaFile.objects.create(
            file=f,
            name=f.name,
            folder=folder,
            mime_type=mime,
            size=f.size,
            width=width,
            height=height,
        )
        results.append({
            'id': str(media.id),
            'url': media.url,
            'name': media.name,
            'size': media.size,
        })

    if len(results) == 1:
        return JsonResponse(results[0])
    return JsonResponse({'files': results})


@login_required
def shared_assets(request):
    """Return grid of shared blueprint assets from Cloud API."""
    folder = request.GET.get('folder', '')
    search = request.GET.get('q', '')

    cloud_url = getattr(settings, 'CLOUD_BASE_URL', 'https://erplora.com')

    # Fetch asset listing from Cloud
    assets = []
    try:
        import requests as http_requests
        params = {}
        if folder:
            params['folder'] = folder
        if search:
            params['q'] = search

        resp = http_requests.get(
            f'{cloud_url}/api/blueprints/assets/',
            params=params,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            assets = data.get('assets', [])
    except Exception:
        pass

    return render(request, 'core/media/shared_grid.html', {
        'assets': assets,
        'cloud_url': cloud_url,
        'current_folder': folder,
        'search': search,
    })


@login_required
def shared_folders(request):
    """Return JSON list of shared asset folder names."""
    cloud_url = getattr(settings, 'CLOUD_BASE_URL', 'https://erplora.com')

    folders = []
    try:
        import requests as http_requests
        resp = http_requests.get(
            f'{cloud_url}/api/blueprints/assets/folders/',
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            folders = data.get('folders', [])
    except Exception:
        pass

    return JsonResponse({'folders': folders})
