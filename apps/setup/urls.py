from django.urls import path
from . import views

app_name = 'setup'

urlpatterns = [
    path('', views.wizard, name='wizard'),
    path('step/<int:step>/', views.wizard_step, name='step'),
    path('install-modules/', views.install_modules, name='install_modules'),
]
