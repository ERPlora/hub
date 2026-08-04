# apps/tauri

Empaquetado **desktop/móvil** (Tauri v2) del mismo shell + runtime Rust. ARQUITECTURA.md §1, §3.

Arranca el **runtime embebido** (`erplora_server::serve` en un hilo tokio dedicado, loopback
`127.0.0.1:8787`) y expone por `invoke` el gate de arranque + identidad de dispositivo/máquina
(`validate_entitlement`, `device_context`, `enroll_device`, `rotate_machine_token`). DB local =
SQLite en `app_data_dir`. Sin red salvo marketplace/AI/primer-login (§2.8).

**Estado**: **compila** — `crates/cloud-client/src/entitlement.rs` (RS256 offline) + `src-tauri/`
(gate + keychain del SO para el token de máquina). Es **miembro del workspace raíz**;
`cargo check -p erplora-tauri` pasa en verde.

**Para construir el binario** (`cargo tauri build`):
1. Toolchain Tauri v2 + WebView del SO (macOS WKWebView / Windows WebView2 / Linux webkit2gtk).
2. Frontend: `pnpm -F @erplora/web build` (genera el `dist` que referencia `tauri.conf.json`).
3. Iconos de bundle completos: el set vive en `src-tauri/icons/` y lo genera el pipeline propio
   `scripts/gen-tauri-icon.py` (icono de **app** real: fondo de marca + safe-area + forma por
   plataforma), a partir del asset fuente `branding/app-icon-source.png`. El arte de marca
   **definitivo lo aporta el humano** ahí; el set actual es **provisional** (marca V5). Ver
   [`branding/README.md`](branding/README.md). (`cargo tauri icon` sigue valiendo como
   alternativa, pero genera un recorte plano sin composición de app.)

## Accesos de lanzamiento por canal (escritorio)

Qué acceso directo ve el usuario tras instalar, según el canal de distribución. No se
configura nada extra en `tauri.conf.json`: es el comportamiento por defecto de cada
empaquetador (no inventamos claves de config; si algún default no se cumple, se ajusta
entonces con la clave documentada que corresponda).

| Canal | Artefacto | Acceso de lanzamiento |
| --- | --- | --- |
| Windows NSIS (S3, canal secundario) | `erplora-app-setup.exe` | Acceso directo en **Escritorio + Menú Inicio** (default del template NSIS de Tauri v2) |
| Windows Microsoft Store (canal principal, ADR-0136) | MSIX | Entrada en **Menú Inicio** (convención Store; sin icono de escritorio) |
| Linux `.deb` (S3) | `erplora-app.deb` | Entrada en el **menú de aplicaciones** (fichero `.desktop` autogenerado por el bundler) |
| Linux AppImage (S3, canal de QA) | `erplora-app.AppImage` | **Portable**: no instala nada ni crea accesos; se ejecuta directamente |
| macOS (build local) | `.app`/`.dmg` | Arrastrar a `/Applications` (convención macOS; sin instalador) |

> ⚠️ **Validación pendiente en el primer build real de CI (tag `v1.0.0`)**: confirmar en
> máquina limpia que NSIS crea ambos accesos, que el MSIX solo aparece en Menú Inicio y que
> el `.deb` registra la entrada de menú.

## Gate de arranque por entitlement (la app Tauri es GRATIS)

Ya scaffoldeado en `src-tauri/` (`Cargo.toml`, `tauri.conf.json`, `src/lib.rs`). La app de
escritorio/Android **no se compra**: es la versión ligera (basic + compliance) para captar
clientes. Lo que desbloquea módulos es un **entitlement por tiers** servido por el SaaS.

Flujo (`src/lib.rs::EntitlementGate`):

1. El frontend (`apps/web`), tras el login, llama a `invoke('validate_entitlement', { hubId, accessToken })`.
2. El gate pide al SaaS la clave pública (`/api/v1/auth/public-key/`) + el token firmado
   (`/api/v1/hub/device/entitlement/`), lo **verifica** (`erplora-cloud-client::verify_entitlement`,
   RS256) y lo **cachea** en `app_data_dir` (`entitlement.jwt` + `cloud_public_key.pem`).
3. **Sin red**: verifica el token cacheado **offline** y sigue dentro de la ventana de gracia
   (`grace_until`, lo emite el SaaS — `saas/apps/public/modules/entitlement.py`).
4. Devuelve `GateOutcome`: `unlocked { modules, deployment_mode, offline }` → el frontend monta
   SOLO esos módulos; o `needs_activation { reason }` → pantalla de login/activación, sin negocio.

`HUB_CLOUD_API_URL` sobreescribe la base del SaaS (por defecto `https://erplora.com`).

> Histórico (ya resuelto): en su día `apps/tauri/src-tauri` no estaba en `members` del
> workspace raíz. Hoy **sí lo está** (ver `../../Cargo.toml`); `cargo check -p erplora-tauri`
> pasa en verde (línea 12 arriba). La lógica criptográfica/gracia (verificable con `cargo test -p
> erplora-cloud-client`) vive en `crates/cloud-client/src/entitlement.rs`.

## Hardware local = sidecar de `erplora-peripherals` (§2.7)

> **ADR-0196 (2026-08-03) deroga el reparto de esta sección, y todavía NO se ha ejecutado.**
> Decide que `apps/bridge` (WS `:12321`) y la app Kotlin desaparecen: queda `isTauri()` →
> `invoke` in-process y nada más, y la cola de impresión se muda al Hub. Mientras el código de
> `apps/bridge` siga en el árbol, lo de abajo describe el camino Tauri, que es el que
> sobrevive. Para saber si la retirada ya ocurrió, mira si existe `apps/bridge/`.

En el producto **Hub Local** (Tauri), el shell **es el bridge**: no hay proceso aparte ni segundo install. La
lógica de hardware ya vive en el crate compartido **`crates/peripherals`** (red-only, ESC/POS
sobre TCP:9100), el mismo que usa el bridge standalone (`apps/bridge`) en **Hub Cloud**.

Los DATOS NO van por `invoke` (ADR-0050): el front habla HTTP+WS al runtime Axum embebido. `invoke`
queda solo para lo nativo y para el HARDWARE — handlers que delegan en `erplora-peripherals` (en vez
del servidor WebSocket que monta `apps/bridge`):

| `invoke`                     | Llama a                                              |
|------------------------------|-----------------------------------------------------|
| `erplora_discover_printers`  | `peripherals::discovery::discover_printers(&reg)`   |
| `erplora_print`              | `escpos::render_document` + `queue::PrintQueue`      |
| `erplora_test_print`         | `escpos::render_test_page` + envío                   |
| `erplora_open_drawer`        | `peripherals::drawer::open_drawer(&target, pin)`     |
| `erplora_get_devices` / role/name/remove | `peripherals::registry::DeviceRegistry`  |

El watchdog (`registry::Watchdog`) corre como tarea async del shell. Para el HARDWARE el frontend usa
`IpcBridgeTransport` del `module-sdk` (los datos van aparte por `HttpWsTransport`); el contrato es
idéntico al WS de `apps/bridge`, así que la UI no distingue el transporte de hardware. Ver
`crates/peripherals/README.md`.
