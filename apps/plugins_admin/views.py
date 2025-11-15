import json
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
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
