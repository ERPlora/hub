"""
System Plugins URLs

Plugin management and marketplace routes.
"""
from django.urls import path

from . import views

app_name = 'system'

urlpatterns = [
    # Pages (HTMX SPA)
    path('', views.plugins_index, name='plugins'),
    path('marketplace/', views.marketplace, name='marketplace'),

    # HTMX partials (HTML responses)
    path('htmx/plugins-list/', views.marketplace_plugins_list, name='marketplace_plugins_list'),

    # API endpoints (JSON)
    path('api/activate/<str:plugin_id>/', views.plugin_activate, name='plugin_activate'),
    path('api/deactivate/<str:plugin_id>/', views.plugin_deactivate, name='plugin_deactivate'),
    path('api/delete/<str:plugin_id>/', views.plugin_delete, name='plugin_delete'),
    path('api/restart/', views.plugin_restart_server, name='plugin_restart'),

    # Marketplace API
    path('api/marketplace/', views.fetch_marketplace, name='fetch_marketplace'),
    path('api/marketplace/purchase/', views.purchase_plugin, name='purchase_plugin'),
    path('api/marketplace/install/', views.install_from_marketplace, name='install_from_marketplace'),
    path('api/marketplace/ownership/<str:plugin_id>/', views.check_ownership, name='check_ownership'),
]
