from django.urls import path
from . import views

app_name = 'plugins'

urlpatterns = [
    # Plugin Management
    path('plugins/', views.plugins, name='plugins'),

    # Plugin API endpoints
    path('api/plugins/install/', views.api_plugin_install, name='api_plugin_install'),
    path('api/plugins/activate/', views.api_plugin_activate, name='api_plugin_activate'),
    path('api/plugins/uninstall/', views.api_plugin_uninstall, name='api_plugin_uninstall'),
    path('api/plugins/list/', views.api_plugins_list, name='api_plugins_list'),
]
