from django.urls import path
from . import views

# Note: This app's URLs are included under the 'main' namespace
# so we don't define app_name here

urlpatterns = [
    path('', views.index, name='settings'),
]
