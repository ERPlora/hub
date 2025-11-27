# Sistema de Impresión Desacoplado

Sistema centralizado de impresión que permite a los plugins emitir eventos de impresión sin conocer la configuración de impresoras.

## 🎯 Objetivo

Desacoplar completamente los plugins de la gestión de impresoras. Los plugins solo necesitan emitir un evento de impresión, y el plugin `printers` se encarga de:

1. Seleccionar la impresora correcta según el tipo de documento
2. Formatear el documento con la configuración apropiada
3. Manejar reintentos, colas y errores
4. Notificar el resultado (éxito/fallo)

## 📐 Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                        PLUGINS (Desacoplados)                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Sales Plugin          Restaurant Plugin      Inventory Plugin  │
│      │                      │                       │            │
│      └──────────────────────┴───────────────────────┘            │
│                             │                                    │
│                             ▼                                    │
│                   print_helper.py                                │
│           (print_receipt, print_kitchen_order, etc.)             │
│                             │                                    │
└─────────────────────────────┼────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Django Signals  │
                    │   (Event Bus)    │
                    └──────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PRINTERS PLUGIN (Centralizado)                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  signal_handlers.py                                              │
│      │                                                           │
│      ├──> 1. Find Printer (by document type + priority)         │
│      ├──> 2. Prepare Data (merge config + data)                 │
│      ├──> 3. Print (via print_service)                          │
│      └──> 4. Emit Result (success/failure signal)               │
│                                                                  │
│  Printer Model:                                                  │
│    - document_types: ['receipt', 'invoice', 'kitchen_order']    │
│    - priority: 1-10 (lower = higher priority)                   │
│    - is_default: fallback printer                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                     ┌────────────────┐
                     │  Hardware      │
                     │  (Printers)    │
                     └────────────────┘
```

## 🚀 Uso desde Plugins

### Método 1: Usando Helper Functions (Recomendado)

```python
# En cualquier plugin
from apps.core.print_helper import print_receipt, print_delivery_note

# Imprimir recibo (no necesitas saber qué impresora)
print_receipt(
    receipt_id='SALE-123',
    items=[
        {'name': 'Product A', 'quantity': 2, 'price': 10.00, 'total': 20.00},
        {'name': 'Product B', 'quantity': 1, 'price': 30.00, 'total': 30.00},
    ],
    total=50.00,
    payment_method='Cash',
    paid=50.00,
    change=0.00
)

# Imprimir albarán
print_delivery_note(
    note_id='DN-456',
    items=[...],
    customer_name='John Doe'
)
```

### Método 2: Usando Señales Directamente

```python
from apps.core.signals import print_ticket_requested

# Emitir señal personalizada
print_ticket_requested.send(
    sender='my_plugin',
    ticket_type='custom_document',
    data={
        'receipt_id': 'DOC-789',
        'custom_field': 'value',
        # ... más datos
    },
    priority=8  # 10=máxima, 1=mínima
)
```

## 🔧 Configuración de Impresoras

### Tipos de Documento Soportados

| Tipo | Descripción | Prioridad Típica | Uso |
|------|-------------|------------------|-----|
| `receipt` | Recibos de venta | 8 (alta) | Ventas en POS |
| `delivery_note` | Albaranes de entrega | 7 | Albaranes antes de pagar |
| `invoice` | Facturas | 7 | Facturación |
| `kitchen_order` | Comandas de cocina | 10 (máxima) | Restaurantes |
| `barcode_label` | Etiquetas con código de barras | 5 (normal) | Inventario |
| `cash_session_report` | Cierre de caja | 5 (normal) | Caja |

### Configurar una Impresora

```python
# Crear impresora para recibos y albaranes
printer = Printer.objects.create(
    name='Impresora POS Principal',
    printer_type='network',
    system_printer_name='Brother_HL_3150CDW_series',
    paper_width=80,
    is_active=True,
    is_default=True,

    # Configurar tipos de documento que maneja
    document_types=['receipt', 'delivery_note'],

    # Prioridad (1=máxima, 10=mínima)
    priority=1
)

# Crear impresora para cocina
kitchen_printer = Printer.objects.create(
    name='Impresora Cocina',
    printer_type='escpos_network',
    paper_width=58,
    is_active=True,

    # Solo comandas de cocina
    document_types=['kitchen_order'],

    # Alta prioridad para cocina
    priority=1
)
```

### Múltiples Impresoras para el Mismo Tipo

Si hay múltiples impresoras que manejan el mismo tipo de documento, el sistema usa la de **menor `priority`** (número más bajo = mayor prioridad):

```python
# Impresora principal para recibos
Printer.objects.create(
    name='POS 1',
    document_types=['receipt'],
    priority=1  # ← Se usa esta primero
)

