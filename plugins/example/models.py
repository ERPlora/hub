"""
Modelos del plugin Example Plugin

IMPORTANTE: Usa prefijos en db_table para evitar conflictos.
Por defecto Django usa: example_modelname
"""

from django.db import models
from django.conf import settings


# Ejemplo de modelo
# class Product(models.Model):
#     name = models.CharField(max_length=255)
#     price = models.DecimalField(max_digits=10, decimal_places=2)
#     created_at = models.DateTimeField(auto_now_add=True)
#     created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
#
#     class Meta:
#         db_table = 'example_product'  # Prefijo para evitar conflictos
#         ordering = ['-created_at']
#
#     def __str__(self):
#         return self.name
