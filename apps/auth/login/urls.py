from django.urls import path
from . import views

app_name = 'auth'

urlpatterns = [
    # Auth pages
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('verify-pin/', views.verify_pin, name='verify_pin'),
    path('cloud-login/', views.cloud_login, name='cloud_login'),
    path('setup-pin/', views.setup_pin, name='setup_pin'),
    # Device trust (AWS auth)
    path('verify-device-trust/', views.verify_device_trust, name='verify_device_trust'),
    path('trust-device/', views.trust_device, name='trust_device'),
    path('revoke-device/', views.revoke_device, name='revoke_device'),
]
