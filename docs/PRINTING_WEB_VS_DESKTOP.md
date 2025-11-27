# Impresión: Web vs Desktop

Guía completa sobre cómo funciona el sistema de impresión en diferentes entornos.

## 🎯 Resumen Ejecutivo

| Componente | Desktop (PyWebView) | Web (Navegador) | Estado |
|------------|---------------------|-----------------|--------|
| **Backend Signals** | ✅ Funciona igual | ✅ Funciona igual | Implementado |
| **Signal Handlers** | ✅ Funciona igual | ✅ Funciona igual | Implementado |
| **Impresión Física** | ✅ Directa (Python → OS) | ⚠️ Requiere adaptación | Implementado |

## 📐 Arquitectura por Entorno

### Desktop App (PyWebView + PyInstaller)

```
JavaScript Frontend
        ↓
window.pywebview.api.print_receipt()
        ↓
Python Backend (print_service.py)
        ↓
Sistema Operativo (lp / PowerShell)
        ↓
Impresora Física
```

**✅ Ventajas:**
- Acceso directo a impresoras locales
- Sin dependencias externas
- Impresión silenciosa (sin diálogos)
- Control total del formato

### Web App (Navegador)

#### **Opción 1: Window.print() API** (Recomendada)

```
JavaScript Frontend
        ↓
generateReceiptHTML()
        ↓
window.open() + window.print()
        ↓
Diálogo de impresión del navegador
        ↓
Impresora seleccionada por usuario
```

**✅ Ventajas:**
- No requiere instalación
- Funciona en cualquier navegador
- Estándar web
- Usuario selecciona impresora

**❌ Limitaciones:**
- Requiere intervención del usuario
- Menos control sobre formato
- No puede seleccionar impresora automáticamente

#### **Opción 2: Servicio Local** (Para POS web profesional)

```
Web App (Cloud/Internet)
        ↓ HTTP Request
Servicio Local (localhost:8080)
        ↓
Python (print_service.py)
        ↓
Sistema Operativo
        ↓
Impresora Física
```

**✅ Ventajas:**
- Impresión automática (sin diálogos)
- Control total como desktop
- Funciona desde la nube
- Selección automática de impresora

**❌ Limitaciones:**
- Requiere instalación de servicio local
- Complejidad adicional

## 🚀 Implementación: Sistema Adaptativo

He creado un sistema que **se integra con la configuración de Django** y puede detectar automáticamente el entorno cuando no se especifica.

### Uso desde JavaScript

```javascript
// Importar script adaptativo
<script src="{% static 'printers/js/adaptive_print.js' %}"></script>

// Opción 1: Usar configuración del backend (RECOMENDADO)
await printReceiptAdaptive({
    receipt_id: 'SALE-123',
    items: [...],
    total: 50.00
}, '{{ DEPLOYMENT_MODE }}');  // Django context processor

// Opción 2: Auto-detección (para compatibilidad con versiones antiguas)
await printReceiptAdaptive({
    receipt_id: 'SALE-123',
    items: [...],
    total: 50.00
});

// Detectar entorno actual
const env = detectPrintEnvironment('{{ DEPLOYMENT_MODE }}');
console.log(env); // 'pywebview', 'web_browser', o 'local_service'
```

### Configuración en Django Settings

**Paso 1: Configurar variable de entorno**

```bash
# .env
DEPLOYMENT_MODE=local  # o 'web'
```

**Paso 2: Acceso en templates**

El context processor `deployment_config` expone automáticamente:

```django
<!-- En cualquier template Django -->
<script>
    const DEPLOYMENT_MODE = '{{ DEPLOYMENT_MODE }}';  // 'local' o 'web'
    const IS_LOCAL = {{ IS_LOCAL_DEPLOYMENT|lower }};  // true/false
    const IS_WEB = {{ IS_WEB_DEPLOYMENT|lower }};      // true/false
</script>
```

### Detección de Entorno (con Backend Integration)

```javascript
function detectPrintEnvironment(deploymentMode = null) {
    // 1. Si hay configuración del backend, usarla
    if (deploymentMode) {
        if (deploymentMode === 'local') {
            // Verificar si realmente estamos en PyWebView
            if (typeof window.pywebview !== 'undefined' && window.pywebview.api) {
                return 'pywebview';
            }
            console.warn('[PRINT] Backend configured as "local" but PyWebView not detected');
        } else if (deploymentMode === 'web') {
            // Verificar si hay servicio local configurado
            if (localStorage.getItem('local_print_service_enabled') === 'true') {
                return 'local_service';
            }
            return 'web_browser';
        }
    }

    // 2. Fallback a auto-detección
    if (typeof window.pywebview !== 'undefined' && window.pywebview.api) {
        return 'pywebview';
    }
    if (localStorage.getItem('local_print_service_enabled') === 'true') {
        return 'local_service';
    }
    return 'web_browser';
}
```

## 🔧 Configuración por Escenario

