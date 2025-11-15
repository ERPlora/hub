# Example Plugin - Plugin de Ejemplo para CPOS Hub

**Versión:** 0.1.0
**Autor:** CPOS Team
**Descripción:** Plugin de ejemplo funcional que muestra cómo crear plugins para CPOS Hub.

---

## 📋 ¿Qué es este plugin?

Este plugin es un **ejemplo completo y funcional** que demuestra cómo crear plugins para CPOS Hub. Incluye:

✅ Estructura completa de archivos
✅ Página "Hello World" con Ionic components
✅ Ejemplo de Alpine.js para interactividad
✅ Modelo de datos comentado
✅ URLs configuradas
✅ Tests de ejemplo
✅ Documentación detallada

---

## 🚀 Instalación

Este plugin está incluido por defecto en el Hub para propósitos educativos.

### Activar el plugin:

1. Ir al dashboard del Hub
2. Navegar a "Plugins"
3. Activar "Example Plugin"
4. El plugin estará disponible en `/example/`

---

## 📁 Estructura del Plugin

```
example/
├── plugin.json              # Metadata del plugin (nombre, versión, deps)
├── __init__.py              # Package init
├── apps.py                  # Configuración Django del plugin
├── models.py                # Modelos de datos (ejemplo comentado)
├── views.py                 # Vistas del plugin
├── urls.py                  # URLs del plugin
├── templates/
│   └── example/
│       └── index.html       # Template con Ionic + Alpine.js
├── static/
│   └── example/
│       ├── css/            # CSS personalizado
│       ├── js/             # JavaScript adicional
│       └── img/            # Imágenes del plugin
├── migrations/
│   └── __init__.py         # Migraciones de base de datos
├── management/
│   └── commands/           # Management commands personalizados
├── tests/
│   ├── __init__.py
│   └── test_example.py     # Tests del plugin
├── README.md               # Este archivo
├── LICENSE                 # Licencia del plugin
└── .gitignore             # Archivos a ignorar

```

---

## 🔧 Desarrollo

### Requisitos previos

- Python 3.11+
- Django 5.1+
- CPOS Hub instalado

### Comandos útiles

```bash
# Activar entorno virtual
source .venv/bin/activate

# Crear migraciones (si agregaste modelos)
python manage.py makemigrations example

# Aplicar migraciones
python manage.py migrate example

# Ejecutar tests
pytest plugins/example/tests/

# Validar estructura del plugin
python manage.py validate_plugin example

# Empaquetar plugin para distribución
python manage.py package_plugin example

# Firmar plugin (para marketplace)
python manage.py sign_plugin example
```

---

## 📝 Crear un plugin desde cero

Usa este plugin como base para crear tus propios plugins:

### Opción 1: Copiar este plugin

```bash
# Copiar carpeta example
cp -r plugins/example plugins/mi-plugin

# Editar archivos:
# 1. plugin.json - Cambiar plugin_id, name, author
# 2. apps.py - Cambiar nombre de clase
# 3. Renombrar carpetas templates/example → templates/mi-plugin
# 4. Renombrar carpetas static/example → static/mi-plugin
```

### Opción 2: Usar comando create_plugin (futuro)

```bash
python manage.py create_plugin mi-plugin \
  --name "Mi Plugin" \
  --author "Tu Nombre" \
  --description "Descripción del plugin"
```

---

## 🎨 Componentes de UI

Este plugin usa:

- **Ionic 8**: Componentes UI profesionales
- **Alpine.js**: Reactividad ligera sin framework pesado
- **HTMX**: Interactividad sin escribir mucho JavaScript

### Ejemplo de componente Ionic:

```html
<ion-card>
  <ion-card-header>
    <ion-card-title>Título</ion-card-title>
  </ion-card-header>
  <ion-card-content>
    Contenido del card
  </ion-card-content>
</ion-card>
```

### Ejemplo de Alpine.js:

```html
<div x-data="{ count: 0 }">
  <ion-button @click="count++">
    Contador: <span x-text="count"></span>
  </ion-button>
</div>
```

---

## 📊 Modelos de Datos

Para crear modelos, edita `models.py`. **IMPORTANTE:** Usa prefijos en `db_table` para evitar conflictos:

```python
from django.db import models

class ExampleItem(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'example_item'  # Prefijo 'example_' es crucial
        ordering = ['-created_at']

    def __str__(self):
        return self.name
```

Después de crear modelos:

```bash
# Crear migración
python manage.py makemigrations example

# Aplicar migración
python manage.py migrate example
```

---

## 🔌 Dependencias

Los plugins pueden usar **25 librerías pre-empaquetadas** sin necesidad de pip.

### Librerías disponibles:

**Críticas:**
- `Pillow` - Imágenes
- `qrcode` - Códigos QR
- `python-barcode` - Códigos de barras
- `openpyxl` - Excel
- `reportlab` - PDFs
- `python-escpos` - Impresoras térmicas
- `lxml`, `xmltodict`, `signxml` - XML/Facturación
- `cryptography`, `zeep` - Seguridad y SOAP
- `requests`, `websockets` - HTTP/WebSocket

**Importantes:**
- `python-dateutil`, `pytz` - Fechas
- `phonenumbers` - Teléfonos
- `stripe` - Pagos
- `pandas`, `numpy` - Análisis
- `pyserial` - Hardware
- `email-validator`, `python-slugify`, `pydantic` - Utils

**Útiles:**
- `beautifulsoup4` - HTML parsing
- `PyPDF2` - PDF manipulación

### Declarar dependencias en plugin.json:

```json
{
  "dependencies": {
    "python": [
      "Pillow>=10.0.0",
      "qrcode>=7.4.0"
    ],
    "plugins": []
  }
}
```

---

## 🧪 Testing

Crea tests en `tests/test_example.py`:

```python
import pytest
from django.urls import reverse

@pytest.mark.django_db
def test_example_view(client):
    """Test que la vista principal funciona"""
    url = reverse('example:index')
    response = client.get(url)
    assert response.status_code == 200
```

Ejecutar tests:

```bash
# Todos los tests del plugin
pytest plugins/example/tests/

# Test específico
pytest plugins/example/tests/test_example.py::test_example_view

# Con coverage
pytest plugins/example/tests/ --cov=example
```

---

## 📚 Recursos

- [Documentación CPOS Plugins](../../docs/PLUGIN_ARCHITECTURE.md)
- [Ionic Components](https://ionicframework.com/docs/components)
- [Alpine.js Docs](https://alpinejs.dev)
- [HTMX Docs](https://htmx.org/docs/)

---

## 🤝 Contribuir

Si mejoras este plugin de ejemplo:

1. Fork el repositorio
2. Crea feature branch: `git checkout -b feature/mejora-example`
3. Commit cambios: `git commit -m "feat: añadir ejemplo de X"`
4. Push: `git push origin feature/mejora-example`
5. Crear Pull Request

---

## 📄 Licencia

Ver [LICENSE](LICENSE)

---

## ✍️ Autor

**CPOS Team**
Email: support@cpos.io
Website: https://cpos.io

---

**Última actualización:** 2025-01-14
