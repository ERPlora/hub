# Hardware POS - Guía de Implementación

Esta guía explica cómo usar las librerías de hardware POS incluidas en CPOS Hub para conectar impresoras térmicas, scanners de códigos de barras, cajones de dinero, y otros dispositivos.

## 📦 Librerías Incluidas

### Core Hardware
- **`python-escpos>=3.0`** - Impresoras térmicas ESC/POS (USB/LAN/Serial)
- **`pyserial>=3.5`** - Puerto serial RS232 (cajón de dinero, displays)
- **`pyusb>=1.2.1`** - Dispositivos USB genéricos

### Platform-Specific
- **`evdev>=1.6.0`** (Linux) - Barcode scanners como HID keyboard
- **`pywinusb>=0.4.2`** (Windows) - USB HID devices

---

## 🖨️ Impresoras Térmicas ESC/POS

### Conexiones Soportadas

**USB, Network (LAN), Serial (RS232)**

### Ejemplo Básico

```python
from escpos.printer import Usb, Network, Serial

# === IMPRESORA USB ===
# Encontrar Vendor ID y Product ID con: lsusb (Linux) o Device Manager (Windows)
printer = Usb(0x04b8, 0x0e28)  # Ejemplo: Epson TM-T88V

# === IMPRESORA LAN (Ethernet) ===
printer = Network("192.168.1.100")  # IP de la impresora

# === IMPRESORA SERIAL ===
printer = Serial("/dev/ttyUSB0")  # Linux
printer = Serial("COM3")           # Windows

# Imprimir ticket básico
printer.text("CPOS Hub - Ticket de Venta\n")
printer.text("Fecha: 2025-01-10 14:30\n")
printer.text("=" * 32 + "\n")
printer.text("1x Producto A    $10.00\n")
printer.text("2x Producto B    $20.00\n")
printer.text("=" * 32 + "\n")
printer.text("TOTAL:           $30.00\n")
printer.cut()
```

### Ejemplo Avanzado - Ticket Completo