# Impresora backup para recibos
Printer.objects.create(
    name='POS 2 (Backup)',
    document_types=['receipt'],
    priority=5  # ← Se usa si la principal falla
)
```

## 🔍 Lógica de Selección de Impresora

El sistema busca la impresora en este orden:

1. **Impresora específica** (si se pasó `printer_id` en la señal)
2. **Impresora asignada al tipo de documento** con menor `priority`
3. **Impresora por defecto** (`is_default=True`)
4. **Primera impresora activa** disponible

```python
# Ejemplo de lógica de selección
def _find_printer_for_document(ticket_type, printer_id=None):
    # 1. Impresora específica
    if printer_id:
        return Printer.objects.get(id=printer_id, is_active=True)

    # 2. Impresora asignada al tipo (ordenada por priority)
    printers = Printer.objects.filter(
        is_active=True,
        document_types__contains=[ticket_type]
    ).order_by('priority')

    if printers.exists():
        return printers.first()

    # 3. Impresora por defecto
    return Printer.objects.get(is_default=True, is_active=True)

    # 4. Cualquier impresora activa
    return Printer.objects.filter(is_active=True).first()
```

## 📡 Señales Disponibles

### `print_ticket_requested` (Entrada)

**Emitida por**: Cualquier plugin que necesite imprimir
**Escuchada por**: Plugin `printers`

```python
print_ticket_requested.send(
    sender='sales',                    # Nombre del plugin
    ticket_type='receipt',             # Tipo de documento
    data={...},                        # Datos del documento
    printer_id=None,                   # Opcional: impresora específica
    priority=8                         # Prioridad (10=máxima)
)
```

### `print_completed` (Salida)

**Emitida por**: Plugin `printers`
**Escuchada por**: Plugin que inició la impresión

```python
@receiver(print_completed)
def on_print_success(sender, print_job_id, ticket_type, printer_name, **kwargs):
    print(f"✓ Impresión completada en {printer_name}")
```

### `print_failed` (Salida)

**Emitida por**: Plugin `printers`
**Escuchada por**: Plugin que inició la impresión

```python
@receiver(print_failed)
def on_print_error(sender, print_job_id, ticket_type, error, **kwargs):
    print(f"✗ Error al imprimir: {error}")
    # Mostrar mensaje al usuario, guardar en log, etc.
```

## 📝 Ejemplos Completos

### Ejemplo 1: Plugin de Ventas

```python
# plugins/sales/views.py
from apps.core.print_helper import print_receipt

def complete_sale(request):
    # Procesar venta...
    sale = Sale.objects.create(...)

    # Imprimir recibo (automáticamente va a la impresora correcta)
    print_receipt(
        receipt_id=f'SALE-{sale.id}',
        items=sale.items.all(),
        total=sale.total,
        payment_method=sale.payment_method,
        paid=sale.amount_paid,
        change=sale.change
    )

    return JsonResponse({'success': True})
```

### Ejemplo 2: Plugin de Restaurante

```python
# plugins/restaurant/views.py
from apps.core.print_helper import print_kitchen_order

def send_to_kitchen(request, order_id):
    order = Order.objects.get(id=order_id)

    # Imprimir en cocina (automáticamente va a impresora de cocina)
    print_kitchen_order(
        order_number=f'#{order.number}',
        table=order.table.name,
        items=[
            {
                'name': item.product.name,
                'quantity': item.quantity,
                'notes': item.notes
            }
            for item in order.items.all()
        ],
        waiter=order.waiter.name,
        priority='HIGH' if order.is_urgent else 'NORMAL'
    )

    return JsonResponse({'success': True})
```

### Ejemplo 3: Escuchar Resultados de Impresión

```python
# plugins/sales/apps.py
from django.apps import AppConfig
from django.dispatch import receiver
from apps.core.signals import print_completed, print_failed

class SalesConfig(AppConfig):
    def ready(self):
        @receiver(print_completed)
        def on_print_success(sender, ticket_type, printer_name, **kwargs):
            if ticket_type == 'receipt':
                # Marcar venta como impresa
                logger.info(f"Recibo impreso en {printer_name}")

        @receiver(print_failed)
        def on_print_error(sender, ticket_type, error, **kwargs):
            if ticket_type == 'receipt':
                # Mostrar error al usuario
                logger.error(f"Error al imprimir recibo: {error}")
                # Podríamos guardar en cola para reintentar más tarde
