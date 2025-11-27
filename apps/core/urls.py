from django.urls import path
from . import views, views_update

app_name = 'core'

urlpatterns = [
    # Health check endpoint (for Docker healthcheck)
    path('health/', views.health_check, name='health_check'),

    path('', views.login, name='login'),
    path('verify-pin/', views.verify_pin, name='verify_pin'),
    path('cloud-login/', views.cloud_login, name='cloud_login'),
    path('setup-pin/', views.setup_pin, name='setup_pin'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('pos/', views.pos, name='pos'),
    path('settings/', views.settings, name='settings'),
    path('employees/', views.employees, name='employees'),
    path('logout/', views.logout, name='logout'),

    # Employee API endpoints
    path('api/employees/create/', views.api_employee_create, name='api_employee_create'),
    path('api/employees/update/', views.api_employee_update, name='api_employee_update'),
    path('api/employees/delete/', views.api_employee_delete, name='api_employee_delete'),
    path('api/employees/reset-pin/', views.api_employee_reset_pin, name='api_employee_reset_pin'),

    # Plugin Management
    path('plugins/', views.plugins, name='plugins'),

    # Plugin API endpoints
    path('api/plugins/install/', views.api_plugin_install, name='api_plugin_install'),
    path('api/plugins/activate/', views.api_plugin_activate, name='api_plugin_activate'),
    path('api/plugins/uninstall/', views.api_plugin_uninstall, name='api_plugin_uninstall'),
    path('api/plugins/list/', views.api_plugins_list, name='api_plugins_list'),

    # Update API endpoints
    path('api/update/check/', views_update.check_updates, name='update_check'),
    path('api/update/status/', views_update.update_status, name='update_status'),
    path('api/update/download/', views_update.download_update, name='update_download'),
    path('api/update/install/', views_update.install_update, name='update_install'),
    path('api/update/apply/', views_update.apply_update, name='update_apply'),
    path('api/update/rollback/', views_update.rollback_update, name='update_rollback'),
    path('api/update/notification/', views_update.update_notification, name='update_notification'),

    # FRP Client API endpoints - Moved to multi_device plugin
    # Access via /multi_device/frp/status/, /multi_device/frp/start/, etc.
]
