# Global Configuration System

Sistema de configuración global del Hub usando patrón Singleton + Cache.

---

## Índice

- [Configuraciones Disponibles](#configuraciones-disponibles)
  - [HubConfig](#hubconfig)
  - [StoreConfig](#storeconfig)
- [Uso en Plugins](#uso-en-plugins)
  - [En Views (Python)](#en-views-python)
  - [En Templates (HTML)](#en-templates-html)
  - [En Modelos](#en-modelos)
  - [En Utilidades](#en-utilidades)
- [Ejemplos Completos](#ejemplos-completos)
- [Best Practices](#best-practices)

---

## Configuraciones Disponibles

### HubConfig

Configuración del Hub (credenciales, idioma, tema, moneda).

**Ubicación:** `apps.configuration.models.HubConfig`

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `hub_id` | UUIDField | `null` | ID único del Hub en Cloud |
| `cloud_api_token` | CharField | `''` | Token para autenticación HTTP con Cloud API |
| `is_configured` | BooleanField | `False` | Si el Hub ha completado configuración inicial |
| `os_language` | CharField | `'en'` | Idioma del sistema (detectado del OS) |
| `currency` | CharField | `'EUR'` | Moneda usada en transacciones |
| `color_theme` | CharField | `'default'` | Tema de color ('default', 'blue') |
| `dark_mode` | BooleanField | `False` | Modo oscuro activado |
| `auto_print` | BooleanField | `False` | Impresión automática de tickets |

**Opciones de currency:**
- 'USD' - US Dollar ($)
- 'EUR' - Euro (€) ← **Default**
- 'GBP' - British Pound (£)
- 'JPY' - Japanese Yen (¥)
- 'CNY' - Chinese Yuan (¥)
- 'MXN' - Mexican Peso ($)
- 'CAD' - Canadian Dollar ($)
- 'AUD' - Australian Dollar ($)
- 'BRL' - Brazilian Real (R$)
- 'ARS' - Argentine Peso ($)
- 'COP' - Colombian Peso ($)
- 'CLP' - Chilean Peso ($)
- 'PEN' - Peruvian Sol (S/)
- 'CRC' - Costa Rican Colón (₡)

**Acceso rápido:**
```python
from apps.configuration.models import HubConfig

# Obtener instancia completa
hub_config = HubConfig.get_solo()

# Obtener valor específico
currency = HubConfig.get_value('currency', 'EUR')
is_configured = HubConfig.get_value('is_configured', False)
dark_mode = HubConfig.get_value('dark_mode', False)
```

---

### StoreConfig

Configuración de la tienda (datos fiscales, recibos, impuestos).

**Ubicación:** `apps.configuration.models.StoreConfig`

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `business_name` | CharField | `''` | Nombre del negocio |
| `business_address` | TextField | `''` | Dirección del negocio |
| `vat_number` | CharField | `''` | NIF/CIF/VAT ID |
| `phone` | CharField | `''` | Teléfono de contacto |
| `email` | EmailField | `''` | Email de contacto |
| `website` | URLField | `''` | Sitio web |
| `logo` | ImageField | `null` | Logo del negocio |
| `tax_rate` | DecimalField | `0.00` | Tasa de impuesto en % (ej: 21.00 para 21%) |
| `tax_included` | BooleanField | `True` | Si los precios incluyen impuestos |
| `receipt_header` | TextField | `''` | Texto adicional en encabezado de recibos |
| `receipt_footer` | TextField | `''` | Texto adicional en pie de recibos |
| `is_configured` | BooleanField | `False` | Si la tienda ha completado configuración |

**Acceso rápido:**
```python
from apps.configuration.models import StoreConfig

# Obtener instancia completa
store_config = StoreConfig.get_solo()

# Obtener valores específicos
business_name = StoreConfig.get_value('business_name', 'My Store')
tax_rate = StoreConfig.get_value('tax_rate', 0.00)
tax_included = StoreConfig.get_value('tax_included', True)
```

---

## Uso en Plugins

### En Views (Python)

```python
# plugins/your_plugin/views.py
from apps.configuration.models import HubConfig, StoreConfig
from apps.accounts.decorators import login_required
from django.shortcuts import render

@login_required
def product_list(request):
    # Obtener configuraciones globales
    currency = HubConfig.get_value('currency', 'EUR')
    tax_rate = StoreConfig.get_value('tax_rate', 0.00)
    tax_included = StoreConfig.get_value('tax_included', True)
    business_name = StoreConfig.get_value('business_name', '')

    # Usar en lógica
    products = Product.objects.filter(is_active=True)

    # Opcional: Pasar al contexto (aunque ya está disponible vía context processor)
    context = {
        'products': products,
        'currency': currency,
        'tax_rate': tax_rate,
    }

    return render(request, 'your_plugin/list.html', context)
```

**Ejemplo completo - Dashboard de Inventario:**
```python
# plugins/_inventory/views.py
from apps.configuration.models import HubConfig
from django.db.models import Sum, F

@login_required
def dashboard(request):
    # Obtener moneda configurada
    currency = HubConfig.get_value('currency', 'EUR')

    # Calcular valor total del inventario
    total_inventory_value = Product.objects.filter(is_active=True).aggregate(
        total=Sum(F('stock') * F('price'))
    )['total'] or 0

    context = {
        'total_inventory_value': total_inventory_value,
        'currency': currency,  # Pasar para formateo específico
    }

    return render(request, 'inventory/index.html', context)
```

---

### En Templates (HTML)

Las configuraciones están disponibles **automáticamente** en todos los templates via context processor.

**Variables disponibles:**
- `{{ HUB_CONFIG }}` - Instancia completa de HubConfig
- `{{ STORE_CONFIG }}` - Instancia completa de StoreConfig

```django
<!-- plugins/your_plugin/templates/your_plugin/list.html -->
{% extends "app_base.html" %}

{% block content %}
<ion-header>
    <ion-toolbar>
        <ion-title>Products - {{ STORE_CONFIG.business_name }}</ion-title>
    </ion-toolbar>
</ion-header>

<ion-content>
    <ion-card>
        <ion-card-header>
            <ion-card-title>Inventory Value</ion-card-title>
        </ion-card-header>
        <ion-card-content>
            <!-- Acceso directo a campos -->
            <h2>{{ total_inventory_value }} {{ HUB_CONFIG.currency }}</h2>

            <!-- Condicionales -->
            {% if STORE_CONFIG.tax_included %}
                <p><small>Tax included ({{ STORE_CONFIG.tax_rate }}%)</small></p>
            {% else %}
                <p><small>Tax not included ({{ STORE_CONFIG.tax_rate }}%)</small></p>
            {% endif %}

            <!-- Información de negocio -->
            <p>{{ STORE_CONFIG.business_name }}</p>
            <p>{{ STORE_CONFIG.business_address }}</p>
            <p>VAT: {{ STORE_CONFIG.vat_number }}</p>
        </ion-card-content>
    </ion-card>

    <!-- Lista de productos con moneda -->
    <ion-list>
        {% for product in products %}
        <ion-item>
            <ion-label>
                <h3>{{ product.name }}</h3>
                <p>{{ product.price }} {{ HUB_CONFIG.currency }}</p>
            </ion-label>
        </ion-item>
        {% endfor %}
    </ion-list>
</ion-content>
{% endblock %}
```

**Ejemplo con Alpine.js:**
```django
<!-- plugins/your_plugin/templates/your_plugin/checkout.html -->
{% extends "app_base.html" %}

{% block content %}
<div x-data="checkoutData()">
    <ion-card>
        <ion-card-content>
            <ion-item>
                <ion-label>Subtotal</ion-label>
                <ion-note slot="end" x-text="formatCurrency(subtotal)"></ion-note>
            </ion-item>

            <ion-item>
                <ion-label>Tax ({{ STORE_CONFIG.tax_rate }}%)</ion-label>
                <ion-note slot="end" x-text="formatCurrency(taxAmount)"></ion-note>
            </ion-item>

            <ion-item>
                <ion-label><strong>Total</strong></ion-label>
                <ion-note slot="end" x-text="formatCurrency(total)"></ion-note>
            </ion-item>
        </ion-card-content>
    </ion-card>
</div>
{% endblock %}

{% block scripts %}
<script>
function checkoutData() {
    return {
        subtotal: 100.00,
        currency: '{{ HUB_CONFIG.currency }}',
        taxRate: {{ STORE_CONFIG.tax_rate }},
        taxIncluded: {{ STORE_CONFIG.tax_included|lower }},

        get taxAmount() {
            if (this.taxIncluded) {
                // Extraer impuesto del precio
                return this.subtotal - (this.subtotal / (1 + this.taxRate / 100));
            } else {
                // Calcular impuesto a añadir
                return this.subtotal * (this.taxRate / 100);
            }
        },

        get total() {
            return this.taxIncluded ? this.subtotal : this.subtotal + this.taxAmount;
        },

        formatCurrency(amount) {
            const symbols = {
                'EUR': '€',
                'USD': '$',
                'GBP': '£',
                'JPY': '¥',
                'CNY': '¥',
                'MXN': '$',
                'CAD': '$',
                'AUD': '$',
                'BRL': 'R$',
                'ARS': '$',
                'COP': '$',
                'CLP': '$',
                'PEN': 'S/',
                'CRC': '₡'
            };
            const symbol = symbols[this.currency] || this.currency;
            return `${symbol}${amount.toFixed(2)}`;
        }
    }
}
</script>
{% endblock %}
```

---

### En Modelos

```python
# plugins/your_plugin/models.py
from django.db import models
from apps.configuration.models import HubConfig, StoreConfig

class Product(models.Model):
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def get_formatted_price(self):
        """Retorna precio formateado con moneda configurada"""
        currency = HubConfig.get_value('currency', 'EUR')
        currency_symbols = {
            'EUR': '€', 'USD': '$', 'GBP': '£', 'JPY': '¥',
            'CNY': '¥', 'MXN': '$', 'CAD': '$', 'AUD': '$',
            'BRL': 'R$', 'ARS': '$', 'COP': '$', 'CLP': '$',
            'PEN': 'S/', 'CRC': '₡'
        }
        symbol = currency_symbols.get(currency, currency)
        return f"{symbol}{self.price:.2f}"

    def get_price_with_tax(self):
        """Calcula precio con impuesto según configuración de tienda"""
        tax_rate = StoreConfig.get_value('tax_rate', 0.00)
        tax_included = StoreConfig.get_value('tax_included', True)

        if tax_included:
            return self.price
        else:
            return self.price * (1 + tax_rate / 100)

    def get_tax_amount(self):
        """Calcula el monto de impuesto"""
        tax_rate = StoreConfig.get_value('tax_rate', 0.00)
        tax_included = StoreConfig.get_value('tax_included', True)

        if tax_included:
            # Extraer impuesto del precio
            return self.price - (self.price / (1 + tax_rate / 100))
        else:
            # Calcular impuesto a añadir
            return self.price * (tax_rate / 100)
```

---

### En Utilidades

Crear helpers reutilizables para formateo y cálculos:

```python
# plugins/your_plugin/utils.py
from apps.configuration.models import HubConfig, StoreConfig
from decimal import Decimal

def format_currency(amount):
    """Helper para formatear moneda según configuración"""
    currency = HubConfig.get_value('currency', 'EUR')

    # Símbolos de moneda
    symbols = {
        'EUR': '€', 'USD': '$', 'GBP': '£', 'JPY': '¥',
        'CNY': '¥', 'MXN': '$', 'CAD': '$', 'AUD': '$',
        'BRL': 'R$', 'ARS': '$', 'COP': '$', 'CLP': '$',
        'PEN': 'S/', 'CRC': '₡'
    }

    symbol = symbols.get(currency, currency)
    return f"{symbol}{amount:.2f}"

def calculate_tax(amount, include_tax=None):
    """
    Helper para calcular impuesto según configuración

    Args:
        amount: Monto base
        include_tax: Si None, usa configuración de StoreConfig

    Returns:
        tuple: (tax_amount, total_amount)
    """
    tax_rate = StoreConfig.get_value('tax_rate', 0.00)
    tax_included = StoreConfig.get_value('tax_included', True) if include_tax is None else include_tax

    amount = Decimal(str(amount))
    tax_rate_decimal = Decimal(str(tax_rate)) / 100

    if tax_included:
        # Extraer impuesto del precio
        tax_amount = amount - (amount / (1 + tax_rate_decimal))
        total_amount = amount
    else:
        # Calcular impuesto a añadir
        tax_amount = amount * tax_rate_decimal
        total_amount = amount + tax_amount

    return (tax_amount, total_amount)

def get_currency_symbol():
    """Obtiene símbolo de moneda configurada"""
    currency = HubConfig.get_value('currency', 'EUR')
    symbols = {
        'EUR': '€', 'USD': '$', 'GBP': '£', 'JPY': '¥',
        'CNY': '¥', 'MXN': '$', 'CAD': '$', 'AUD': '$',
        'BRL': 'R$', 'ARS': '$', 'COP': '$', 'CLP': '$',
        'PEN': 'S/', 'CRC': '₡'
    }
    return symbols.get(currency, currency)

def get_business_info():
    """Obtiene información completa del negocio"""
    return {
        'name': StoreConfig.get_value('business_name', ''),
        'address': StoreConfig.get_value('business_address', ''),
        'vat_number': StoreConfig.get_value('vat_number', ''),
        'phone': StoreConfig.get_value('phone', ''),
        'email': StoreConfig.get_value('email', ''),
        'website': StoreConfig.get_value('website', ''),
    }
```

**Uso de utilidades:**
```python
# plugins/your_plugin/views.py
from .utils import format_currency, calculate_tax, get_business_info

@login_required
def invoice(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)

    # Usar helpers
    subtotal = invoice.subtotal
    tax_amount, total = calculate_tax(subtotal)
    formatted_total = format_currency(total)
    business_info = get_business_info()

    context = {
        'invoice': invoice,
        'subtotal': subtotal,
        'tax_amount': tax_amount,
        'total': total,
        'formatted_total': formatted_total,
        'business_info': business_info,
    }

    return render(request, 'your_plugin/invoice.html', context)
```

---

## Ejemplos Completos

### Ejemplo 1: Dashboard de Ventas

```python
# plugins/sales/views.py
from apps.configuration.models import HubConfig, StoreConfig
from django.db.models import Sum, Count, F
from datetime import date

@login_required
def sales_dashboard(request):
    today = date.today()
    currency = HubConfig.get_value('currency', 'EUR')

    # Estadísticas del día
    today_sales = Sale.objects.filter(date=today)
    total_sales_today = today_sales.aggregate(
        total=Sum('total')
    )['total'] or 0

    count_sales_today = today_sales.count()

    context = {
        'total_sales_today': total_sales_today,
        'count_sales_today': count_sales_today,
        'currency': currency,
        'today': today,
    }

    return render(request, 'sales/dashboard.html', context)
```

```django
<!-- plugins/sales/templates/sales/dashboard.html -->
{% extends "app_base.html" %}

{% block content %}
<ion-header>
    <ion-toolbar>
        <ion-title>Sales Dashboard - {{ STORE_CONFIG.business_name }}</ion-title>
    </ion-toolbar>
</ion-header>

<ion-content>
    <ion-grid>
        <ion-row>
            <ion-col>
                <ion-card>
                    <ion-card-header>
                        <ion-card-subtitle>Today's Sales</ion-card-subtitle>
                        <ion-card-title>{{ total_sales_today }} {{ HUB_CONFIG.currency }}</ion-card-title>
                    </ion-card-header>
                    <ion-card-content>
                        {{ count_sales_today }} transactions
                    </ion-card-content>
                </ion-card>
            </ion-col>
        </ion-row>
    </ion-grid>
</ion-content>
{% endblock %}
```

---

### Ejemplo 2: Recibo de Venta

```python
# plugins/pos/views.py
from apps.configuration.models import StoreConfig

@login_required
def print_receipt(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)

    # Obtener configuración de recibos
    receipt_header = StoreConfig.get_value('receipt_header', '')
    receipt_footer = StoreConfig.get_value('receipt_footer', '')

    context = {
        'sale': sale,
        'receipt_header': receipt_header,
        'receipt_footer': receipt_footer,
    }

    return render(request, 'pos/receipt.html', context)
```

```django
<!-- plugins/pos/templates/pos/receipt.html -->
<div class="receipt">
    <!-- Header con logo y datos del negocio -->
    <div class="receipt-header">
        {% if STORE_CONFIG.logo %}
        <img src="{{ STORE_CONFIG.logo.url }}" alt="Logo">
        {% endif %}

        <h2>{{ STORE_CONFIG.business_name }}</h2>
        <p>{{ STORE_CONFIG.business_address }}</p>
        <p>VAT: {{ STORE_CONFIG.vat_number }}</p>
        <p>Tel: {{ STORE_CONFIG.phone }}</p>

        {% if receipt_header %}
        <p>{{ receipt_header }}</p>
        {% endif %}
    </div>

    <!-- Detalles de venta -->
    <div class="receipt-body">
        <table>
            {% for item in sale.items.all %}
            <tr>
                <td>{{ item.product.name }}</td>
                <td>{{ item.quantity }}</td>
                <td>{{ item.price }} {{ HUB_CONFIG.currency }}</td>
            </tr>
            {% endfor %}
        </table>

        <hr>

        <table>
            <tr>
                <td>Subtotal:</td>
                <td>{{ sale.subtotal }} {{ HUB_CONFIG.currency }}</td>
            </tr>
            {% if not STORE_CONFIG.tax_included %}
            <tr>
                <td>Tax ({{ STORE_CONFIG.tax_rate }}%):</td>
                <td>{{ sale.tax_amount }} {{ HUB_CONFIG.currency }}</td>
            </tr>
            {% endif %}
            <tr>
                <td><strong>Total:</strong></td>
                <td><strong>{{ sale.total }} {{ HUB_CONFIG.currency }}</strong></td>
            </tr>
        </table>

        {% if STORE_CONFIG.tax_included %}
        <p><small>Tax included ({{ STORE_CONFIG.tax_rate }}%)</small></p>
        {% endif %}
    </div>

    <!-- Footer -->
    <div class="receipt-footer">
        {% if receipt_footer %}
        <p>{{ receipt_footer }}</p>
        {% endif %}

        <p>Thank you for your purchase!</p>
        <p>{{ sale.created_at|date:"Y-m-d H:i" }}</p>
    </div>
</div>
```

---

## Best Practices

### ✅ DO

1. **Usar siempre configuraciones globales para:**
   - Moneda en precios y cálculos
   - Tasas de impuestos
   - Información del negocio en recibos
   - Preferencias de usuario (tema, idioma)

2. **Acceso eficiente:**
```python
# Bueno: Obtener solo el valor necesario
currency = HubConfig.get_value('currency', 'EUR')

# Bueno: Reutilizar instancia si necesitas varios campos
hub_config = HubConfig.get_solo()
currency = hub_config.currency
dark_mode = hub_config.dark_mode
```

3. **Siempre proporcionar defaults:**
```python
# Bueno: Con default
currency = HubConfig.get_value('currency', 'EUR')

# Malo: Sin default (puede retornar None)
currency = HubConfig.get_value('currency')
```

4. **En templates, usar variables globales:**
```django
<!-- Bueno: Usar HUB_CONFIG y STORE_CONFIG -->
<p>{{ product.price }} {{ HUB_CONFIG.currency }}</p>

<!-- Malo: Pasar manualmente al contexto -->
<p>{{ product.price }} {{ currency }}</p>
```

### ❌ DON'T

1. **NO hardcodear valores de configuración:**
```python
# Malo: Hardcoded
currency = 'EUR'

# Bueno: Desde configuración
currency = HubConfig.get_value('currency', 'EUR')
```

2. **NO hacer queries innecesarias:**
```python
# Malo: Query por cada valor
business_name = StoreConfig.get_solo().business_name
address = StoreConfig.get_solo().business_address  # 2 queries!

# Bueno: Una sola query
store_config = StoreConfig.get_solo()
business_name = store_config.business_name
address = store_config.business_address
```

3. **NO modificar configuración sin validación:**
```python
# Malo: Modificar directamente
hub_config = HubConfig.get_solo()
hub_config.currency = request.POST.get('currency')
hub_config.save()

# Bueno: Validar antes de guardar
currency = request.POST.get('currency', 'EUR')
from django.conf import settings
valid_currencies = [choice[0] for choice in settings.CURRENCY_CHOICES]
if currency in valid_currencies:
    HubConfig.set_value('currency', currency)
```

---

## Ventajas del Sistema

✅ **Acceso global**: Disponible en cualquier parte de la aplicación (views, templates, models)
✅ **Cache automático**: Alto rendimiento, sin queries repetidas (1 hora de duración)
✅ **Singleton pattern**: Solo una instancia en base de datos
✅ **Invalidación automática**: El caché se limpia al guardar cambios
✅ **Type-safe**: Con type hints para mejor autocompletado en IDE
✅ **Consistencia**: Misma configuración en toda la aplicación
✅ **Sin duplicación**: No necesitas pasar configuración en cada context

---

## Referencias

- Implementación completa: [`apps/configuration/models.py`](../apps/configuration/models.py)
- Documentación detallada: [`apps/configuration/README.md`](../apps/configuration/README.md)
- Context processor: [`apps/configuration/context_processors.py`](../apps/configuration/context_processors.py)
- Ejemplo en plugin: [`plugins/_inventory/views.py`](../plugins/_inventory/views.py)

---

**Última actualización:** 2025-01-23