### Escenario 1: Desktop App (PyWebView)

**✅ Configuración mínima requerida**

```bash
# .env
DEPLOYMENT_MODE=local
```

```javascript
// Usa configuración del backend
await printReceiptAdaptive(data, '{{ DEPLOYMENT_MODE }}');
// → Detecta PyWebView y imprime directamente en impresora configurada
```

### Escenario 2: Web Simple (Sin instalaciones)

**✅ Configuración mínima requerida**

```bash
# .env
DEPLOYMENT_MODE=web
```

```javascript
// Usa configuración del backend
await printReceiptAdaptive(data, '{{ DEPLOYMENT_MODE }}');
// → Abre diálogo de impresión del navegador
```

**Experiencia de usuario:**
1. Usuario hace clic en "Imprimir"
2. Se abre ventana con vista previa del recibo
3. Usuario hace clic en "Imprimir" del navegador
4. Selecciona impresora y confirma

### Escenario 3: Web POS Profesional (Con servicio local)

#### **Paso 1: Instalar servicio local**

Crear mini-aplicación que se ejecuta en el POS:

```python
# local_print_service.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import sys
import os

# Añadir path del Hub para importar print_service
sys.path.insert(0, '/path/to/hub')
from plugins.printers.print_service import print_service

app = Flask(__name__)
CORS(app)  # Permitir requests desde web app

@app.route('/print', methods=['POST'])
def print_receipt():
    """Recibe petición HTTP y imprime usando print_service"""
    try:
        data = request.json
        result = print_service.print_receipt(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check para verificar que el servicio está activo"""
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    print("[LOCAL PRINT SERVICE] Starting on http://localhost:8080")
    app.run(host='127.0.0.1', port=8080, debug=False)
```

**Ejecutar servicio:**

```bash
# Opción 1: Python directamente
python local_print_service.py

# Opción 2: PyInstaller (distribuir como ejecutable)
pyinstaller local_print_service.py --onefile
./dist/local_print_service
```

#### **Paso 2: Configurar web app**

```bash
# .env
DEPLOYMENT_MODE=web
LOCAL_PRINT_SERVICE_URL=http://localhost:8080
```

```javascript
// En la web app, habilitar servicio local
enableLocalPrintService('{{ LOCAL_PRINT_SERVICE_URL }}');

// Ahora las impresiones van al servicio local
await printReceiptAdaptive(data, '{{ DEPLOYMENT_MODE }}');
// → HTTP POST a localhost:8080
// → Servicio local imprime en impresora física
```

#### **Paso 3: Auto-detección**

El servicio puede auto-anunciarse:

```javascript
// Verificar si servicio local está disponible
async function checkLocalService() {
    try {
        const response = await fetch('http://localhost:8080/health');
        if (response.ok) {
            enableLocalPrintService('http://localhost:8080');
            console.log('✓ Servicio local detectado');
        }
    } catch (e) {
        console.log('✗ Servicio local no disponible, usando web print');
    }
}

// Ejecutar al cargar la app
checkLocalService();
```

## 📊 Comparativa de Opciones

### Para Web App

| Opción | Complejidad | UX | Control | Recomendado para |
|--------|-------------|----|---------|--------------------|
| **window.print()** | Baja | Media (requiere clic) | Bajo | Negocios pequeños, uso ocasional |
| **Servicio Local** | Media | Alta (automático) | Total | POS profesional, alta frecuencia |
| **PDF Download** | Baja | Baja (manual) | Bajo | Backup/fallback |

### Recomendaciones por Tipo de Negocio

#### **Tienda Pequeña** (Web)
```javascript
// Usar window.print() - Simple y suficiente
await printReceiptAdaptive(data);
```
- ✅ Sin instalación
- ✅ Funciona en cualquier dispositivo
- ⚠️ Usuario debe hacer clic extra

#### **Restaurante** (Web con servicio local)
```javascript
// Instalar servicio local
// Cocina imprime automáticamente
enableLocalPrintService('http://localhost:8080');
await printReceiptAdaptive(data);
```
- ✅ Impresión automática
- ✅ Múltiples impresoras (cocina, barra, etc.)
- ⚠️ Requiere instalación una vez

#### **Cadena de Tiendas** (Desktop app)
```python
# Distribuir app de escritorio con PyInstaller
# Impresión completamente automática
```
- ✅ Control total
- ✅ Sin dependencias
- ✅ Offline-first

## 🔒 Seguridad: Servicio Local

### Consideraciones Importantes

1. **Solo localhost**: Servicio solo escucha en `127.0.0.1`
2. **CORS**: Configurar dominios permitidos
3. **Autenticación**: Token de acceso para requests

