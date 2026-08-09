# erplora-peripherals

Lógica de hardware POS reutilizable, **solo red** (ESC/POS sobre TCP, puerto 9100).
Diseño en [architecture/hub/apps/bridge.md](../../../architecture/hub/apps/bridge.md) (reubicado desde `ARQUITECTURA.md §2.7`). Es el reemplazo en Rust del Bridge Python
(`bridge/ERPlora-Bridge-desktop`), empaquetado como **librería** sin servidor ni UI.

## Consumidores

- **`apps/tauri`** — **la** app instalable (ADR-0196/0204): sus `invoke` de hardware llaman a este
  crate **in-process**. No hay servidor local, ni puerto, ni token de emparejamiento.

> 🪦 Hubo un segundo consumidor, el **Bridge standalone** (`apps/bridge`, Axum `GET /status` +
> `WS /ws` en `localhost:12321`), al que la web shell llegaba por localhost. ADR-0196 lo retiró y
> **hub#340 lo borró del árbol**: el precio explícito es que una PWA en un navegador, sin la app,
> no imprime tiques térmicos. Historia en
> [architecture/hub/apps/bridge.md](../../../architecture/hub/apps/bridge.md).

Habla el **mismo protocolo JSON** que la web shell del Hub consume.

## Decisión red-only (§2.7)

USB y Bluetooth se descartan (drivers + mantenimiento por SO no escalan). El escáner por
HID lo maneja el SO/navegador como teclado. Por eso aquí **no** hay `usb`/`bluetooth`/
`scanner`/`keyboard`. `printer_id` es siempre `network:{ip}:{port}`.

## Mapeo Python → Rust (qué portar y de dónde)

| Módulo Rust | Origen Python | Qué hace |
|---|---|---|
| `protocol` | `erplora_bridge/protocol.py`, `Protocol.kt` | Tipos `serde` de `Command`/`Event`/`PrinterInfo`/`Device`. **Elimina** `toggle_keyboard`, evento `barcode`, `keyboard_toggled`. |
| `discovery` | `hardware/discovery.py` (solo rama `network`) | `parse_printer_id`, escaneo de subred /24 al 9100, mDNS, enriquecido MAC. Descarta `_discover_usb`. |
| `escpos` | `hardware/printer.py` + `_RawNetworkPrinter` (`discovery.py`) | Comandos ESC/POS (align/bold/size/cut/barcode) + renderizadores por `document_type`. |
| `drawer` | `hardware/drawer.py` | Kick ESC/POS pin 2/5 por el socket de la impresora. |
| `queue` | *(nuevo)* | Cola + reintentos (§2.7). En Python la impresión era síncrona. |
| `registry` | `hardware/network.py` + `hardware/watchdog.py` | Registro persistente `devices.json`, MAC vía ARP, watchdog de re-localización por DHCP. |

Lo que **no** se porta: `hardware/scanner.py`, `toggle_keyboard`/teclado virtual, USB
(`pyusb`), Bluetooth (`pyserial`).

## Estado

**Implementado**: los módulos (`protocol`, `discovery`, `escpos`, `drawer`, `queue`,
`registry`, `lib`) tienen lógica real, no firmas con `todo!()`. `cargo test -p erplora-peripherals`
corre en verde (render ESC/POS contra bytes esperados, cola/reintentos contra un socket, apertura
de cajón, sonda del watchdog, discovery).

> 🪦 Hubo un módulo `printer` con una capa de traits (`Printer`/`CashDrawer`) y **su propia**
> política de reintentos, propuesta en pm#4 y nunca consumida: la app instalable encola por `queue`
> y abre el cajón por `drawer`. **hub#379** lo borró —dos políticas de reintento coexistiendo son
> una que nadie mantiene— y movió sus tests a las vías vivas, que hasta entonces no tenían ninguno.
