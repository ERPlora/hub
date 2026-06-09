# apps/tauri (STUB)

Empaquetado **desktop/móvil** (Tauri v2) del mismo shell + runtime Rust. ARQUITECTURA.md §1, §3.

Expondrá `erplora_query`/`erplora_command` por `invoke` (IPC) + Tauri events (push) →
delegando en `crates/runtime`. DB local = SQLite (`HUB_SQLITE_PATH`, §8). Sin red salvo
marketplace/AI/primer-login (§2.8).

**Pendiente**: requiere toolchain Rust + Tauri CLI. De-risk #2 del §12 (Tauri `invoke` y
Axum llamando al *mismo* `runtime`).

## Hardware local = sidecar de `erplora-peripherals` (§2.7)

En los combos Tauri, el shell **es el bridge**: no hay proceso aparte ni segundo install. La
lógica de hardware ya vive en el crate compartido **`crates/peripherals`** (red-only, ESC/POS
sobre TCP:9100), el mismo que usa el bridge standalone (`apps/bridge`) para `cloud + web-PWA`.

Cuando se levante este `apps/tauri`, además de `erplora_query`/`erplora_command` (→ `crates/runtime`),
registrar handlers `invoke` de hardware que delegan en `erplora-peripherals` (en vez del servidor
WebSocket que monta `apps/bridge`):

| `invoke`                     | Llama a                                              |
|------------------------------|-----------------------------------------------------|
| `erplora_discover_printers`  | `peripherals::discovery::discover_printers(&reg)`   |
| `erplora_print`              | `escpos::render_document` + `queue::PrintQueue`      |
| `erplora_test_print`         | `escpos::render_test_page` + envío                   |
| `erplora_open_drawer`        | `peripherals::drawer::open_drawer(&target, pin)`     |
| `erplora_get_devices` / role/name/remove | `peripherals::registry::DeviceRegistry`  |

El watchdog (`registry::Watchdog`) corre como tarea async del shell. El frontend usa el mismo
`IpcTransport` del `module-sdk`; el contrato de datos es idéntico al WS de `apps/bridge`, así que
`hub/static/js/bridge.js` y la UI no distinguen el transporte. Ver `crates/peripherals/README.md`.
