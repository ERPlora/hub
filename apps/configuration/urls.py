from django.urls import path
from . import views

app_name = 'configuration'

urlpatterns = [
    # Dashboard and POS
    path('dashboard/', views.dashboard, name='dashboard'),
    path('pos/', views.pos, name='pos'),

    # Settings
    path('settings/', views.settings, name='settings'),
]
