from django.urls import path
from . import views_update

app_name = 'sync'

urlpatterns = [
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
