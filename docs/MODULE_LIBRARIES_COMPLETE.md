# Librerías Pre-empaquetadas para CPOS Hub - Lista Completa

## 🎯 Categorías de Funcionalidad

### 1️⃣ Imágenes & Media (Productos, Logos, etc)
```python
'Pillow>=10.0.0'              # Manipulación de imágenes (productos, categorías)
'qrcode>=7.4.0'               # QR codes (mesas, productos, pagos)
'python-barcode>=0.15.0'      # Códigos de barras (EAN, UPC, Code128)
'cairosvg>=2.7.0'             # SVG a PNG/PDF (logos, iconos)
```

**Casos de uso:**
- Productos con imágenes
- QR de mesas para restaurantes
- Códigos de barras de productos
- Logos en tickets

---

### 2️⃣ Office & Reportes (Excel, PDF, Word)
```python
'openpyxl>=3.1.0'             # Excel (import/export productos, inventarios)
'xlrd>=2.0.1'                 # Leer Excel antiguos (.xls)
'reportlab>=4.0.0'            # PDFs (tickets, reportes, facturas)
'PyPDF2>=3.0.0'               # Manipular PDFs existentes
'python-docx>=1.0.0'          # Word documents (reportes, contratos)
'weasyprint>=60.0'            # HTML a PDF (templates avanzados)
```

**Casos de uso:**
- Export/import de inventarios
- Tickets de venta en PDF
- Facturas profesionales
- Reportes contables

---

### 3️⃣ Impresión (Tickets, Facturas, Comandas)
```python
'python-escpos>=3.0'          # Impresoras térmicas (tickets POS)
'pywin32>=305'                # Windows printing (solo Windows)
'pycups>=2.0.1'               # CUPS printing (Linux/macOS)
'win32print'                  # Windows print spooler (incluido en pywin32)
```

**Casos de uso:**
- Tickets térmicos (58mm, 80mm)
- Impresión de comandas en cocina
- Facturas en impresora láser
- Etiquetas de productos

---

### 4️⃣ XML & Facturación Electrónica (Hacienda, SAT, AFIP)
```python
'lxml>=5.0.0'                 # XML parsing/generation (rápido y robusto)
'xmltodict>=0.13.0'           # XML a dict Python (fácil manejo)
'signxml>=3.2.0'              # Firmas digitales XML (facturas)
'cryptography>=42.0.0'        # Cifrado, certificados digitales
'pyOpenSSL>=24.0.0'           # SSL/TLS, certificados X.509
'zeep>=4.2.0'                 # SOAP web services (APIs de Hacienda)
```

**Casos de uso:**
- Facturación electrónica España (FacturaE)
- CFDi México (SAT)
- Factura electrónica Argentina (AFIP)
- Firmas digitales de documentos

**Ejemplo real:**
```xml
<!-- CFDi México (SAT) -->
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/3">
  <cfdi:Emisor Rfc="ABC123456789" Nombre="Mi Negocio"/>
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital /> <!-- Firma digital aquí -->
  </cfdi:Complemento>
</cfdi:Comprobante>
```

---

### 5️⃣ Networking & Tunneling (Acceso Remoto)
```python
'requests>=2.31.0'            # HTTP requests (APIs, webhooks)
'urllib3>=2.0.0'              # HTTP bajo nivel (incluido en requests)
'httpx>=0.25.0'               # HTTP async (más moderno que requests)
'websockets>=12.0'            # WebSocket cliente (notificaciones Cloud)
```

**Casos de uso:**
- WebSocket para notificaciones en tiempo real
- APIs de pagos (Stripe, PayPal)
- Webhooks de integraciones

---

### 6️⃣ Pagos & Stripe (Compra de Modules)
```python
'stripe>=7.0.0'               # Stripe payments (modules, suscripciones)
'paypalrestsdk>=1.13.1'       # PayPal payments
'braintree>=4.24.0'           # Braintree (PayPal/Venmo)
```

**Casos de uso:**
- Compra de modules desde el Hub
- Suscripciones mensuales
- Pagos de clientes (TPV integrado)

---

### 7️⃣ Data & Analysis (Reportes, Estadísticas)
```python
'pandas>=2.1.0'               # Análisis de datos (reportes avanzados)
'numpy>=1.26.0'               # Cálculos numéricos (márgenes, inventarios)
'openpyxl'                    # (ya listado arriba)
'tabulate>=0.9.0'             # Tablas ASCII/Markdown (reportes CLI)
```

**Casos de uso:**
- Reportes de ventas avanzados
- Análisis de inventario
- Cálculo de márgenes y rentabilidad
- Exportar a Excel con fórmulas

---