```

## ⚙️ Configuración Avanzada

### Prioridades por Tipo de Documento

```python
PRIORITY_BY_DOCUMENT_TYPE = {
    'kitchen_order': 10,      # Máxima prioridad
    'receipt': 8,             # Alta prioridad
    'delivery_note': 7,       # Alta prioridad
    'invoice': 7,             # Alta prioridad
    'cash_session_report': 5, # Normal
    'barcode_label': 5,       # Normal
}
```

### Configurar Impresora con Todos los Parámetros

```python
printer = Printer.objects.create(
    # Identificación
    name='Impresora POS Principal',
    printer_type='network',

    # Conexión
    system_printer_name='Brother_HL_3150CDW_series',
    connection_settings={},

    # Configuración de papel
    paper_width=80,  # 58 o 80 mm

    # Estado
    is_active=True,
    is_default=True,

    # Tipos de documento y prioridad
    document_types=['receipt', 'delivery_note', 'invoice'],
    priority=1,
)
```

## 🔒 Ventajas del Sistema

### ✅ **Desacoplamiento Total**
- Los plugins NO necesitan importar código del plugin de impresoras
- Los plugins NO necesitan saber qué impresora usar
- Se pueden desactivar/activar impresoras sin tocar código

### ✅ **Configuración Centralizada**
- Un solo lugar para configurar impresoras
- Fácil reasignar impresoras a diferentes tipos de documento
- UI de configuración en el plugin de impresoras

### ✅ **Escalabilidad**
- Múltiples impresoras para el mismo tipo de documento
- Sistema de prioridades para fallback automático
- Preparado para cola de impresión futura

### ✅ **Mantenibilidad**
- Cambios en impresión no afectan a otros plugins
- Helper functions simplifican el uso
- Logging centralizado de impresiones

### ✅ **Flexibilidad**
- Nuevos tipos de documento sin modificar código
- Plugins custom pueden definir sus propios tipos
- Sistema de señales permite extensiones

## 📊 Casos de Uso Reales

### Restaurante con Múltiples Zonas

```python
# Impresora para barra
bar_printer = Printer.objects.create(
    name='Impresora Barra',
    document_types=['kitchen_order'],
    priority=1
)

# Impresora para cocina
kitchen_printer = Printer.objects.create(
    name='Impresora Cocina',
    document_types=['kitchen_order'],
    priority=2  # Fallback si barra falla
)

# El plugin solo hace:
print_kitchen_order(order_number='#42', items=[...])
# → Se imprime automáticamente en barra (priority=1)
```

### Tienda con Facturación

```python
# Impresora térmica para recibos (58mm)
receipt_printer = Printer.objects.create(
    name='Térmica POS',
    paper_width=58,
    document_types=['receipt', 'delivery_note'],
    priority=1
)

# Impresora láser para facturas (A4)
invoice_printer = Printer.objects.create(
    name='Láser Oficina',
    paper_width=210,  # A4
    document_types=['invoice'],
    priority=1
)

# El plugin usa:
print_receipt(...)      # → Térmica 58mm
print_invoice(...)      # → Láser A4
```

## 🐛 Troubleshooting

### No se imprime nada

1. **Verificar que el plugin de impresoras está activo**
   ```bash
   # En logs debe aparecer:
   [PRINTERS] ✓ Plugin loaded with signal handlers
   ```

2. **Verificar que hay impresoras configuradas**
   ```python
   from printers.models import Printer
   Printer.objects.filter(is_active=True).count()  # Debe ser > 0
   ```

3. **Verificar logs de impresión**
   ```bash
   # Buscar en logs:
   [PRINT REQUEST] From: sales, Type: receipt
   [PRINTER SELECT] Using...
   [PRINT SUCCESS] o [PRINT FAILED]
   ```

### Impresora incorrecta

1. **Verificar document_types de la impresora**
   ```python
   printer = Printer.objects.get(name='Mi Impresora')
   print(printer.document_types)  # Debe incluir el tipo que estás imprimiendo
   ```

2. **Verificar prioridades**
   ```python
   Printer.objects.filter(
       document_types__contains=['receipt']
   ).order_by('priority')  # La primera es la que se usa
   ```

## 🚀 Roadmap Futuro

- [ ] **Cola de impresión** para reintentos automáticos
- [ ] **Modelo PrintJob** para tracking de trabajos
- [ ] **UI de historial** de impresiones
- [ ] **Webhooks** para notificar impresiones fallidas
- [ ] **Balanceo de carga** entre múltiples impresoras
- [ ] **Impresión remota** via cloud para Hubs desconectados
