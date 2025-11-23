from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Authentication
    path('login/', views.login, name='login'),
    path('verify-pin/', views.verify_pin, name='verify_pin'),
    path('cloud-login/', views.cloud_login, name='cloud_login'),
    path('setup-pin/', views.setup_pin, name='setup_pin'),
    path('logout/', views.logout, name='logout'),

    # Employee Management
    path('employees/', views.employees, name='employees'),

    # Employee API endpoints
    path('api/employees/create/', views.api_employee_create, name='api_employee_create'),
    path('api/employees/update/', views.api_employee_update, name='api_employee_update'),
    path('api/employees/delete/', views.api_employee_delete, name='api_employee_delete'),
    path('api/employees/reset-pin/', views.api_employee_reset_pin, name='api_employee_reset_pin'),
]