```python
# local_print_service.py con seguridad
from flask import Flask, request, jsonify
from flask_cors import CORS
import secrets

app = Flask(__name__)

# CORS solo para dominios específicos
CORS(app, origins=[
    'https://erplora.com',
    'https://tu-dominio.com'
])

# Token de autenticación (generado al instalar)
API_TOKEN = secrets.token_hex(32)

def verify_token():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if token != API_TOKEN:
        return jsonify({'error': 'Unauthorized'}), 401
    return None

@app.route('/print', methods=['POST'])
def print_receipt():
    # Verificar token
    error = verify_token()
    if error:
        return error

    # Procesar impresión...
    data = request.json
    result = print_service.print_receipt(data)
    return jsonify(result)

if __name__ == '__main__':
    print(f"[LOCAL PRINT SERVICE] API Token: {API_TOKEN}")
    print(f"[LOCAL PRINT SERVICE] Guarda este token en tu web app")
    app.run(host='127.0.0.1', port=8080)
```

### Configurar token en web app

```javascript
// Guardar token al configurar servicio
function enableLocalPrintService(url, apiToken) {
    localStorage.setItem('local_print_service_enabled', 'true');
    localStorage.setItem('local_print_service_url', url);
    localStorage.setItem('local_print_service_token', apiToken);
}

// Usar token en requests
async function printViaLocalService(data) {
    const token = localStorage.getItem('local_print_service_token');

    const response = await fetch('http://localhost:8080/print', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(data)
    });

    return await response.json();
}
```

## 🎨 Ejemplo Completo: Tienda Online

```html
<!-- Página web de POS -->
<!DOCTYPE html>
<html>
<head>
    <title>POS Online</title>
    <script src="/static/printers/js/adaptive_print.js"></script>
</head>
<body>
    <button onclick="vender()">Completar Venta</button>

    <script>
    // Auto-detectar servicio local al cargar
    window.addEventListener('load', async () => {
        try {
            const response = await fetch('http://localhost:8080/health');
            if (response.ok) {
                const data = await response.json();
                enableLocalPrintService('http://localhost:8080', data.token);
                console.log('✓ Impresión automática habilitada');
            }
        } catch (e) {
            console.log('✓ Usando impresión manual del navegador');
        }
    });

    async function vender() {
        // Procesar venta en backend...
        const sale = await fetch('/api/sales/', {
            method: 'POST',
            body: JSON.stringify({...})
        }).then(r => r.json());

        // Imprimir (se adapta automáticamente al entorno)
        const result = await printReceiptAdaptive({
            receipt_id: sale.id,
            items: sale.items,
            total: sale.total
        });

        if (result.success) {
            alert('✓ Venta completada y recibo impreso');
        } else {
            alert('✗ Error al imprimir: ' + result.message);
        }
    }
    </script>
</body>
</html>
```

## 🚀 Resumen: ¿Qué Usar?

### ✅ **Siempre funciona** (ambos entornos):
- Sistema de señales Django ✅
- Handlers de impresión ✅
- Selección automática de impresora ✅

### **Solo Desktop** (PyWebView):
- Impresión directa sin diálogos ✅
- Comando de sistema (lp, PowerShell) ✅

### **Solo Web** (Navegador):
- `window.print()` con HTML ✅
- PDF downloadable ✅
- Servicio local (opcional) ✅

### Tabla de Decisión

| Tu Caso | Solución Recomendada |
|---------|---------------------|
| Desarrollo local | Desktop app (PyWebView) |
| Negocio pequeño, web | `window.print()` |
| POS profesional, web | Servicio local |
| Cadena de tiendas | Desktop app distribuida |
| App móvil | `window.print()` o Cloud Print API |
| Kiosco/Tablet | Desktop app o servicio local |

## 🎁 Ventajas de la Integración con Backend

### ✅ Configuración Centralizada
- **Una fuente de verdad**: DEPLOYMENT_MODE en `.env`
- **No duplicación**: Backend y frontend usan la misma configuración
- **Fácil cambio**: Cambiar de local a web solo requiere editar `.env`

### ✅ Consistencia Garantizada
- **Sin desincronización**: Frontend siempre refleja configuración del backend
- **Validación en settings.py**: Solo permite valores válidos ('local' o 'web')
- **Logs mejorados**: Modo de despliegue visible en consola del navegador

### ✅ Mantenibilidad
```python
# Backend (settings.py)
DEPLOYMENT_MODE = config('DEPLOYMENT_MODE', default='local')

# Frontend (JavaScript)
printReceiptAdaptive(data, '{{ DEPLOYMENT_MODE }}')
```

### ✅ Fallback Inteligente
Si por alguna razón la configuración del backend no está disponible, el sistema hace auto-detección automática para compatibilidad con versiones anteriores.

## 📝 Próximos Pasos

1. ✅ Sistema adaptativo implementado
2. ✅ Integración con Django settings (DEPLOYMENT_MODE)
3. ⏳ Actualizar plugin sales para usar sistema adaptativo
4. ⏳ Crear ejecutable del servicio local (PyInstaller)
5. ⏳ UI de configuración para servicio local
6. ⏳ Testing en entornos web y desktop
