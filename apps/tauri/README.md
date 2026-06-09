# apps/tauri (scaffold parcial)

Empaquetado **desktop/móvil** (Tauri v2) del mismo shell + runtime Rust. ARQUITECTURA.md §1, §3.

Expondrá `erplora_query`/`erplora_command` por `invoke` (IPC) + Tauri events (push) →
delegando en `crates/runtime`. DB local = SQLite (`HUB_SQLITE_PATH`, §8). Sin red salvo
marketplace/AI/primer-login (§2.8).

**Pendiente**: requiere toolchain Rust + Tauri CLI. De-risk #2 del §12 (Tauri `invoke` y
Axum llamando al *mismo* `runtime`).

## Gate de arranque por entitlement (la app Tauri es GRATIS)

Ya scaffoldeado en `src-tauri/` (`Cargo.toml`, `tauri.conf.json`, `src/lib.rs`). La app de
escritorio/Android **no se compra**: es la versión ligera (basic + compliance) para captar
clientes. Lo que desbloquea módulos es un **entitlement por tiers** servido por el Cloud.

Flujo (`src/lib.rs::EntitlementGate`):

1. El frontend (`apps/web`), tras el login, llama a `invoke('validate_entitlement', { hubId, accessToken })`.
2. El gate pide al Cloud la clave pública (`/api/v1/auth/public-key/`) + el token firmado
   (`/api/v1/hub/device/entitlement/`), lo **verifica** (`erplora-cloud-client::verify_entitlement`,
   RS256) y lo **cachea** en `app_data_dir` (`entitlement.jwt` + `cloud_public_key.pem`).
3. **Sin red**: verifica el token cacheado **offline** y sigue dentro de la ventana de gracia
   (`grace_until`, lo emite el Cloud — `cloud/apps/public/modules/entitlement.py`).
4. Devuelve `GateOutcome`: `unlocked { modules, deployment_mode, offline }` → el frontend monta
   SOLO esos módulos; o `needs_activation { reason }` → pantalla de login/activación, sin negocio.

`HUB_CLOUD_API_URL` sobreescribe la base del Cloud (por defecto `https://erplora.com`).

> **No está en `members` del workspace raíz** (necesita el toolchain Tauri v2 + el `dist` de
> `apps/web`). Cuando se estabilice el arranque, añadir `"apps/tauri/src-tauri"` a `members` en
> `../../Cargo.toml`. La lógica criptográfica/gracia (verificable hoy con `cargo test -p
> erplora-cloud-client`) vive en `crates/cloud-client/src/entitlement.rs`.

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
