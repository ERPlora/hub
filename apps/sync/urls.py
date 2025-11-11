from django.urls import path
from . import views_update, views_frp

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

    # FRP Client API endpoints
    path('api/frp/status/', views_frp.frp_status, name='frp_status'),
    path('api/frp/start/', views_frp.frp_start, name='frp_start'),
    path('api/frp/stop/', views_frp.frp_stop, name='frp_stop'),
    path('api/frp/restart/', views_frp.frp_restart, name='frp_restart'),
]