### 8️⃣ Bases de Datos & Almacenamiento
```python
'SQLAlchemy>=2.0.0'           # ORM avanzado (si modules necesitan BD custom)
'psycopg2-binary>=2.9.9'      # PostgreSQL (si modules usan Postgres)
'pymongo>=4.6.0'              # MongoDB (si modules necesitan NoSQL)
'redis>=5.0.0'                # Redis client (cache, sessions)
```

**Casos de uso:**
- Modules con modelos complejos
- Cache de datos (Redis)
- Sincronización con bases externas

**Nota:** Hub usa SQLite, pero algunos modules enterprise podrían necesitar Postgres.

---

### 9️⃣ Email & Notificaciones
```python
# Email ya incluido en Django (smtplib stdlib)
'python-magic>=0.4.27'        # Detectar tipos MIME (attachments)
'email-validator>=2.1.0'      # Validar emails
```

**Casos de uso:**
- Enviar tickets por email
- Notificaciones de bajo stock
- Reportes automáticos por email

---

### 🔟 Fechas, Horarios & Localización
```python
'python-dateutil>=2.8.2'      # Parsing de fechas flexible
'pytz>=2024.1'                # Timezones (importante para multi-país)
'phonenumbers>=8.13.0'        # Validar teléfonos internacionales
'Babel>=2.14.0'               # i18n, localización de números/fechas
```

**Casos de uso:**
- Manejo correcto de timezones
- Formateo de fechas según país
- Validación de teléfonos
- Traducción de números (1.000,00 vs 1,000.00)

---

### 1️⃣1️⃣ Hardware & Periféricos
```python
'pyserial>=3.5'               # Puerto serial (básculas, cajones, displays)
'pyusb>=1.2.1'                # USB devices (scanners, impresoras USB)
'hidapi>=0.14.0'              # HID devices (lectores RFID, NFC)
'evdev>=1.6.1'                # Input devices Linux (scanners como teclado)
```

**Casos de uso:**
- Báscula electrónica conectada
- Apertura de cajón de dinero
- Display de cliente
- Lectores de código de barras USB
- Lectores RFID/NFC

---

### 1️⃣2️⃣ Seguridad & Autenticación
```python
'cryptography>=42.0.0'        # (ya listado en XML)
'PyJWT>=2.8.0'                # JSON Web Tokens (ya lo usas)
'bcrypt>=4.1.0'               # Hashing de passwords (Django lo incluye)
'python-jose>=3.3.0'          # JWT con más algoritmos
```

**Casos de uso:**
- Tokens JWT para API
- Cifrado de datos sensibles
- Firmas digitales

---

### 1️⃣3️⃣ Scraping & Parsing (Importar de Web)
```python
'beautifulsoup4>=4.12.0'      # HTML parsing (importar catálogos web)
'html5lib>=1.1'               # Parser HTML5 robusto
'bleach>=6.1.0'               # Sanitizar HTML (seguridad)
```

**Casos de uso:**
- Importar catálogo de proveedor desde web
- Limpiar descripciones de productos
- Convertir HTML a texto plano

---

### 1️⃣4️⃣ Compresión & Archivos
```python
'zipfile'                     # ZIP (incluido en stdlib)
'tarfile'                     # TAR (incluido en stdlib)
'py7zr>=0.21.0'               # 7zip (si necesitas)
```

**Casos de uso:**
- Comprimir backups
- Descomprimir modules
- Export masivo de datos

---

### 1️⃣5️⃣ Utils & Helpers
```python
'python-slugify>=8.0.0'       # URLs amigables (slug de productos)
'humanize>=4.9.0'             # Números human-friendly (hace 2 horas)
'arrow>=1.3.0'                # Fechas human-friendly (alternativa a dateutil)
'click>=8.1.0'                # CLI tools (si modules tienen comandos)
'pydantic>=2.5.0'             # Validación de datos (mejor que forms Django)
'python-dotenv>=1.0.0'        # .env files (ya usas python-decouple)
```

**Casos de uso:**
- URLs limpias de productos
- Fechas amigables en UI
- Validación robusta de datos

---

## 📊 Lista Priorizada (por importancia)

### 🔴 CRÍTICAS (Obligatorias)
```python
CRITICAL_LIBRARIES = [
    # Imágenes & Media
    'Pillow>=10.0.0',
    'qrcode>=7.4.0',
    'python-barcode>=0.15.0',

    # Office & Reports
    'openpyxl>=3.1.0',
    'reportlab>=4.0.0',

    # Impresión
    'python-escpos>=3.0',

    # XML & Facturación
    'lxml>=5.0.0',
    'xmltodict>=0.13.0',
    'signxml>=3.2.0',
    'cryptography>=42.0.0',
    'zeep>=4.2.0',

    # Network
    'requests>=2.31.0',
    'websockets>=12.0',

    # Fechas & Utils
    'python-dateutil>=2.8.2',
    'pytz>=2024.1',
    'phonenumbers>=8.13.0',
]
```

