import json
import requests
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from .models import Plugin


def plugins(request):
    """
    Plugins management view - list installed and available plugins
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('accounts:login')

    from apps.plugins_runtime.loader import plugin_loader

    # Get all installed plugins
    installed_plugins = Plugin.objects.filter(is_installed=True).order_by('name')

    # Get discovered plugins (from filesystem)
    discovered = plugin_loader.discover_plugins()

    context = {
        'installed_plugins': installed_plugins,
        'discovered_count': len(discovered),
        'current_view': 'plugins'
    }
    return render(request, 'core/plugins.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def api_plugin_install(request):
    """
    API: Install plugin from uploaded ZIP file
    """
    try:
        # Check if file was uploaded
        if 'plugin_zip' not in request.FILES:
            return JsonResponse({'success': False, 'error': 'No file uploaded'})

        plugin_file = request.FILES['plugin_zip']

        # Validate file extension
        if not plugin_file.name.endswith('.zip'):
            return JsonResponse({'success': False, 'error': 'File must be a ZIP archive'})

        # Save uploaded file to temp directory (cross-platform)
        from apps.plugins_runtime.manager import plugin_runtime_manager

        # Use runtime manager's temp directory (works on Windows, macOS, Linux)
        tmp_file_path = plugin_runtime_manager.get_temp_file_path(plugin_file.name)

        # Write uploaded file to temp location
        with open(tmp_file_path, 'wb') as tmp_file:
            for chunk in plugin_file.chunks():
                tmp_file.write(chunk)

        # Install plugin using runtime manager
        # Note: The ZIP file is automatically deleted after extraction
        result = plugin_runtime_manager.install_plugin_from_zip(str(tmp_file_path))

        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def api_plugin_activate(request):
    """
    API: Activate/deactivate a plugin
    """
    try:
        data = json.loads(request.body)
        plugin_id = data.get('plugin_id')
        activate = data.get('activate', True)

        if not plugin_id:
            return JsonResponse({'success': False, 'error': 'Missing plugin_id'})

        from apps.plugins_runtime.loader import plugin_loader

        plugin = Plugin.objects.get(plugin_id=plugin_id)

        if activate:
            # Activate and load plugin
            plugin.is_active = True
            plugin.save()

            if plugin_loader.load_plugin(plugin_id):
                return JsonResponse({'success': True, 'message': f'Plugin {plugin_id} activated'})
            else:
                return JsonResponse({'success': False, 'error': 'Failed to load plugin'})
        else:
            # Deactivate plugin
            if plugin_loader.unload_plugin(plugin_id):
                return JsonResponse({'success': True, 'message': f'Plugin {plugin_id} deactivated'})
            else:
                return JsonResponse({'success': False, 'error': 'Failed to deactivate plugin'})

    except Plugin.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Plugin not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def api_plugin_uninstall(request):
    """
    API: Uninstall a plugin
    """
    try:
        data = json.loads(request.body)
        plugin_id = data.get('plugin_id')

        if not plugin_id:
            return JsonResponse({'success': False, 'error': 'Missing plugin_id'})

        from apps.plugins_runtime.manager import plugin_runtime_manager

        result = plugin_runtime_manager.uninstall_plugin(plugin_id)

        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["GET"])
def api_plugins_list(request):
    """
    API: List all plugins with their status
    """
    try:
        plugins = Plugin.objects.all().order_by('name')
        plugins_data = []

        for plugin in plugins:
            plugins_data.append({
                'plugin_id': plugin.plugin_id,
                'name': plugin.name,
                'description': plugin.description,
                'version': plugin.version,
                'author': plugin.author,
                'icon': plugin.icon,
                'category': plugin.category,
                'is_installed': plugin.is_installed,
                'is_active': plugin.is_active,
                'show_in_menu': plugin.show_in_menu,
                'menu_label': plugin.menu_label,
                'menu_icon': plugin.menu_icon,
                'menu_order': plugin.menu_order,
            })

        return JsonResponse({'success': True, 'plugins': plugins_data})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def marketplace(request):
    """
    Plugin marketplace view - browse and purchase plugins from Cloud
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('accounts:login')

    from apps.configuration.models import HubConfig

    hub_config = HubConfig.get_config()

    # Verificar que el Hub esté configurado
    if not hub_config.is_configured or not hub_config.cloud_api_token:
        context = {
            'error': 'Hub not configured. Please complete setup first.',
            'current_view': 'marketplace'
        }
        return render(request, 'plugins/marketplace.html', context)

    # Obtener plugins desde Cloud API
    api_url = f"{settings.CLOUD_API_URL}/api/plugins/"
    headers = {'X-Hub-Token': hub_config.cloud_api_token}

    try:
        # Obtener lista de plugins
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Obtener categorías
        categories_response = requests.get(
            f"{settings.CLOUD_API_URL}/api/plugins/categories/",
            headers=headers,
            timeout=10
        )
        categories_data = categories_response.json() if categories_response.ok else {'categories': []}

        # Obtener compras del usuario
        purchases_response = requests.get(
            f"{settings.CLOUD_API_URL}/api/plugins/my-purchases/",
            headers=headers,
            timeout=10
        )
        purchases_data = purchases_response.json() if purchases_response.ok else {'purchases': []}

        # Crear set de IDs de plugins comprados para fácil lookup
        purchased_plugin_ids = {p['plugin_id'] for p in purchases_data.get('purchases', [])}

        # Marcar plugins como comprados
        for plugin in data.get('results', []):
            plugin['is_purchased'] = plugin['id'] in purchased_plugin_ids

        context = {
            'plugins': data.get('results', []),
            'categories': categories_data.get('categories', []),
            'purchased_plugins': purchases_data.get('purchases', []),
            'current_view': 'marketplace'
        }

    except requests.exceptions.ConnectionError:
        context = {
            'error': 'Could not connect to Cloud. Please check your internet connection.',
            'current_view': 'marketplace'
        }
    except requests.exceptions.Timeout:
        context = {
            'error': 'Request timeout. Please try again later.',
            'current_view': 'marketplace'
        }
    except Exception as e:
        context = {
            'error': f'Error loading marketplace: {str(e)}',
            'current_view': 'marketplace'
        }

    return render(request, 'plugins/marketplace.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def api_create_checkout(request):
    """
    API: Create Stripe Checkout session for plugin purchase
    """
    try:
        from apps.configuration.models import HubConfig

        data = json.loads(request.body)
        plugin_id = data.get('plugin_id')

        if not plugin_id:
            return JsonResponse({'success': False, 'error': 'Missing plugin_id'})

        hub_config = HubConfig.get_config()

        if not hub_config.is_configured or not hub_config.cloud_api_token:
            return JsonResponse({'success': False, 'error': 'Hub not configured'})

        # Crear sesión de checkout en Cloud
        api_url = f"{settings.CLOUD_API_URL}/api/plugins/checkout/"
        headers = {
            'X-Hub-Token': hub_config.cloud_api_token,
            'Content-Type': 'application/json'
        }

        # Build success/cancel URLs
        success_url = request.build_absolute_uri('/plugins/marketplace/?purchase=success')
        cancel_url = request.build_absolute_uri('/plugins/marketplace/?purchase=cancelled')

        payload = {
            'plugin_id': plugin_id,
            'success_url': success_url,
            'cancel_url': cancel_url
        }

        response = requests.post(api_url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()

        return JsonResponse({
            'success': True,
            'checkout_url': result.get('checkout_url'),
            'session_id': result.get('session_id')
        })

    except requests.exceptions.RequestException as e:
        return JsonResponse({'success': False, 'error': f'Cloud API error: {str(e)}'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
def api_download_plugin_from_cloud(request):
    """
    API: Download plugin from Cloud and install it
    """
    try:
        from apps.configuration.models import HubConfig
        from apps.plugins_runtime.manager import plugin_runtime_manager

        data = json.loads(request.body)
        plugin_id = data.get('plugin_id')

        if not plugin_id:
            return JsonResponse({'success': False, 'error': 'Missing plugin_id'})

        hub_config = HubConfig.get_config()

        if not hub_config.is_configured or not hub_config.cloud_api_token:
            return JsonResponse({'success': False, 'error': 'Hub not configured'})

        # Download plugin from Cloud
        api_url = f"{settings.CLOUD_API_URL}/api/plugins/{plugin_id}/download/"
        headers = {'X-Hub-Token': hub_config.cloud_api_token}

        response = requests.get(api_url, headers=headers, timeout=30, stream=True)

        # Check if purchase is required
        if response.status_code == 402:
            return JsonResponse({
                'success': False,
                'error': 'Plugin not purchased',
                'requires_purchase': True
            })

        response.raise_for_status()

        # Save to temp file
        tmp_file_path = plugin_runtime_manager.get_temp_file_path(f'plugin_{plugin_id}.zip')

        with open(tmp_file_path, 'wb') as tmp_file:
            for chunk in response.iter_content(chunk_size=8192):
                tmp_file.write(chunk)

        # Install plugin
        result = plugin_runtime_manager.install_plugin_from_zip(str(tmp_file_path))

        return JsonResponse(result)

    except requests.exceptions.RequestException as e:
        return JsonResponse({'success': False, 'error': f'Download error: {str(e)}'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
