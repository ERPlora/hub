"""
System Modules URLs

Module management and marketplace routes.
"""
from django.urls import path

from . import views

app_name = 'system'

urlpatterns = [
    # Pages (HTMX SPA)
    path('', views.modules_index, name='modules'),
    path('marketplace/', views.marketplace, name='marketplace'),
    path('marketplace/<slug:slug>/', views.module_detail, name='module_detail'),

    # HTMX partials (HTML responses)
    path('htmx/modules-list/', views.marketplace_modules_list, name='marketplace_modules_list'),

    # API endpoints (JSON)
    path('api/activate/<str:module_id>/', views.module_activate, name='module_activate'),
    path('api/deactivate/<str:module_id>/', views.module_deactivate, name='module_deactivate'),
    path('api/delete/<str:module_id>/', views.module_delete, name='module_delete'),
    path('api/restart/', views.module_restart_server, name='module_restart'),

    # Marketplace API
    path('api/marketplace/', views.fetch_marketplace, name='fetch_marketplace'),
    path('api/marketplace/purchase/', views.purchase_module, name='purchase_module'),
    path('api/marketplace/install/', views.install_from_marketplace, name='install_from_marketplace'),
    path('api/marketplace/ownership/<str:module_id>/', views.check_ownership, name='check_ownership'),
]
