from django.urls import path
from . import views
from . import views_plugins

app_name = 'configuration'

urlpatterns = [
    # Root redirect
    path('', views.index, name='index'),

    # Dashboard and POS
    path('dashboard/', views.dashboard, name='dashboard'),
    path('pos/', views.pos, name='pos'),

    # Settings
    path('settings/', views.settings, name='settings'),

    # Plugins Management
    path('plugins/', views_plugins.plugins_index, name='plugins'),
    path('plugins/activate/<str:plugin_id>/', views_plugins.plugin_activate, name='plugin_activate'),
    path('plugins/deactivate/<str:plugin_id>/', views_plugins.plugin_deactivate, name='plugin_deactivate'),
    path('plugins/delete/<str:plugin_id>/', views_plugins.plugin_delete, name='plugin_delete'),
]
