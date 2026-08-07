# apps/tauri

La app **de escritorio y Android** (Tauri v2). Es un **cliente fino** (ADR-0159): ARQUITECTURA.md §1, §3.

La ventana arranca en el SaaS (`erplora.com/shell/`), **captura** a qué hub apunta esta instalación
(ADR-0243) y a partir de ahí abre ese hub a pantalla completa en cada arranque. **No hay runtime
embebido ni base de datos local**: los datos viajan por HTTP+WS al hub cloud. Lo que la app aporta
—y su razón de existir— es el **hardware** de la caja: impresoras ESC/POS y cajón por `invoke` sobre
`crates/peripherals`, más la identidad de dispositivo (`device_context` → `X-Device-Id`, sesión única
ADR-0154) y las notificaciones del SO.

> **ADR-0154 retiró el producto local**, y con él tres cosas que este README describía y ya no
> existen: el runtime embebido (`erplora_server::serve` en loopback `:8787` + SQLite en
> `app_data_dir`), el gate `validate_entitlement` (verificación RS256 **offline** de un token
> cacheado, con ventana de gracia) y `frontendDist` apuntando a `../../web/dist`. Quién decide hoy
> el entitlement está más abajo. Las guardas que impiden que vuelvan viven en
> `src-tauri/tests/shell_surface.rs` (hub#336).

**Estado**: miembro del workspace raíz. `cargo test -p erplora-tauri` pasa en verde; su CI propio es
[`test-shell.yml`](../../.github/workflows/test-shell.yml), que se dispara **solo** cuando cambia el
shell (el `cargo test --workspace` del gate principal lo excluye: tauri/wry arrastra GTK/webkit2gtk).

**Para construir el binario** (`cargo tauri build`):
1. Toolchain Tauri v2 + WebView del SO (macOS WKWebView / Windows WebView2 / Linux webkit2gtk).
2. Frontend: **nada que construir**. `tauri.conf.json` empaqueta `shell-dist/`, una página estática
   commiteada (la pantalla degradada que se ve cuando todavía no hay hub, o cuando no carga). La PWA
   del hub **la sirve el hub**, no el instalador.
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

## Entitlement: la app NO decide (ADR-0154)

La app de escritorio/Android **no se compra**: se descarga gratis y lo que desbloquea módulos es el
**entitlement por tiers** que emite el SaaS. Lo que cambió con ADR-0154 no es *qué* se decide, sino
**dónde**: la app dejó de tener su propia copia de la decisión.

El shell **no** tiene ya ningún comando de entitlement. Quién decide hoy, y contra qué:

| Capa | Dónde | Qué hace |
| --- | --- | --- |
| **Cloud (fuente de verdad)** | SaaS, `/api/v1/hub/device/entitlement/` | emite el entitlement firmado RS256 por hub |
| **Runtime del hub (el que manda)** | [`crates/server/src/entitlement.rs`](../../crates/server/src/entitlement.rs) | revalidación híbrida (ADR-0114 §6): verifica la firma con `erplora-cloud-client::verify_entitlement` y el dispatcher responde **402** a las queries/commands de un módulo de pago bloqueado |
| **UI** | [`apps/web/src/lib/entitlement.ts`](../web/src/lib/entitlement.ts) | `GET /api/entitlement` filtra qué módulos se montan y deshabilita los bloqueados con CTA de suscripción |

Es decir: el gate sigue vivo y **más fuerte** que antes, porque la negativa la aplica el servidor en
cada llamada, no un chequeo de arranque en el cliente. Lo que se retiró fue el camino Tauri
(`validate_entitlement`): un veredicto **offline** sobre un token cacheado en `app_data_dir` con
ventana de gracia. En un cliente fino ese camino es una segunda respuesta, más débil, a una pregunta
que el Cloud ya contesta — y es justo la que el usuario puede editar en su propio disco.

> `crates/cloud-client/src/entitlement.rs` **sigue en uso** (lo llama la revalidación del runtime);
> lo que desapareció es su llamador Tauri. No lo borres pensando que es código muerto.

## Hardware local = sidecar de `erplora-peripherals` (§2.7)

> **ADR-0196 (2026-08-03) deroga el reparto de esta sección, y todavía NO se ha ejecutado.**
> Decide que `apps/bridge` (WS `:12321`) y la app Kotlin desaparecen: queda `isTauri()` →
> `invoke` in-process y nada más, y la cola de impresión se muda al Hub. Mientras el código de
> `apps/bridge` siga en el árbol, lo de abajo describe el camino Tauri, que es el que
> sobrevive. Para saber si la retirada ya ocurrió, mira si existe `apps/bridge/`.

En la app, el shell **es el bridge**: no hay proceso aparte ni segundo install. La lógica de
hardware vive en el crate compartido **`crates/peripherals`** (red-only, ESC/POS sobre TCP:9100), el
mismo que usa el bridge standalone (`apps/bridge`).

Los DATOS NO van por `invoke` (ADR-0050): el front habla HTTP+WS **con su hub cloud** (no hay
runtime embebido — ADR-0154). `invoke` queda solo para lo nativo y para el HARDWARE — handlers que
delegan en `erplora-peripherals` (en vez del servidor WebSocket que monta `apps/bridge`):

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
