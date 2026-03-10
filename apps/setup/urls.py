from django.urls import path

from . import views

app_name = 'setup'

urlpatterns = [
    path('', views.index, name='index'),
    path('region/', views.step_region, name='step_region'),
    path('business/', views.step_business, name='step_business'),
    path('business/types/', views.load_business_types, name='load_business_types'),
    path('info/', views.step_info, name='step_info'),
    path('tax/', views.step_tax, name='step_tax'),
    path('tax/load/', views.load_tax_preset, name='load_tax_preset'),
    path('finalize/', views.finalize, name='finalize'),
    path('complete/', views.complete, name='complete'),
]
