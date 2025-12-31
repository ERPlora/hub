"""
Module Management URLs (My Modules)

Mounted at /modules/ in config/urls.py

URL Structure:
/modules/                                   -> mymodules:index (My Modules)
/modules/marketplace/                       -> Redirects to /marketplace/modules/
/modules/marketplace/<slug>/                -> Redirects to /marketplace/modules/<slug>/

NOTE: The marketplace has been moved to /marketplace/ (see apps.marketplace)

API Structure:
/modules/api/activate/<id>/                 -> mymodules:api_activate
/modules/api/deactivate/<id>/               -> mymodules:api_deactivate
/modules/api/delete/<id>/                   -> mymodules:api_delete
/modules/api/restart/                       -> mymodules:api_restart
/modules/api/marketplace/                   -> mymodules:api_fetch
/modules/api/marketplace/purchase/          -> mymodules:api_purchase
/modules/api/marketplace/install/           -> mymodules:api_install
/modules/api/marketplace/ownership/         -> mymodules:api_ownership
"""
from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = 'mymodules'

urlpatterns = [
    # Main page (My Modules)
    path('', views.modules_index, name='index'),

    # Redirect old marketplace to new one
    path('marketplace/', RedirectView.as_view(url='/marketplace/modules/', permanent=False), name='marketplace'),
    path('marketplace/<slug:slug>/', RedirectView.as_view(url='/marketplace/modules/%(slug)s/', permanent=False), name='detail'),

    # HTMX partials
    path('htmx/list/', views.marketplace_modules_list, name='htmx_list'),

    # API endpoints
    path('api/activate/<str:module_id>/', views.module_activate, name='api_activate'),
    path('api/deactivate/<str:module_id>/', views.module_deactivate, name='api_deactivate'),
    path('api/delete/<str:module_id>/', views.module_delete, name='api_delete'),
    path('api/restart/', views.module_restart_server, name='api_restart'),
    path('api/marketplace/', views.fetch_marketplace, name='api_fetch'),
    path('api/marketplace/purchase/', views.purchase_module, name='api_purchase'),
    path('api/marketplace/install/', views.install_from_marketplace, name='api_install'),
    path('api/marketplace/ownership/<str:module_id>/', views.check_ownership, name='api_ownership'),
]
