"""
URL patterns for roles management.
"""

from django.urls import path
from . import views, api

app_name = 'roles'

urlpatterns = [
    # List and create
    path('', views.role_list, name='list'),
    path('create/', views.role_create, name='create'),

    # Detail, edit, delete
    path('<uuid:role_id>/', views.role_detail, name='detail'),
    path('<uuid:role_id>/edit/', views.role_edit, name='edit'),
    path('<uuid:role_id>/delete/', views.role_delete, name='delete'),
    path('<uuid:role_id>/toggle-active/', views.role_toggle_active, name='toggle_active'),

    # Admin actions
    path('sync-permissions/', views.sync_permissions, name='sync_permissions'),
    path('create-defaults/', views.create_default_roles, name='create_defaults'),

    # API endpoints
    path('api/<uuid:role_id>/permissions/', api.update_role_permissions, name='api_permissions'),
    path('api/<uuid:role_id>/wildcard/', api.add_wildcard, name='api_add_wildcard'),
    path('api/<uuid:role_id>/wildcard/<str:wildcard>/', api.remove_wildcard, name='api_remove_wildcard'),

    # HTMX endpoints for UI
    path('api/<uuid:role_id>/module/<str:module_id>/toggle/', api.toggle_module, name='api_toggle_module'),
    path('api/<uuid:role_id>/permission/<path:codename>/toggle/', api.toggle_permission, name='api_toggle_permission'),
]
