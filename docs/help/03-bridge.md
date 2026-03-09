# ERPlora Bridge (Hardware)

ERPlora Bridge es la aplicación nativa que conecta tu Hub con el hardware: impresoras de tickets, cajón de dinero y escáner de códigos de barras.

## ¿Qué es el Bridge?

El Bridge es un programa que se ejecuta en el **mismo equipo** donde usas el Hub. Se comunica con el Hub mediante WebSocket (`ws://localhost:12321`).

```
┌─────────────┐     WebSocket      ┌──────────────┐     USB/Red/BT     ┌──────────────┐
│   Hub       │ ◄──────────────► │   Bridge     │ ◄──────────────► │  Hardware    │
│  (navegador)│    localhost:12321  │  (app nativa)│                   │  (impresora, │
│             │                    │              │                   │   cajón, etc.)│
└─────────────┘                    └──────────────┘                   └──────────────┘
```

## Terminales

- **Terminal Principal**: Equipo con Bridge instalado. Puede imprimir y abrir cajón.
- **Terminal Satélite**: Cualquier otro dispositivo (tablet, móvil). Solo usa el navegador, sin hardware directo.

## Instalación del Bridge

### macOS

1. Descarga `ERPlora Bridge.app` desde tu panel de Cloud
2. Mueve la app a **Aplicaciones**
3. Abre la app — puede que macOS pida autorización en **Preferencias del Sistema → Seguridad**
4. El icono del Bridge aparecerá en la barra de menú
5. El Bridge se conectará automáticamente al Hub

### Windows

1. Descarga `ERPlora Bridge Setup.exe` desde tu panel de Cloud
2. Ejecuta el instalador
3. El Bridge se instalará y arrancará automáticamente
4. El icono aparecerá en la bandeja del sistema (junto al reloj)

### Linux

1. Descarga el binario desde tu panel de Cloud
2. Dale permisos de ejecución: `chmod +x erplora-bridge`
3. Ejecuta: `./erplora-bridge`
4. Para autoarranque, añade al inicio de sesión de tu escritorio

### Android

1. Descarga `ERPlora Bridge.apk` desde tu panel de Cloud
2. Permite la instalación de fuentes desconocidas si es necesario
3. Instala y abre la app
4. Conecta tu impresora por Bluetooth o USB OTG

## Configuración en el Hub

Una vez instalado el Bridge:

1. Ve a **Ajustes** en el Hub
2. Busca la sección **Hardware / Bridge**
3. Activa el interruptor **"Bridge habilitado"**
4. El Hub detectará automáticamente el Bridge si está corriendo en el mismo equipo
5. El indicador de conexión mostrará **"Conectado"** en verde

## Impresoras

### Tipos de conexión

| Tipo | Descripción | Ejemplo |
|------|-------------|---------|
| USB | Conectada directamente por USB | Epson TM-T20, Star TSP100 |
| Red | Conectada por ethernet o WiFi | Impresoras con IP fija |
| Bluetooth | Conexión inalámbrica | Impresoras portátiles |

### Configurar una impresora

1. Conecta la impresora al equipo donde corre el Bridge
2. El Bridge detectará la impresora automáticamente
3. Ve a **Ajustes → Hardware** en el Hub
4. La impresora aparecerá en la lista de impresoras disponibles
5. Configura:
   - **Nombre**: Nombre descriptivo (ej: "Cocina", "Barra")
   - **Ancho de papel**: 58mm o 80mm
   - **Tipos de documento**: Qué imprime (tickets, pedidos de cocina, facturas)
   - **Predeterminada**: Si es la impresora principal

### Cajón de dinero

El cajón se conecta a la impresora de tickets (puerto RJ11/DK). Se abre automáticamente al:
- Abrir una sesión de caja
- Cobrar en efectivo
- Cerrar caja

### Escáner de códigos de barras

Los escáneres USB funcionan como teclado — no necesitan configuración. Simplemente:

1. Conecta el escáner por USB
2. Coloca el cursor en el campo de búsqueda de productos
3. Escanea — el código se introduce automáticamente

## Solución de Problemas

| Problema | Solución |
|----------|----------|
| Bridge no conecta | Verifica que el Bridge está corriendo. Comprueba que el puerto 12321 no está bloqueado. |
| Impresora no detectada | Verifica la conexión USB/red. Reinicia el Bridge. |
| No imprime | Comprueba que la impresora está asignada al tipo de documento correcto en Ajustes. |
| Cajón no abre | Verifica que el cable RJ11 conecta el cajón a la impresora. |
