"""
Marketplace URLs

Mounted at /marketplace/ in config/urls.py

URL Structure:
/marketplace/                            -> marketplace:index (modules store)
/marketplace/purchases/                  -> marketplace:my_purchases (owned modules)
/marketplace/business-types/             -> marketplace:business_types (informational)
/marketplace/business-types/<slug>/      -> marketplace:business_type_detail
/marketplace/compliance/                 -> marketplace:compliance (country requirements)
/marketplace/compliance/<code>/          -> marketplace:compliance_detail
/marketplace/<slug>/                     -> marketplace:module_detail (module detail page)

HTMX Endpoints:
/marketplace/products/              -> marketplace:products_list
/marketplace/filters/               -> marketplace:filters_view
/marketplace/purchase/              -> marketplace:module_purchase (POST)

Internal API (used by install flows):
/marketplace/solutions/bulk-install/     -> marketplace:solutions_bulk_install (POST)
/marketplace/solutions/<slug>/install/   -> marketplace:solution_install (POST)
/marketplace/solutions/<slug>/toggle/    -> marketplace:block_toggle (POST)

Legacy (hubs):
/marketplace/hubs/                  -> marketplace:store_hubs
/marketplace/hubs/products/         -> marketplace:hubs_products_list
"""
from django.urls import path

from . import views

app_name = 'marketplace'

urlpatterns = [
    # Root: modules store (default)
    path('', views.store_index, {'store_type': 'modules'}, name='index'),

    # Business Types (informational — modules & roles per business type)
    path('business-types/', views.business_types_index, name='business_types'),
    path('business-types/<slug:slug>/', views.business_type_detail, name='business_type_detail'),

    # Solutions
    path('solutions/bulk-install/', views.solutions_bulk_install, name='solutions_bulk_install'),
    path('solutions/<slug:slug>/install/', views.solution_install, name='solution_install'),
    path('solutions/<slug:slug>/toggle/', views.block_toggle, name='block_toggle'),
    path('solutions/<slug:slug>/', views.solution_detail, name='solution_detail'),

    # Compliance
    path('compliance/', views.compliance_index, name='compliance'),
    path('compliance/<str:country_code>/', views.compliance_detail, name='compliance_detail'),

    # My Purchases
    path('purchases/', views.my_purchases, name='my_purchases'),

    # HTMX endpoints for modules (default store)
    path('modules/bulk-install/', views.modules_bulk_install, name='modules_bulk_install'),
    path('products/', views.products_list, {'store_type': 'modules'}, name='products_list'),
    path('filters/', views.filters_view, {'store_type': 'modules'}, name='filters_view'),
    path('purchase/', views.module_purchase, name='module_purchase'),

    # Hubs store (legacy, still accessible)
    path('hubs/', views.store_index, {'store_type': 'hubs'}, name='store_hubs'),
    path('hubs/products/', views.products_list, {'store_type': 'hubs'}, name='hubs_products_list'),

    # Module detail page (MUST be last - catches slugs)
    path('<slug:slug>/', views.module_detail, name='module_detail'),
]
