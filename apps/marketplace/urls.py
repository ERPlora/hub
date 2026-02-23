"""
Marketplace URLs

Mounted at /marketplace/ in config/urls.py

URL Structure:
/marketplace/                            -> marketplace:index (modules store)
/marketplace/solutions/                  -> marketplace:solutions (solution bundles)
/marketplace/solutions/<slug>/           -> marketplace:solution_detail
/marketplace/solutions/<slug>/install/   -> marketplace:solution_install (POST)
/marketplace/compliance/                 -> marketplace:compliance (country requirements)
/marketplace/compliance/<code>/          -> marketplace:compliance_detail
/marketplace/cart/                       -> marketplace:cart_page
/marketplace/<slug>/                     -> marketplace:module_detail (module detail page)

HTMX Endpoints:
/marketplace/products/              -> marketplace:products_list
/marketplace/filters/               -> marketplace:filters_view
/marketplace/cart/view/             -> marketplace:cart_view
/marketplace/cart/add/              -> marketplace:cart_add
/marketplace/cart/remove/<item_id>/ -> marketplace:cart_remove
/marketplace/cart/checkout/         -> marketplace:cart_checkout (POST)
/marketplace/cart/clear/            -> marketplace:cart_clear

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

    # Solutions
    path('solutions/', views.solutions_index, name='solutions'),
    path('solutions/<slug:slug>/install/', views.solution_install, name='solution_install'),
    path('solutions/<slug:slug>/', views.solution_detail, name='solution_detail'),

    # Compliance
    path('compliance/', views.compliance_index, name='compliance'),
    path('compliance/<str:country_code>/', views.compliance_detail, name='compliance_detail'),

    # Cart page
    path('cart/', views.cart_page, {'store_type': 'modules'}, name='cart_page'),

    # HTMX endpoints for modules (default store)
    path('products/', views.products_list, {'store_type': 'modules'}, name='products_list'),
    path('filters/', views.filters_view, {'store_type': 'modules'}, name='filters_view'),
    path('cart/view/', views.cart_view, {'store_type': 'modules'}, name='cart_view'),
    path('cart/add/', views.cart_add, {'store_type': 'modules'}, name='cart_add'),
    path('cart/checkout/', views.cart_checkout, {'store_type': 'modules'}, name='cart_checkout'),
    path('cart/remove/<str:item_id>/', views.cart_remove, {'store_type': 'modules'}, name='cart_remove'),
    path('cart/clear/', views.cart_clear, {'store_type': 'modules'}, name='cart_clear'),

    # Hubs store (legacy, still accessible)
    path('hubs/', views.store_index, {'store_type': 'hubs'}, name='store_hubs'),
    path('hubs/products/', views.products_list, {'store_type': 'hubs'}, name='hubs_products_list'),
    path('hubs/cart/', views.cart_page, {'store_type': 'hubs'}, name='hubs_cart_page'),

    # Module detail page (MUST be last - catches slugs)
    path('<slug:slug>/', views.module_detail, name='module_detail'),
]
