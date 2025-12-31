from django.urls import path
from . import views

# Note: This app's URLs are included under the 'main' namespace

urlpatterns = [
    path('', views.index, name='employees'),
    path('add/', views.add, name='employee_add'),
    path('<uuid:employee_id>/', views.edit, name='employee_edit'),
    path('<uuid:employee_id>/reset-pin/', views.reset_pin, name='employee_reset_pin'),
    path('<uuid:employee_id>/delete/', views.delete, name='employee_delete'),
]
