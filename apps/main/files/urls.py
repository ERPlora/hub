from django.urls import path
from . import views

# Note: This app's URLs are included under the 'main' namespace

urlpatterns = [
    path('', views.index, name='files'),
]