```python
from escpos.printer import Network
from escpos import printer as escpos_printer
from datetime import datetime
from django.conf import settings
from pathlib import Path

class TicketPrinter:
    """Wrapper para imprimir tickets POS"""

    def __init__(self, connection_type='network', **kwargs):
        """
        Args:
            connection_type: 'usb', 'network', 'serial'
            kwargs: Parámetros específicos de conexión
        """
        if connection_type == 'usb':
            self.printer = Usb(kwargs['vendor_id'], kwargs['product_id'])
        elif connection_type == 'network':
            self.printer = Network(kwargs['host'], kwargs.get('port', 9100))
        elif connection_type == 'serial':
            self.printer = Serial(kwargs['port'], kwargs.get('baudrate', 9600))
        else:
            raise ValueError(f"Unknown connection type: {connection_type}")

    def print_sale_ticket(self, sale):
        """Imprime ticket de venta"""
        # Header con logo (si existe)
        logo_path = Path(settings.STATIC_ROOT) / 'img' / 'logo.png'
        if logo_path.exists():
            self.printer.image(str(logo_path))

        # Información del negocio
        self.printer.set(align='center', text_type='B', width=2, height=2)
        self.printer.text("MI NEGOCIO\n")
        self.printer.set(align='center', text_type='normal')
        self.printer.text("Calle Falsa 123\n")
        self.printer.text("Tel: +1 234 567 890\n")
        self.printer.text("RFC: ABC123456XYZ\n")
        self.printer.text("\n")

        # Fecha y ticket number
        self.printer.set(align='left')
        self.printer.text(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.printer.text(f"Ticket: #{sale.id:06d}\n")
        self.printer.text(f"Cajero: {sale.cashier.get_full_name()}\n")
        self.printer.text("=" * 42 + "\n")

        # Items de venta
        self.printer.set(text_type='B')
        self.printer.text(f"{'Producto':<25} {'Cant':>5} {'Precio':>11}\n")
        self.printer.set(text_type='normal')
        self.printer.text("-" * 42 + "\n")

        for item in sale.items.all():
            # Nombre del producto (truncado si es largo)
            name = item.product.name[:25]
            qty = f"{item.quantity:>5}"
            price = f"${item.subtotal:>9.2f}"
            self.printer.text(f"{name:<25} {qty} {price}\n")

        self.printer.text("=" * 42 + "\n")

        # Totales
        self.printer.text(f"{'Subtotal:':<30} ${sale.subtotal:>9.2f}\n")
        if sale.tax > 0:
            self.printer.text(f"{'IVA (16%):':<30} ${sale.tax:>9.2f}\n")
        if sale.discount > 0:
            self.printer.text(f"{'Descuento:':<30} -${sale.discount:>9.2f}\n")

        self.printer.set(text_type='B', width=2, height=2)
        self.printer.text(f"{'TOTAL:':<15} ${sale.total:>9.2f}\n")
        self.printer.set(text_type='normal', width=1, height=1)

        # Método de pago
        self.printer.text("\n")
        self.printer.text(f"Pago: {sale.payment_method.upper()}\n")
        if sale.payment_method == 'cash':
            self.printer.text(f"Recibido:  ${sale.amount_paid:>9.2f}\n")
            self.printer.text(f"Cambio:    ${sale.change:>9.2f}\n")

        # QR Code (factura electrónica o URL)
        self.printer.text("\n")
        if sale.invoice_uuid:
            self.printer.set(align='center')
            self.printer.qr(sale.invoice_uuid, size=6)
            self.printer.text(f"\nUUID: {sale.invoice_uuid}\n")

        # Footer
        self.printer.text("\n")
        self.printer.set(align='center')
        self.printer.text("Gracias por su compra!\n")
        self.printer.text("www.minegocio.com\n")
        self.printer.text("\n")

        # Cortar papel
        self.printer.cut()

    def open_cash_drawer(self):
        """Abre cajón de dinero (pulso en pin 2/5)"""
        self.printer.cashdraw(2)  # Pin 2 (estándar)
        # self.printer.cashdraw(5)  # Pin 5 (alternativo)

# === USO EN VIEWS ===
from django.shortcuts import render
from django.http import JsonResponse
from .models import Sale

def print_ticket(request, sale_id):
    """Imprime ticket de venta"""
    sale = Sale.objects.get(id=sale_id)

    try:
        # Configuración desde settings o base de datos
        printer = TicketPrinter(
            connection_type='network',
            host='192.168.1.100'
        )

        printer.print_sale_ticket(sale)
        printer.open_cash_drawer()

        return JsonResponse({'success': True, 'message': 'Ticket impreso'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
```

### Detección Automática de Impresoras

```python
import usb.core
from escpos.printer import Usb

def find_pos_printers():
    """Encuentra todas las impresoras POS USB conectadas"""
    printers = []

    # Vendor IDs comunes de impresoras POS
    KNOWN_VENDORS = {
        0x04b8: 'Epson',
        0x0519: 'Star Micronics',
        0x0fe6: 'ICS Advent',
        0x20d1: 'Xprinter',
    }

    # Buscar dispositivos USB
    devices = usb.core.find(find_all=True)

    for dev in devices:
        if dev.idVendor in KNOWN_VENDORS:
            printers.append({
                'vendor_id': dev.idVendor,
                'product_id': dev.idProduct,
                'manufacturer': KNOWN_VENDORS[dev.idVendor],
                'product': usb.util.get_string(dev, dev.iProduct),
            })

    return printers

# Uso
printers = find_pos_printers()
for p in printers:
    print(f"Found: {p['manufacturer']} - {p['product']}")
    print(f"  VID: 0x{p['vendor_id']:04x}, PID: 0x{p['product_id']:04x}")
```

---

## 📟 Barcode Scanners

Los scanners de códigos de barras suelen conectarse como **teclado USB (HID)**, por lo que no necesitan configuración especial.

### Modo Estándar (Keyboard Wedge)

El scanner envía el código como si se escribiera en el teclado:

```html
<!-- Template Django -->
<input type="text"
       id="barcode-input"
       x-model="barcode"
       @input.debounce.500ms="searchProduct()"
       placeholder="Escanea código de barras..."
       autofocus>

<script>
function posData() {
    return {
        barcode: '',

        searchProduct() {
            if (!this.barcode) return;

            // Buscar producto por código de barras
            fetch(`/api/products/by-barcode/${this.barcode}/`)
                .then(r => r.json())
                .then(product => {
                    this.addToCart(product);
                    this.barcode = '';  // Limpiar para siguiente scan
                });
        }
    }
}
</script>
```

