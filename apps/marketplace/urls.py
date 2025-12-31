"""
Marketplace URLs

Mounted at /marketplace/ in config/urls.py

URL Structure:
/marketplace/                       -> marketplace:index (modules store - default)
/marketplace/hubs/                  -> marketplace:store_hubs (hubs store)
/marketplace/cart/                  -> marketplace:cart_page
/marketplace/<slug>/                -> marketplace:module_detail (module detail page)

HTMX Endpoints:
/marketplace/products/              -> marketplace:products_list (infinite scroll)
/marketplace/filters/               -> marketplace:filters_view
/marketplace/cart/view/             -> marketplace:cart_view
/marketplace/cart/add/              -> marketplace:cart_add
/marketplace/cart/remove/<item_id>/ -> marketplace:cart_remove
/marketplace/cart/clear/            -> marketplace:cart_clear

HTMX Endpoints (hubs):
/marketplace/hubs/products/         -> marketplace:hubs_products_list
"""
from django.urls import path

from . import views

app_name = 'marketplace'

urlpatterns = [
    # Root: modules store (default)
    path('', views.store_index, {'store_type': 'modules'}, name='index'),

    # Cart page
    path('cart/', views.cart_page, {'store_type': 'modules'}, name='cart_page'),

    # HTMX endpoints for modules (default store)
    path('products/', views.products_list, {'store_type': 'modules'}, name='products_list'),
    path('filters/', views.filters_view, {'store_type': 'modules'}, name='filters_view'),
    path('cart/view/', views.cart_view, {'store_type': 'modules'}, name='cart_view'),
    path('cart/add/', views.cart_add, {'store_type': 'modules'}, name='cart_add'),
    path('cart/remove/<str:item_id>/', views.cart_remove, {'store_type': 'modules'}, name='cart_remove'),
    path('cart/clear/', views.cart_clear, {'store_type': 'modules'}, name='cart_clear'),

    # Hubs store
    path('hubs/', views.store_index, {'store_type': 'hubs'}, name='store_hubs'),
    path('hubs/products/', views.products_list, {'store_type': 'hubs'}, name='hubs_products_list'),
    path('hubs/cart/', views.cart_page, {'store_type': 'hubs'}, name='hubs_cart_page'),

    # Module detail page (MUST be last - catches slugs)
    path('<slug:slug>/', views.module_detail, name='module_detail'),
]