### 🟡 IMPORTANTES (Muy útiles)
```python
IMPORTANT_LIBRARIES = [
    # Pagos
    'stripe>=7.0.0',

    # Data & Analysis
    'pandas>=2.1.0',
    'numpy>=1.26.0',

    # Hardware
    'pyserial>=3.5',
    'pyusb>=1.2.1',

    # Email
    'email-validator>=2.1.0',

    # Utils
    'python-slugify>=8.0.0',
    'humanize>=4.9.0',
    'pydantic>=2.5.0',

    # Scraping
    'beautifulsoup4>=4.12.0',

    # PDF avanzado
    'PyPDF2>=3.0.0',
]
```

### 🟢 OPCIONALES (Nice to have)
```python
OPTIONAL_LIBRARIES = [
    # Tunneling alternativo
    'paramiko>=3.4.0',
    'sshtunnel>=0.4.0',

    # Pagos adicionales
    'paypalrestsdk>=1.13.1',
    'braintree>=4.24.0',

    # BD adicionales
    'psycopg2-binary>=2.9.9',
    'pymongo>=4.6.0',
    'redis>=5.0.0',

    # Office adicional
    'python-docx>=1.0.0',
    'xlrd>=2.0.1',
    'weasyprint>=60.0',

    # SVG
    'cairosvg>=2.7.0',

    # Hardware avanzado
    'hidapi>=0.14.0',

    # Utils adicionales
    'arrow>=1.3.0',
    'Babel>=2.14.0',
]
```

---

## 🎯 Recomendación Final: Lista Definitiva

**Para CPOS Hub, incluir estas 25 librerías:**

```python
# hub/config/module_allowed_deps.py

MODULE_ALLOWED_DEPENDENCIES = {
    # === CRÍTICAS (13) ===
    'Pillow': '>=10.0.0',          # Imágenes
    'qrcode': '>=7.4.0',           # QR codes
    'python-barcode': '>=0.15.0',  # Códigos de barras
    'openpyxl': '>=3.1.0',         # Excel
    'reportlab': '>=4.0.0',        # PDF
    'python-escpos': '>=3.0',      # Impresoras térmicas
    'lxml': '>=5.0.0',             # XML (facturación)
    'xmltodict': '>=0.13.0',       # XML dict
    'signxml': '>=3.2.0',          # Firmas XML
    'cryptography': '>=42.0.0',    # Cifrado
    'zeep': '>=4.2.0',             # SOAP (Hacienda)
    'requests': '>=2.31.0',        # HTTP
    'websockets': '>=12.0',        # WebSocket

    # === IMPORTANTES (10) ===
    'python-dateutil': '>=2.8.2',  # Fechas
    'pytz': '>=2024.1',            # Timezones
    'phonenumbers': '>=8.13.0',    # Teléfonos
    'stripe': '>=7.0.0',           # Pagos
    'pandas': '>=2.1.0',           # Análisis datos
    'numpy': '>=1.26.0',           # Cálculos
    'pyserial': '>=3.5',           # Serial (hardware)
    'email-validator': '>=2.1.0',  # Validar emails
    'python-slugify': '>=8.0.0',   # URLs amigables
    'pydantic': '>=2.5.0',         # Validación datos

    # === ÚTILES (2) ===
    'beautifulsoup4': '>=4.12.0',  # HTML parsing
    'PyPDF2': '>=3.0.0',           # PDF manipulación
}

# Total: 25 librerías
# Peso estimado: +150-200MB al bundle
```

---

## 📦 Impacto en el Bundle

```
Bundle actual (sin librerías extra): ~130MB

Con 25 librerías:
    - Pillow: +10MB
    - pandas + numpy: +50MB
    - reportlab: +5MB
    - lxml + cryptography: +15MB
    - zeep + requests: +5MB
    - Resto: +30MB
    Total: +115MB

Bundle final: ~245MB

¿Es aceptable?
    - macOS apps típicas: 100-500MB
    - Electron apps: 150-300MB
    - 245MB es razonable para un POS completo ✅
```

---

## 🚀 Siguiente Paso

¿Quieres que implemente esto en `main.spec` con las 25 librerías?

Incluiría:
1. Actualizar `main.spec` con `collect_submodules()` para cada una
2. Crear `hub/config/module_allowed_deps.py` con la whitelist
3. Crear validador de `module.json`
4. Actualizar documentación en CLAUDE.md

¿Procedo? ¿O prefieres ajustar la lista primero?