### Modo Avanzado (Linux - evdev)

Para capturar eventos del scanner directamente:

```python
from evdev import InputDevice, categorize, ecodes
import threading

class BarcodeScanner:
    """Captura códigos de barras desde dispositivo HID"""

    def __init__(self, device_path='/dev/input/event0'):
        self.device = InputDevice(device_path)
        self.barcode = ''
        self.running = False

    def start(self, callback):
        """
        Inicia captura de códigos de barras

        Args:
            callback: Función a llamar con cada código escaneado
        """
        self.running = True
        thread = threading.Thread(target=self._read_loop, args=(callback,))
        thread.daemon = True
        thread.start()

    def stop(self):
        """Detiene captura"""
        self.running = False

    def _read_loop(self, callback):
        """Loop de lectura de eventos"""
        for event in self.device.read_loop():
            if not self.running:
                break

            if event.type == ecodes.EV_KEY:
                key_event = categorize(event)

                # Solo procesar key press (value=1)
                if key_event.keystate == 1:
                    key = key_event.keycode

                    if key == 'KEY_ENTER':
                        # Código completo escaneado
                        if self.barcode:
                            callback(self.barcode)
                            self.barcode = ''
                    else:
                        # Agregar carácter al código
                        char = self._key_to_char(key)
                        if char:
                            self.barcode += char

    def _key_to_char(self, key):
        """Convierte keycode a carácter"""
        # Mapeo simplificado
        key_map = {
            'KEY_0': '0', 'KEY_1': '1', 'KEY_2': '2', 'KEY_3': '3',
            'KEY_4': '4', 'KEY_5': '5', 'KEY_6': '6', 'KEY_7': '7',
            'KEY_8': '8', 'KEY_9': '9',
            'KEY_A': 'A', 'KEY_B': 'B', 'KEY_C': 'C',
            # ... resto de letras
        }
        return key_map.get(key, '')

# Uso
def on_barcode_scanned(barcode):
    print(f"Barcode scanned: {barcode}")
    # Buscar producto y agregar al carrito
    product = Product.objects.filter(barcode=barcode).first()
    if product:
        print(f"Product found: {product.name}")

scanner = BarcodeScanner('/dev/input/event3')
scanner.start(callback=on_barcode_scanned)
```

### Detectar Scanner

```python
from evdev import InputDevice, list_devices

def find_barcode_scanner():
    """Encuentra scanner de códigos de barras"""
    devices = [InputDevice(path) for path in list_devices()]

    for device in devices:
        # Buscar dispositivos que sean teclados
        capabilities = device.capabilities()

        # Verificar si tiene capacidades de teclado
        if 1 in capabilities:  # EV_KEY
            if 'scanner' in device.name.lower() or 'barcode' in device.name.lower():
                return device.path

    return None

# Uso
scanner_path = find_barcode_scanner()
if scanner_path:
    print(f"Scanner found at: {scanner_path}")
else:
    print("No scanner found")
```

---

## 💰 Cajón de Dinero

El cajón de dinero se conecta a la impresora térmica y se controla enviando un pulso.

### Apertura con python-escpos

```python
from escpos.printer import Network

printer = Network("192.168.1.100")

# Abrir cajón (pulso en pin 2)
printer.cashdraw(2)

# O pin 5 (dependiendo del modelo)
printer.cashdraw(5)
```

### Apertura con Serial

```python
import serial

def open_cash_drawer(port='/dev/ttyUSB0'):
    """Abre cajón de dinero por puerto serial"""
    with serial.Serial(port, 9600, timeout=1) as ser:
        # Comando ESC/POS para abrir cajón
        # ESC p m t1 t2
        # m = pin (0 o 1), t1 = on time, t2 = off time
        command = b'\x1B\x70\x00\x32\xFA'
        ser.write(command)

open_cash_drawer()
```

---

## 📊 Display de Cliente (Pole Display)

Display secundario que muestra el precio al cliente.

### Ejemplo con Serial

