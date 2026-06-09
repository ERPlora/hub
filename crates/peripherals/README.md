# erplora-peripherals

Lógica de hardware POS reutilizable, **solo red** (ESC/POS sobre TCP, puerto 9100).
ARQUITECTURA.md §2.7. Es el reemplazo en Rust del Bridge Python
(`bridge/ERPlora-Bridge-desktop`), empaquetado como **librería** sin servidor ni UI.

## Consumidores

- **`apps/bridge`** — bridge standalone (combo `cloud + web-PWA`): servidor Axum
  `GET /status` + `WS /ws` que envuelve este crate.
- **`apps/tauri`** — sidecar (combos Tauri): handlers `invoke` que llaman a este crate
  (pendiente; ver `apps/tauri`).

Ambos hablan el **mismo protocolo JSON** que `hub/static/js/bridge.js` ya consume.

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

**Esqueleto**: tipos y firmas con `todo!()`. La implementación real (y los tests del crate:
render ESC/POS contra bytes esperados, cola/reintentos con socket simulado) es la fase
siguiente. Ver el plan en `~/.claude/plans/`.

## Dependencias pendientes (al implementar)

- `mdns-sd` — descubrimiento mDNS.
- `chrono` — timestamps `first_seen`/`last_seen`.
- codificación cp437 para `escpos::text` (crate `codepage`/tabla propia).
