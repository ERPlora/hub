from django.urls import path
from . import views

# Note: This app's URLs are included under the 'main' namespace

urlpatterns = [
    path('', views.index, name='employees'),

    # Employee API endpoints
    path('api/create/', views.api_create, name='employee_create'),
    path('api/update/', views.api_update, name='employee_update'),
    path('api/delete/', views.api_delete, name='employee_delete'),
    path('api/reset-pin/', views.api_reset_pin, name='employee_reset_pin'),
]