```python
import serial

class PoleDisplay:
    """Display de cliente por puerto serial"""

    def __init__(self, port='/dev/ttyUSB1', baudrate=9600):
        self.ser = serial.Serial(port, baudrate, timeout=1)
        self.clear()

    def clear(self):
        """Limpia display"""
        self.ser.write(b'\x0C')  # Form feed

    def display_price(self, amount):
        """Muestra precio en el display"""
        self.clear()
        # Línea 1: "TOTAL"
        self.ser.write(b'TOTAL\r\n')
        # Línea 2: Precio
        price_str = f'${amount:,.2f}'
        self.ser.write(price_str.encode('ascii'))

    def display_item(self, name, price):
        """Muestra item en el display"""
        self.clear()
        # Línea 1: Nombre del producto (20 chars)
        name_line = name[:20].ljust(20)
        self.ser.write(name_line.encode('ascii') + b'\r\n')
        # Línea 2: Precio
        price_str = f'${price:,.2f}'
        self.ser.write(price_str.encode('ascii'))

    def display_welcome(self):
        """Mensaje de bienvenida"""
        self.clear()
        self.ser.write(b'   BIENVENIDO\r\n')
        self.ser.write(b'  A MI NEGOCIO')

# Uso en POS
display = PoleDisplay('/dev/ttyUSB1')

# Al agregar producto
display.display_item('Coca Cola 355ml', 15.00)

# Al finalizar compra
display.display_price(125.50)

# Entre transacciones
display.display_welcome()
```

---

## ⚖️ Báscula Electrónica

Báscula para pesar productos (carnicería, frutas, etc.).

### Ejemplo con Serial

```python
import serial
import struct

class Scale:
    """Báscula electrónica por puerto serial"""

    def __init__(self, port='/dev/ttyUSB2', baudrate=9600):
        self.ser = serial.Serial(port, baudrate, timeout=1)

    def read_weight(self):
        """Lee peso actual de la báscula"""
        # Enviar comando de lectura (depende del modelo)
        self.ser.write(b'W')  # Ejemplo: comando 'W' para leer peso

        # Leer respuesta
        response = self.ser.read(10)

        # Parsear respuesta (formato depende del modelo)
        # Ejemplo: "W+00.125kg\r\n"
        if response.startswith(b'W'):
            weight_str = response[2:8].decode('ascii')
            weight = float(weight_str)
            return weight

        return 0.0

    def tare(self):
        """Tarar báscula (poner en cero)"""
        self.ser.write(b'T')

# Uso
scale = Scale('/dev/ttyUSB2')

# Tarar antes de pesar
scale.tare()

# Leer peso
weight = scale.read_weight()
print(f"Weight: {weight} kg")

# En Django view
def weigh_product(request):
    scale = Scale('/dev/ttyUSB2')
    weight = scale.read_weight()

    # Calcular precio por peso
    product = Product.objects.get(id=request.POST['product_id'])
    price = product.price_per_kg * weight

    return JsonResponse({
        'weight': weight,
        'price': price
    })
```

---

## 🔧 Configuración y Troubleshooting

### Linux - Permisos USB

```bash
# Agregar usuario al grupo dialout (serial)
sudo usermod -a -G dialout $USER

# Recargar grupos
newgrp dialout

# Verificar dispositivos
ls -l /dev/ttyUSB*
ls -l /dev/input/event*

# Dar permisos temporales (testing)
sudo chmod 666 /dev/ttyUSB0
```

### Windows - Drivers USB

1. Instalar driver del fabricante de la impresora
2. Verificar puerto COM en Device Manager
3. Usar puerto COM correcto (ej: `COM3`)

### Detectar Dispositivos

```python
import serial.tools.list_ports

def list_serial_ports():
    """Lista todos los puertos seriales disponibles"""
    ports = serial.tools.list_ports.comports()

    for port in ports:
        print(f"Port: {port.device}")
        print(f"  Description: {port.description}")
        print(f"  Manufacturer: {port.manufacturer}")
        print(f"  VID:PID: {port.vid}:{port.pid}")
        print()

list_serial_ports()
```

---

## 📚 Referencias

- **python-escpos**: https://python-escpos.readthedocs.io/
- **pyserial**: https://pyserial.readthedocs.io/
- **pyusb**: https://github.com/pyusb/pyusb
- **evdev**: https://python-evdev.readthedocs.io/

---

**Última actualización:** 2025-01-10
