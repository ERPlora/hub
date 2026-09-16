# hub — Arquitectura

> **ADR-0154 + ADR-0196 — el Hub es Postgres-only y Cloud-only (PWA + app instalable).** Se
> retiró el producto Hub Local (Tauri desktop) y el backend SQLite. La historia queda en el
> decision-log del repo `architecture`.
>
> **Documento de diseño.** Define el Hub de
> ERPlora: **Vue 3 + Ionic + Rust/Axum + módulos declarativos (module.json) +
> WASM + SDK**, con **PostgreSQL per-hub — una BD por hub** (ADR-0201, **completo, 11/11**,
> aterrizado 2026-08-06 — la `Organization` ya no existe) en cloud (Hetzner; AWS: Aurora,
> fallback).
>
> **hub ES el Hub de ERPlora.**
>
> Fuentes: diseño AI/RAG [architecture/hub/crates/vector.md](../architecture/hub/crates/vector.md) (ADR-0033), mapa del monorepo
> [CLAUDE.md](../CLAUDE.md), repo de arquitectura seccionado [architecture/](../architecture/).
>
> **Estado:** en producción — **27 módulos** (source en `modules-workspace/modules/<id>/`, cada
> uno su propio repo git; ⚠️ `ls modules-workspace/modules` ya no cuenta bien porque la flota deja
> worktrees ahí dentro — cuenta los que tienen `.git` como DIRECTORIO, no fichero), runtime con
> suites e2e amplias, imagen Docker del tenant, instalación E2E por marketplace con SHA256.
> Estado vivo: `/estado`.
> Última actualización: 2026-09-16 (recuento de módulos, ADR-0201, canales de imagen, `http.fetch`
> y hardware pasados por verificación contra `origin/develop` — ver `crates/README.md` y `§14`).
>
> 🏗️ **Infra cloud:** donde este doc dice **Aurora/ECS** como backend del Hub Cloud, el
> proveedor **ACTIVO es Hetzner** — Postgres per-hub, una BD por hub (ADR-0201, completo), con
> **failover automático** (Patroni + etcd×3, dirección fija `lb-db` — ADR-0415, nunca la IP de un
> nodo), desplegado como **Dokploy application en el Swarm `hubs-a`** (uno de los tres Swarms de
> la flota: `hubs-a`/`plat`/control-plane); **AWS (ECS + Aurora) = fallback seleccionable, sin infra
> viva** (`get_provider`). Ver [CLAUDE.md](CLAUDE.md) y [architecture/hub/overview.md](../architecture/hub/overview.md).
>
> ⚠️ **Varias secciones citadas en este documento se reubicaron:** §2.3 (auth) →
> [architecture/hub/auth.md](../architecture/hub/auth.md), §2.5 (tenancy) →
> [architecture/hub/tenancy.md](../architecture/hub/tenancy.md), §2.2 (module-system) →
> [architecture/hub/module-system.md](../architecture/hub/module-system.md), y §8–§12
> (instalación, RAG/asistente, entitlement…) →
> [architecture/hub/overview.md](../architecture/hub/overview.md). **§2.7/§2.7.1 SÍ siguen
> aquí.** Las referencias `§2.x`/`§8`-`§12` que quedan sueltas en el texto son residuo de esa
> reubicación.

---

## 0. Propósito

Este documento describe **qué** queremos construir y **por qué**, reconciliando la
visión técnica (Rust/Ionic/module.json) con la **realidad de producción** de
ERPlora (SaaS en Django, marketplace, billing Stripe, provisioning AWS,
contrato S3 + SHA256, auth, asistente AI con RAG).

---

## 0bis. Decisiones finales del proyecto (2026-06-09) — **fuente de verdad**

> Resumen canónico de las decisiones tomadas por el humano y ya **implementadas + verificadas**.
> Consúltese esto primero para saber "cómo tiene que funcionar". Cada punto enlaza con la sección
> que lo detalla y con los ficheros/endpoints reales. `[✓ verificado]` = probado E2E en este repo.

1. **UI / shell unificado SaaS↔Hub** — mismo esqueleto Ionic canónico (`ion-app > ion-split-pane
   content-id="main" when="lg" > ion-menu (sidebar: brand+nav por secciones+tarjeta de usuario) +
   ion-router-outlet#main`). Componentes **Ionic (`ion-*`)**; OutfitKit (`ok-*`) **solo para huecos**
   (p. ej. `ok-data-table`). `apps/web` = Vue 3 + Ionic Vue + Vite. Rail colapsable por CSS. Dark por
   `.ion-palette-dark`. Detalle de UI en §3.1/§7.7. `[✓ verificado]`

2. **Camino de datos (backend de datos) — Postgres-only** — `apps/web` habla con el runtime vía
   `ErploraClient` (`@erplora/module-sdk`, `HttpWsTransport`) → **`erplora-server` (Axum)** en
   `VITE_RUNTIME_URL` (def `http://127.0.0.1:8787`) → **PostgreSQL** (`HUB_DATABASE_URL`, per-hub
   — una BD por hub (ADR-0201) — en cloud; el server falla duro sin él). `ModuleView` **inyecta el cliente** en el Web
   Component del módulo (`wc.client`) para que llame `client.query/command`. Endpoints del runtime:
   `POST /api/query`, `POST /api/command`, `GET /api/navigation`, `GET /api/modules`, `GET /ws`
   (este último exige una API key del hub con lectura desde hub#504 — ADR-0263).
   `[✓ verificado: query/command ejecutan SQL real con scoping hub_id]`

3. **`hub_id` inyectado por despliegue (1 contenedor = 1 hub)** — el server lee `HUB_ID` del entorno
   y lo expone en **`GET /api/hub/context` → `{hub_id, user, cloud_base_url, …}`**; `apps/web` lo
   resuelve al arrancar (`bootHubContext`) y lo envía como **`X-Hub-Id`** en toda llamada. **No hay
   selector de hub.** Liga con la tenancy de §2.5. `[✓ verificado]`
   La misma respuesta trae **`cloud_base_url`** (= `HUB_CLOUD_API_URL`, el valor que ya alimenta la
   CSP `connect-src`): `config.cloudApiUrl` se fija en runtime desde ahí y `VITE_CLOUD_API_URL` es
   solo fallback dev/local; toda llamada al Cloud espera `cloudApiUrlReady()` (hub#1164, una misma
   imagen sirve pre y prod).

4. **Login de usuario real contra el SaaS** — `POST /api/v1/auth/login/` + `GET /api/v1/auth/me/`;
   tokens en `localStorage` (`erplora.access`/`erplora.refresh`); **interceptor refresh-en-401** con
   rotación de ambos tokens y un reintento (`POST /api/v1/auth/refresh/`); `X-Hub-Id` en todas. El
   **fallback demo** queda SOLO tras `VITE_DEMO=1` (producción falla duro). Contrato en §2.3. **Server-side (modelo decidido + implementado, §2.9):** la autoridad de identidad/permisos es **local**. Login por **PIN** o por **JWT de usuario cloud** (verificado RS256 → mapeado a un `hub_user` local) abre una **sesión server-side** (`HUB_AUTH=session`); cada petición lleva `X-Hub-Session` y el runtime resuelve `hub_user` → **permisos del rol** (`role_permissions` de los módulos activos). `hub_id` del despliegue. Verificado vivo: gate por rol real (employee `list`→200, `create`→403). Pendiente menor: argon2id para el PIN; gestión de usuarios/roles (UI admin); credencial de dispositivo de confianza (§14).

5. **Instalación de módulos por el marketplace (API real del SaaS)** — flujo: `GET
   /api/v1/marketplace/modules/{id}/versions/` (sha256) → `GET .../download/?version=` (zip binario) →
   **verificar SHA256** → unzip seguro (anti zip-slip) → `install_from_dir` → `POST .../mark_installed/`.
   En el Hub lo orquesta **`POST /api/modules/request-install {module_id, version}`** (cloud-client +
   source + installer) y emite WS `{"type":"module.installed","module_id"}` → el shell refresca el menú.
   Detalle/contrato en §2.2. **⚠️ Pendiente (SaaS):** `ModuleVersionSerializer` no expone `sha256` por
   `versions/` (solo el endpoint sync) → hoy, si falta, se instala SIN verificación de integridad;
   **arreglar en el SaaS** (añadir `sha256` al serializer) para cumplir el contrato §2.2.

6. **El asistente AI es una CAPACIDAD CORE del Hub, no un módulo de marketplace** (ADR-0033,
   2026-06-13; supera la decisión 2026-06-09 de "módulo instalable"). Está **siempre presente** por
   defecto (✨ del topbar): el proxy está **horneado en el binario** (`crates/server/src/assistant.rs`)
   y el RAG en la tabla `knowledge_chunk` (`crates/vector/src/lib.rs`) — no hay `module.zip`, ni install, ni fila `Module` en el catálogo.
   Su billing es **propio** (`AssistantTier`/`AssistantUsage`, capa gratis con tope + upgrade), fuera de
   `ModulePurchase`/`is_module_entitled`. Su WC alcanza el LLM del SaaS por una **capacidad de host**:
   `POST /api/assistant/chat/stream` del runtime, que hace de **proxy SSE** hacia el SaaS
   (`/api/v1/hub/device/assistant/chat/stream/`, reenvía `Authorization: Bearer` + `X-Hub-Id`)
   con **ensamblado de tools por permiso** (solo queries/commands con bloque `ai:` que el usuario puede
   ejecutar, §9.2). El Hub nunca habla con el LLM directo (§9.3); embeddings/RAG por el proxy del SaaS
   (§9.4/§9.6). La UI de chat de referencia quedó en `apps/web/src/parked/AssistantChat.vue`.

7. **Modelo de eventos del runtime = Outbox transaccional (entrega asíncrona at-least-once)** — ver
   §4 y §5.4 (actualizados). En corto: el command emisor **solo persiste** cada evento en `_event_outbox`
   **dentro de su misma transacción** (escritura atómica); los listeners NO corren inline — los entrega un
   **relay** en background (`erplora-server`, poll 1s) con backoff + dead-letter. **Idempotencia a nivel
   runtime** vía `_event_delivery (event_id, listener_command)` (exactly-once sin que los módulos sean
   idempotentes). La notificación al WS es inline pero **efímera** (solo UI en vivo). `[✓ verificado:
   command emite → 'pending' → relay → 'delivered']`

---

## 1. Visión: "un solo modelo mental" — un solo Hub (Cloud, Postgres)

hub es **una sola app base** (misma UI, mismo modelo de módulos, mismo runtime). Tras
[ADR-0154](../architecture/00-overview/decision-log.md) se entrega como **un único producto**: el
**Hub Cloud** — una **PWA/web shell** que corre en el navegador **y, la MISMA web, dentro de la
app instalable `com.erplora.app`** (escritorio · Android · iOS, ADR-0196), que es quien aporta el
hardware vía `invoke` in-process; **una BD Postgres por hub** (ADR-0201). Se retiró el producto
**Hub Local** (Tauri desktop, como producto separado) y el backend **SQLite**; ya no hay dos
productos ni una matriz de ejes `single`/`cloud` (framing previo retirado por
[ADR-0080](../architecture/00-overview/decision-log.md) y consolidado por ADR-0154):

> **Transporte de datos ([ADR-0050](../architecture/00-overview/decision-log.md)):** un solo runtime
> Axum, **mismo transporte de datos** = **HTTP (RPC) + WebSocket (solo eventos)**. No hay `invoke`/IPC
> **para datos**. El único `DatabaseAdapter` es **`PgAdapter`** (PostgreSQL); el almacenamiento de
> ficheros es **cloud-proxy** (Hub→Cloud→Object Storage), sin rama de disco local.

- **Hub Cloud (PWA)**: el navegador **no puede** abrir TCP crudo (puerto 9100), USB ni
  Bluetooth clásico. Si el usuario necesita hardware físico, el vehículo es la **app instalable**
  `com.erplora.app` (ADR-0196): la misma web dentro del shell Tauri, que aporta los periféricos
  vía `invoke` in-process. Si no lo necesita, imprime por PDF/email o impresora **ePOS-HTTP**
  (alcanzable por navegador).

**Transportes de impresora** — **tres**. El renderizado ESC/POS es el mismo para los tres: lo
único que cambia es por dónde salen los bytes, y quién lo decide es el `printer_id`
(`crates/peripherals/src/discovery.rs`, `parse_print_target`):

| `printer_id` | Transporte | Dónde |
|---|---|---|
| `network:{ip}:{port}` | ESC/POS por TCP al **9100** | todas las plataformas; la única vía con cola y reintentos propios del crate |
| `bluetooth:{mac}` | **Bluetooth Classic SPP** por el plugin Kotlin `crates/tauri-plugin-erplora-android` (ADR-0204, hub#388) | **solo Android** |
| `usb:{queue}` | la **cola RAW del sistema operativo** — `lp -d <cola> -o raw`, filtros fuera (hub#1083) | **solo escritorio** (macOS y Linux, vía CUPS) |

El USB dejó de quedar fuera porque **el driver no es nuestro**: lo pone el fabricante (Star,
Epson), el SO ya es dueño del cable y ESC/POS ya es el idioma que generamos. La razón que lo
mantenía fuera —«un driver por SO no escala»— sigue siendo cierta y por eso el transporte genérico
es **la cola, no una librería USB**. Esa cola no se usa a ciegas: se le pregunta el estado **antes**
de enviar (`lpoptions -p`, atributos IPP —nunca la prosa de `lpstat -p`, que el SO traduce—,
hub#1541) y se comprueba **después** que el trabajo salió de ella de verdad, cancelando el que se
quedó retenido (hub#1564). Sin esas dos comprobaciones, una térmica sin papel daba el tique por
impreso y lo escupía horas más tarde, con un número que la caja ya había dado por fallido.

**Sigue fuera**: **Windows** (mismo diseño contra su spooler, pero sin máquina real donde
verificarlo — hub#1269), el **USB en Android** (exigiría Kotlin, permiso por intent y cables OTG;
ahí la impresora barata ya la cubre el SPP) y las vías `libusb`/WebUSB/OPOS, que reintroducen el
driver por SO. El navegador, sin la app instalable, no abre ninguno de los tres (§2.7.1).

La **cola de impresión vive EN EL HUB** (ADR-0196 §6): el dispositivo con la app instalable la
drena por el WS del runtime. En escritorio, el autostart de la app es un ajuste **OFF por
defecto** (ADR-0204, hub#389).

**Qué se conserva** (en el crate **`crates/peripherals`**, consumido **in-process** por la app
Tauri vía `invoke` — ADR-0196; la **cola de impresión se muda al hub**, ADR-0196 §6):

- **Descubrimiento de dispositivos en red + watchdog** (NECESARIO): detectar impresoras en la
  LAN (escaneo de subred / mDNS), seguir su estado (online/offline) y **re-localizarlas si su
  IP cambia por DHCP**. Sin esto, el usuario tendría que configurar IPs a mano y se rompería la
  impresión al renovar DHCP. → tarea async en `crates/peripherals`.
- **Config de impresoras por terminal** (IP, rol recibo/cocina/barra), persistida.
- **Cola de impresión + reintentos** (impresora apagada / sin papel) — la cola vive en el hub
  (ADR-0196 §6); el dispositivo la drena. **As-built (hub#341):** tabla `_print_queue` (migración
  de sistema v18) + `crates/runtime/src/print_queue.rs` + `POST/GET /api/print/jobs`, idempotente
  por `jobId`. **As-built (hub#342):** registro de **hosts** de impresión — tabla `_print_host`
  (migración de sistema **v22**) + `crates/runtime/src/print_hosts.rs` + `/api/print/hosts`. Un rol
  admite **varios** hosts y un equipo varios roles; la vivacidad **no se almacena**, se deriva del
  último latido (sin noticias durante 3 latidos = no vivo), y el registro sobrevive al reinicio
  porque es configuración, no sesión. `coverage` responde «cuánto espera y cuántos hosts vivos hay»
  por rol. **As-built (hub#343):** el drenaje por `GET /ws/print` (ADR-0262) —
  `crates/runtime/src/print_drain.rs` + `crates/server/src/print_ws.rs` +
  `apps/web/src/lib/print-drain.ts`. **As-built (hub#501, ADR-0265):** el documento
  viaja **ESTRUCTURADO** (`documentType` + `document`, migración de sistema **v25**; el `html` se
  borró) y **no se guarda: se regenera desde la venta**; `apps/web/src/lib/print-host.ts` lo entrega
  a `erplora_print` y el ciclo tique → host → papel está probado contra una térmica real
  (`crates/server/tests/print_to_real_printer.rs`). **As-built (hub#344):** `sdk.print` **ENCOLA**
  — el shell cablea el productor en `apps/web/src/main.ts` (`POST /api/print/jobs`) y la cascada de
  `apps/web/src/lib/print.ts` va bridge → **cola** → navegador: sin app instalada, o con la
  impresora del rol caída, el tique térmico se encola en vez de perderse; el A4 no tiene cola
  térmica y sigue yendo al navegador. Con eso la cadena 4/4 está cerrada. Diseño
  en [architecture/hub/print-queue.md](../architecture/hub/print-queue.md).
- **Enrutado por rol** (recibo vs cocina) cuando un terminal tiene varias configuradas.

El escáner por HID lo maneja el SO/navegador como teclado.

> El escenario **Hub Cloud + hardware físico** **no** queda fuera de alcance: se cubre
> con la **app instalable** (ADR-0196). El POS en navegador es un producto de primera clase (§1),
> no una excepción.

#### 2.7.1 🪦 Bridge standalone — retirado (ADR-0196)

> 🪦 **ADR-0196 retira este componente.** `WsBridgeTransport` **ya no existe** (hub#339): el
> `module-sdk` dejó de exportar el transporte de hardware por WebSocket, y con él se fueron PNA,
> el mixed-content de una página `https` abriendo `ws://localhost` y la clave pública del
> emparejamiento. En un navegador sin la app, `erplora.peripherals` es
> `UnavailableBridgeTransport`: `detect()` contesta `{online:false}` y toda operación de hardware
> rechaza con `hardware_unavailable` — nunca resuelve callando (un tique dado por impreso que no
> ha salido sería el fallo caro).
>
> **La retirada está EJECUTADA** (hub#340, 2026-08-08): del árbol se fueron el standalone
> `apps/bridge` (binario Axum, `GET /status` + `WS /ws` en `localhost:12321`), su pairing
> device-code, su release (`bridge-release.yml` + el MSIX de la 2ª ficha) y las credenciales de
> máquina del bridge — incluido el refresco de `GET /api/bridge/token`, que desde hub#339 pedía
> cada 12 min un secreto con caducidad que **ningún cliente presentaba**. El runtime ya no expone
> esa ruta y `cloud-client` ya no sabe pedirla.
>
> El modelo vigente es la **app instalable** con `invoke` in-process y la **cola de impresión en el
> hub**. Ver [architecture/hub/apps/bridge.md](../architecture/hub/apps/bridge.md) y
> [architecture/hub/crates/peripherals.md](../architecture/hub/crates/peripherals.md).
>
> Queda **el otro lado del cable**: los endpoints `api/v1/bridge/` del SaaS y sus modelos
> (`BridgePairing`/`BridgeDevice`) siguen desplegados, ahora sin un solo llamador en todo el
> código (medido). Su retirada es saas#1274.

| Pieza | Elección | Nota |
|-------|----------|------|
| DB | **PostgreSQL** (`PgAdapter`, per-hub — una BD por hub, ADR-0201) | soporta `pgvector` (clave para RAG, §9) |
| Lógica avanzada | **WASM (Extism)** | Sandbox + ABI lista; evita diseñar una ABI propia al inicio |
| Empaquetado módulo | **module.zip** | manifest + SQL + schemas + UI + WASM + docs, firmado + SHA256 |

**No** se usa: Next.js como core, Node.js en prod local, React Native Web, Capacitor como
runtime, plugins nativos `.so/.dll` dinámicos para terceros.

### 3.1 UI de módulos: Lit vs Stencil (recomendación 2026: Lit)

> Investigado (mayo 2026). **Recomendación: Lit.** Stencil sigue **mantenido** (v4.43.x,
> gobernanza por comité TSC tras la compra de Ionic por OutSystems), no es una apuesta muerta;
> pero el **default del sector en 2026 es Lit**, salvo que necesites generar *wrappers* nativos
> React/Vue/Angular — que **NO es nuestro caso** (nuestro shell es solo Vue 3 + Ionic).

| | **Lit** (Google) | **Stencil** (OutSystems/Ionic) |
|---|---|---|
| Qué es | Librería ~5 KB en runtime sobre WC nativos | **Compilador** → WC optimizados + wrappers React/Vue/Angular |
| Pros | Ligero, cercano al estándar, sin paso de compilación, **default 2026**, respaldo Google | Muy optimizado (lazy-load, scoped CSS, prerender), wrappers multi-framework |
| Contras | Menos "baterías incluidas" | "Caja negra", más complejo; su killer-feature (multi-framework) **no la usamos** |

- **Por qué Lit aquí**: el único consumidor es **Vue 3 + Ionic**; la ventaja única de Stencil
  (multi-framework) no aporta, así que pagaríamos su complejidad sin usar su beneficio. Lit es
  más ligero, más estándar y el camino mayoritario en 2026.
- **Decisión abierta (§14)**: confirmar con un **componente de prueba en cada uno en Fase 0**
  (las guías 2026 lo recomiendan antes de fijar). Por defecto: Lit.

---

## 4. Runtime de módulos en Rust (host genérico)

Rust **no** tiene lógica de negocio hardcodeada. Despachador genérico:

```rust
execute_command("pos.sale.create", payload)
execute_query("inventory.products.list", params)
```

Crate `runtime` (submódulos): `manifest`, `loader`, `registry`, `installer`, `migrations`,
`permissions`, `commands`, `queries`, `events`, `outbox`, `ui`, `wasm`, `errors`.

**Pipeline de instalación** (reconciliado con §2.2):

```
1. Portal valida compra/entitlement → URL S3 firmada + versión + sha256
2. Descargar module.zip de S3
3. Verificar firma ed25519 (autenticidad, hub#239) + SHA256 (integridad)
4. Descomprimir en el store de módulos
5. Leer y validar module.json
6. Comprobar depends_on (orden topológico)
7. Aplicar migrations (PostgreSQL; el dialecto `sqlite` quedó deprecado/ignorado tras ADR-0154)
8. Registrar permisos, queries, commands, eventos/listeners
9. Registrar UI (menú + entry WC)
10. (RAG) Indexar README/ai_context del módulo a su versión (§9)
11. Emitir module.installed → el frontend refresca el menú
```

### 4.1 Entrega y fiabilidad de eventos — Outbox transaccional (decisión 2026-06-09, implementado)

**Problema (estado anterior):** los listeners de un evento corrían *después* del commit del command
emisor y **fuera** de su transacción (dispatch recursivo y síncrono). Sin outbox, retry ni
dead-letter: si un listener fallaba tras commitear (p.ej. `invoice.create_from_sale`), quedaba una
**venta sin factura** y nadie lo reintentaba.

**Decisión (implementada + verificada):** el bus de eventos pasa a **transactional outbox**, con
entrega **100% asíncrona por relay** y garantía **at-least-once**. Tablas de sistema del runtime
(PostgreSQL, las crea el runtime, no un módulo): `_event_outbox` y `_event_delivery`.

1. **Escritura atómica.** Al ejecutar un command, sus eventos `emit` (y, en Tier 2, los que devuelve
   el handler) se **INSERTAN en `_event_outbox` dentro de la MISMA transacción** que el SQL del
   command. Si commitea, el evento existe sí o sí; si revierte, no hay evento. Los commands
   `transaction:false` pasan a **envolverse en transacción**. El `dispatch` inline tras el commit se
   retira.
2. **Relay.** Tarea en background (`erplora-server`, poll ~1s + arranque): lee filas `pending`
   vencidas (FIFO), resuelve los listeners **actuales** de módulos activos (`registry.listeners_for`)
   y ejecuta cada uno. Éxito → `delivered`; fallo → `attempts++` + backoff exponencial en
   `next_attempt_at`; tras `MAX_ATTEMPTS` → `dead` (dead-letter). Los eventos en cascada que emitan
   los listeners → nuevas filas de outbox; guarda de profundidad `MAX_EVENT_DEPTH`.
3. **Idempotencia (exactly-once).** Un listener puede reintentarse; el marcador
   **`_event_delivery (event_id, listener_command)`** se inserta en la **misma transacción** que los
   efectos del listener → nunca corre dos veces aunque el proceso reinicie. Los handlers de módulo
   **no cambian** (idempotencia a nivel runtime).
4. **WS inline efímero.** La notificación al `EventSink` (push a la UI, §7.7) se mantiene inline tras
   commit pero efímera; la entrega DURABLE a listeners es la del outbox.

> Sustituye al antiguo dispatch síncrono recursivo. Código: `crates/runtime/src/outbox.rs`,
> `commands.rs` (`execute_at`/`execute_wasm` + `extra_ops`), `events.rs` (`notify_sink`), relay en
> `crates/server/src/main.rs`. **Verificado:** test de runtime (emisor NO corre listener inline →
> `pending` → relay entrega 1 vez → idempotente) + E2E vivo HTTP (command emite → `_event_outbox`
> `pending` → relay → `delivered`).

---

## 5. Modelo de módulo HÍBRIDO (decisión central)

Declarativo para lo simple, **WASM para la lógica real**, y **SDK tipado** para la UI.

### 5.1 Estructura del `module.zip`

```
inventory-1.2.0.module.zip
├─ module.json            # manifest declarativo (contrato del módulo)
├─ manifest.lock          # generado en build (hashes, versiones resueltas)
├─ migrations/postgres/001_init.sql   # solo dialecto postgres (sqlite deprecado tras ADR-0154)
├─ queries/products_list.sql
├─ commands/stock_decrease.sql
├─ schemas/stock_decrease.json     # JSON Schema (validación en Rust)
├─ ui/ inventory.esm.js + inventory.css   # Web Component (Lit, §3.1)
├─ logic/ stock_rules.wasm         # WASM opcional (Extism)
├─ ai_context.json                 # contexto + tools para el asistente (§9)
└─ README.md / README.es.md        # docs → RAG (§9)
```

### 5.2 `module.json` (reconciliado con el manifest actual)

```jsonc
{
  "id": "inventory",
  "name": "Inventory",
  "version": "1.2.0",
  "depends_on": ["core"],
  "permissions": ["inventory.products.read", "inventory.stock.update"],
  "role_permissions": { "admin": ["*"], "employee": ["inventory.products.read"] },
  "navigation": [
    { "id": "products", "label": "Products", "icon": "cube", "component": "erp-inventory-products" }
  ],
  "migrations": { "postgres": ["migrations/postgres/001_init.sql"] },
  "queries": {
    "inventory.products.list": {
      "permission": "inventory.products.read",
      "sql": "queries/products_list.sql", "schema": "schemas/products_list.json",
      "ai": { "description": "Lists inventory products with their current stock." }
    }
  },
  "commands": {
    "inventory.stock.decrease": {
      "permission": "inventory.stock.update", "transaction": true,
      "sql": ["commands/stock_decrease.sql"],          // declarativo …
      // "handler": { "type": "wasm", "file": "logic/stock_rules.wasm", "function": "decrease_stock" },
      "emit": ["inventory.stock.updated"],
      "ai": { "description": "Adjust stock for a product" }
    }
  },
  "events": { "listen": { "pos.sale.completed": { "command": "inventory.stock.decrease" } } },
  "scheduled_tasks": []
}
```

`ai: { description }` es un bloque **inline** por `query`/`command` (no un `ai_tools` top-level: esa
sección se eliminó — permission/schema/sql se heredan, nunca se redeclaran, §9.2).

**Equivalencias con `module.py`**: `MODULE_ID`→`id`, `MODULE_VERSION`→`version`,
`DEPENDENCIES`→`depends_on`, `PERMISSIONS`→`permissions`, `ROLE_PERMISSIONS`→`role_permissions`,
`NAVIGATION`/`MENU`→`navigation`, `SCHEDULED_TASKS`→`scheduled_tasks`. Lo nuevo:
`queries`/`commands`/`events` declarativos (hoy son código Python), con `ai: { description }` inline
por operación para el asistente.

### 5.3 Niveles de potencia (paga complejidad solo cuando la necesitas)

- **Tier 0 — Declarativo (sin código):** tablas, queries de lista/get, CRUD de una fila,
  permisos/roles, menú, `ai_tools`, scheduled tasks. ~30% de módulos. Máxima seguridad, cero compilación.
- **Tier 1 — Declarativo + capacidades del host:** forma *for-each* para batch sencillo,
  `http.fetch` **mediado** (§5.5). Cubre mucho sin WASM.
- **Tier 2 — WASM tipado (Extism):** lógica real — batch/array (`sale_lines`, `bulk_create`),
  reglas fiscales/descuentos, validaciones dependientes de BD, importadores. El WASM **no**
  toca la BD: recibe input y devuelve *intenciones* (SQL declarado + eventos) que Rust valida
  y ejecuta. Se escribe con el **guest SDK** (§7.3).
- **Escape hatch — Plugins nativos first-party (compilados en el host):** módulos de ERPlora
  **críticos en compliance/rendimiento** (`verifactu`, AEAT, `payroll`) enlazados en el
  binario. La visión dice "no plugins `.so/.dll` al inicio" — correcto **para terceros**
  (solo Tiers 0–2); los módulos propios de ERPlora sí.

**Composición entre módulos:** un command/query puede invocar **queries/commands públicos
de otros módulos** (con permisos) vía host functions, sin importar su código.

### 5.4 Comunicación entre módulos (contratos, no imports)

- Correcto: POS llama `inventory.products.list` (query pública) y emite `pos.sale.completed`;
  Inventory escucha y ejecuta `inventory.stock.decrease`.
- Incorrecto: POS accede a tablas privadas de Inventory, importa su JS, o ejecuta SQL
  arbitrario. Todo va **namespaced** (`modulo.entidad.accion`).

> ⚠️ **Los eventos reales corren código, no un mapeo `evento→command`.** En producción, el
> handler de `pos.sale.completed` **carga la venta, itera líneas, aplica `allow_negative_stock`,
> clampa a cero y cascada** a otros módulos. La forma declarativa solo sirve para fan-out
> trivial; cualquier handler con lógica es **Tier 2 (WASM)**. Refuerza el modelo híbrido (§6).

> **Entrega de eventos (decisión 2026-06-09):** el fan-out a listeners es **asíncrono y durable**
> vía el **Outbox transaccional** del runtime (§4.1), no una llamada inline. El emisor solo persiste
> el evento en su misma transacción; un relay lo entrega at-least-once con idempotencia exactly-once
> (`_event_delivery`). Aplica tanto al fan-out declarativo como a la cascada de handlers Tier 2.

### 5.5 Capacidades del host (Tier 1) — `http.fetch`: el host es DECORADOR, no cortafuegos (ADR-0431/0432)

El host (Rust) expone un conjunto **cerrado** de capacidades que un módulo Tier 0/1 puede
usar de forma declarativa, sin WASM y sin acceso crudo a recursos:

- **`http.fetch` es abierto por diseño (ADR-0431, 2026-09-02 — enmienda la allowlist descrita
  aquí hasta esa fecha, que nunca llegó a construirse: `crates/runtime/src/capabilities.rs::require`
  solo comprueba que el módulo declare la capability `network` y que el usuario la haya
  concedido, ninguna URL).** El módulo elige el destino con total libertad; el campo
  `"network": { "allow": [...] }` del manifest es **documentación para la pantalla de
  consentimiento**, no un control del runtime — un filtro real habría dejado sin salida a la AEAT
  al propio `verifactu`, que no declara `network`.
  1. El módulo declara en `module.json` los secretos del tenant que necesita (por nombre lógico,
     **nunca** el valor): `"network": { "secrets": ["stripe_api_key"] }`.
  2. El usuario/admin **concede** la capability al instalar.
  3. En runtime el módulo llama `host.http_fetch({ url, method, headers, body, secret_ref })` a
     la URL que quiera. El host ejecuta la llamada, **inyecta el secreto del tenant** cuando
     `secret_ref` lo pide (el módulo nunca ve el valor), aplica timeouts/rate-limit y audita
     (módulo, destino, resultado).
  4. **Lo que SÍ acota el host son SUS PROPIAS credenciales** (ADR-0431 §2): `X-Hub-Id`,
     `X-Hub-Token`/`X-Api-Key`, el `Authorization: Bearer` del usuario y `X-Webhook-Secret` solo
     viajan a hosts de confianza (`HUB_CLOUD_API_URL` + `HUB_TRUSTED_HOSTS`); a cualquier otro
     destino la petición sale **sin** esas cabeceras (con un `warn`). `http.fetch` nace **sin**
     credenciales de ERPlora — si un módulo necesita hablar con NUESTRO Cloud con identidad de
     máquina usa el primitivo separado `cloud_call`, nunca `http.fetch`.
  5. **`identity: "machine"` es la única identidad de `http.fetch` que sí acota destino** (ADR-0432,
     2026-09-03) — precisamente porque presta una credencial de ERPlora, no porque desconfíe de la
     URL: se limita a la misma lista de hosts de confianza y solo la conceden módulos
     first-party firmados (`capabilities.certificate.purposes: channel-machine`/`cloud-call`).
  6. Los secretos del tenant viven cifrados (Fernet/KMS) y solo los desreferencia el host.

Así un **tercero puede publicar integraciones** (pago, envío, mensajería) contra cualquier
destino de su elección, sin que el hub le preste jamás una credencial de ERPlora ni le exponga
un secreto del tenant en claro.

> **Lo que NO es una capacidad del host: `render.pdf`/`render.xlsx`** (hub#1237). Esta sección las
> anunció durante toda la Fase 5 y nunca se implementaron: no hay `CapabilityKind` para ellas, no
> se pueden declarar en `module.json` y ningún módulo las puede pedir. Un contrato que promete lo
> que no existe es una mentira a los autores de módulos, así que se retiran en vez de congelarse
> (contrato del kernel, ADR «El Hub se CIERRA como KERNEL»). Un documento se genera hoy en el
> módulo que lo necesita; si algún día el host lo hace, entrará por una ADR y con su
> `CapabilityKind`, no por una línea de esta lista.

> Lo **crítico-fiscal** (`verifactu`/AEAT con mTLS PKCS#12, `payroll`) **no** usa esta vía:
> va por **plugin nativo first-party** (Opción B, escape hatch §5.3).

### 5.6 Puntos de extensión y paridad de framework (a no perder)

El modelo de módulos debe ofrecer estos mecanismos en equivalente declarativo/WASM:

- **Slots** (inserción de UI entre módulos, p. ej. un módulo añade un widget al dashboard de
  otro) → el manifest declara `slots` que provee/consume; el shell los compone.
- **Hooks/filters** (`sale.line_price` y similares: un módulo altera datos de otro) → se
  expresan como **listeners/commands** (Tier 2 WASM cuando hay lógica), no como import de código.
- **Scheduled tasks** (hoy EventBridge → hub vía `X-Webhook-Secret`) → `scheduled_tasks` del
  manifest, ejecutadas por el runtime; en cloud las dispara el Portal igual que hoy.
- **i18n** (ES/EN) → catálogos de traducción por módulo dentro del `module.zip`.

> Cerrar esta paridad es **multi-fase**, no MVP (§12/§14). Se lista aquí para que el modelo
> de módulos la contemple desde el manifest.

---

## 6. ¿Es fácil hacer módulos con `module.json`? (assessment honesto)

**Respuesta corta: sí para CRUD declarativo; no para todo.** Un `module.json` puro
(manifest + SQL) es excelente para listar/crear/editar entidades simples, portable y
seguro. Pero **rompe** en lo que un ERP real necesita a diario:

| Necesidad | ¿Puro declarativo (SQL)? | Solución en el modelo híbrido |
|-----------|--------------------------|-------------------------------|
| CRUD simple | ✅ Fácil | SQL declarativo (Tier 0) |
| **Batch/arrays** (sale_lines, importar CSV) | ❌ La visión lo deja "TODO" | **WASM** devuelve N operaciones (Tier 2) |
| **Reporting/agregación** | ⚠️ SQL complejo, frágil | SQL + WASM para post-proceso |
| **Flujos multi-paso** (factura→stock→asiento) | ❌ | WASM + composición de commands |
| **Integraciones externas** (WhatsApp, fiscal, pasarelas) | ❌ | `http.fetch` mediado (Tier 1) o nativo |
| **Validación > JSON-Schema** | ❌ | WASM (`invariants`) |
| **PDF / Excel** | ❌ | Lo genera el módulo (no hay capacidad host — retirada en hub#1237) |
| **Cross-módulo** | ⚠️ solo vía eventos | Host functions (query/command de otros) |

**Ergonomía.** Un módulo con poder de código arbitrario (SQLAlchemy, servicios, hooks,
PDF/Excel) tiene poder total, pero el puro declarativo es un retroceso brutal frente a eso.
El híbrido recupera ese poder **dentro de un sandbox** y con **contratos** (permisos
namespaced, schemas), ganando portabilidad y seguridad.

**Recomendación (confirmada): modelo HÍBRIDO.** No puro-declarativo (incapaz de
batch/reporting/integraciones/PDF); no seguir en Python (ata el runtime a Python, sin
sandbox, sin modelo unificado local/cloud).

**La evidencia está en producción.** `verifactu` (cadenas hash AEAT, XML, QR, contingencia),
`payroll` (`calculation.py`), `communications` (SMTP/IMAP) e `inventory`
(`bulk_create_products`/`receive_stock` iterando arrays en una transacción) **ya son
código** hoy. Ninguno es expresable en SQL declarativo.

> 🔀 **Fork de red.** El sandbox WASM **no tiene red**. Varios módulos necesitan red saliente:
> `communications` (SMTP/IMAP a host arbitrario), `whatsapp_inbox` (Meta Graph), `verifactu`
> (AEAT vía mTLS PKCS#12), con credenciales **cifradas** y descifradas en memoria. En WASM eso
> no está disponible directamente.
> ✅ **Decisión — Opción A** para integraciones genéricas de terceros: capacidad
> **`http.fetch` mediada por el host** (allowlist + credenciales inyectadas + auditoría;
> contrato en §5.5). **Opción B (nativo first-party)** para lo crítico-fiscal
> (`verifactu`/AEAT, `payroll`) que necesita mTLS/cert y rendimiento.

**Coste honesto:** el híbrido sube el listón de autoría (compilar WASM y WC) y exige
**buena DX** (CLI + plantillas + SDK guest). De ahí la inversión en SDK/CLI (§7) y la
decisión de **Extism** para no diseñar una ABI WASM desde cero.

---

## 7. SDKs y herramientas (sí, hacen falta)

### 7.1 `@erplora/module-sdk` (TypeScript, frontend)

```ts
await erplora.query("inventory.products.list", { limit: 50, offset: 0 });
await erplora.command("pos.sale.create", { customer_id: "cus_1", lines: [...] });
erplora.on("inventory.stock.updated", e => { /* … */ });
const can = await erplora.hasPermission("pos.sale.create"); // solo para UI
erplora.notify({ type: "success", message: "Venta creada" });
```

Con **transport abstracto**:

```ts
interface ErploraTransport {
  query(name: string, params: unknown): Promise<unknown>;
  command(name: string, payload: unknown): Promise<unknown>;
  subscribe(event: string, cb: (e: unknown) => void): void;
}
// Modelo decidido (ADR-0050): el SDK usa HTTP+WS contra el runtime Axum (no hay IpcTransport).
// HttpWsTransport → HTTP POST query/command + WebSocket solo para eventos.
// (WsTransport — todo por un WS — queda como alternativa, no por defecto; §7.5)
```

> `hasPermission` en JS es **solo** para mostrar/ocultar UI. La seguridad real está siempre
> en Rust, que revalida en cada query/command.

### 7.2 `@erplora/module-types` (tipos + JSON Schema)

Tipos TS del manifest + JSON Schema de `module.json`, **generados desde
`schemas/module.schema.json`** (fuente única del contrato, compartida por Rust/TS/CLI).

### 7.3 `crates/guest-sdk` — SDK *guest* para WASM (Rust)

Crate que usan los autores de lógica WASM: macro `#[command]`/`#[query]`, serialización
JSON in/out (ABI Extism), y **host functions** (ejecutar un query/command permitido, emitir
evento, `http.fetch` en allowlist). El guest devuelve *intenciones*; nunca
toca la BD. Sin esto, escribir WASM es inviable.

> **Guest = el código que corre DENTRO del sandbox** (el "invitado"), frente al **host**
> (Rust, el "anfitrión"). Extism permite escribir el guest en **Rust/JS/Go/Python**:
> - **Rust-only (recomendado para empezar)**: el autor escribe la lógica en Rust → WASM más
>   pequeño y rápido, un solo toolchain. Contra: excluye a quien no sabe Rust.
> - **Multi-lenguaje**: permite JS/Go/Python → baja la barrera de autoría (más gente puede
>   publicar módulos con lógica), a cambio de WASM más grande y más toolchains que soportar.
> Por defecto **Rust-first**, con la puerta abierta a más lenguajes sin rediseñar el host
> (decisión en §14).

### 7.4 CLI `@erplora/module-toolkit` (repo propio en la raíz del monorepo)

El CLI vigente es **`erplora`**, sin subcomando `module` (ese prefijo es sintaxis vieja que ya
no existe):

```
erplora startproject <n>        # workspace de dev que puede contener varios módulos
erplora g module <id>           # genera un módulo (repo propio): manifest + WC Lit + SQL + fixtures
erplora dev <id|dir> [puerto]   # preview del WC con transporte mock, CSP estricta, watch
erplora build <id|dir>          # compila el WC (Lit) a dist/, y el handler WASM si aplica
erplora validate <id|dir> [--pg] # valida manifest + CSP + handlers WASM; con --pg, prepara el SQL contra un Postgres efímero
erplora pack <id|dir>           # module.zip + manifest.lock.json + SHA256
erplora sign <id|dir>           # (re)calcula el SHA256 del zip
erplora publish <id|dir>        # imprime el flujo de publicación al marketplace del SaaS (§2.2)
erplora test <id|dir> --against-hub  # baterías e2e del módulo contra un hub real (hub#1264/#1381)
```

### 7.5 Transporte y comunicación — ¿todo por WebSocket?

**No.** El transporte de datos es **HTTP para RPC + WebSocket solo para eventos**, no "todo por un
WS". WS-only obligaría a reimplementar el framing RPC (correlación de IDs, timeouts, replay) que
HTTP da gratis.

**Modelo decidido ([ADR-0050](../architecture/00-overview/decision-log.md)):** el shell web habla
**HTTP+WS** contra el runtime Axum. Se **eliminó** `invoke`/IPC para datos. El backend es **PostgreSQL**
(`PgAdapter`) y los ficheros van por **cloud-proxy** a Object Storage (Hub→Cloud), sin rama de disco
local.

| Qué | Hub Cloud — Axum |
|-----|------------------|
| `query` / `command` (RPC) | **HTTP POST** (`/api/query`, `/api/command`) |
| Eventos / push | **WebSocket** (`/ws`, solo push) — credencial obligatoria (API key con lectura, ADR-0263) |
| App Ionic + assets | **HTTP/CDN** |
| Bundles UI de módulos | **HTTP/CDN** |
| Descarga `module.zip` | **HTTP** (Object Storage) |
| Exports PDF/Excel | **HTTP** |
| SaaS (marketplace, billing, embeddings/LLM) | **HTTP REST** (user-JWT + `X-Hub-Id`) |

> **Canal de hardware ([ADR-0196](../architecture/00-overview/decision-log.md), que sustituye al
> modelo de ADR-0050):** lo aporta la **app instalable** `com.erplora.app` por `invoke`
> in-process; el Bridge standalone se retiró (§2.7.1). El navegador no abre TCP crudo (puerto
> 9100), USB ni Bluetooth: por eso imprimir desde una pestaña sin la app requiere una impresora
> **ePOS-HTTP**.

**Escala**: un hub tiene **1–5 usuarios (máx ~30)**, con tolerancia a crecer. A esa escala
el rendimiento **no decide**; deciden resiliencia y simplicidad:

- **Degradación elegante (clave para un TPV)**: si el WebSocket cae, las **ventas siguen
  por HTTP**; solo se pierden las actualizaciones en vivo. Con WS-only, si el socket falla, **todo** falla.
- **Más simple**: HTTP no necesita framing RPC sobre WS. **Tooling estándar** (reintentos,
  idempotencia, `curl`, proxies/CDN). WebSocket queda **solo para push**.

> **Decisión: HTTP (RPC) + WebSocket (solo eventos).** WS-only queda como
> alternativa (todo por un solo canal), pero no por defecto.

### 7.6 Garantía: el runtime Rust es la única autoridad de datos

> **Modelo decidido ([ADR-0050](../architecture/00-overview/decision-log.md)):** el shell web usa
> **HTTP+WS** contra el runtime Axum; no hay `IpcTransport` ni backend local.

- ✅ **Runtime Rust implementado, compila y pasa tests**: `crates/db` (**PostgreSQL** vía `PgAdapter`,
  traductor `:n`→`$n`) + `crates/runtime` (manifest → migraciones idempotentes → registry → permisos →
  queries/commands en transacción → bus de eventos), con **scope `hub_id`** e inyección de
  `:hub_id/:current_user_id/:now/:new_id`. Módulo `modules/inventory` con SQL real (migración,
  query, 2 commands, listener). Ejemplo `walking_skeleton` + tests de integración contra un
  **Postgres real** (schema efímero por test vía `erplora_db::testutil`; CI con service container
  `postgres:18`).

### Fase 2 — Núcleo declarativo
commands/queries/permisos/migrations/eventos + validación por schema + topo-sort/lifecycle.
**Decidir e implementar el modelo de tenancy** (§2.5, ya fijado: hub_id + DB-por-org).
**Auth de usuario** (§2.9): tabla local de usuarios/roles/PIN, primer login email+password
online + dispositivo de confianza, refresh oportunista de tokens. **Adelantar el `validate`
del CLI** (lint SQL + namespacing + predicado `hub_id`).

### Fase 3 — Cross-módulo (Inventory + POS)
POS usa `inventory.products.list`, emite `pos.sale.completed`, Inventory descuenta stock.
Primer WASM (batch `sale_lines`) o forma *for-each* Tier 1.

### Fase 4 — Hub Cloud
Axum + PostgresAdapter + Docker + transport HTTP/WS, integrado con el SaaS sin
cambios. Instalación desde el marketplace real (`source/s3_source` + `cloud-client`).
- **SaaS-side**: enseñar al **sync Git a leer `module.json`** (`manifest_kind`, §2.6) y
  enchufar instalaciones en `Module`/`ModulePurchase`/`HubModuleInstallation`. Exponer
  `ai_tools` por el proxy de asistente existente.

### Fase 5 — WASM + tooling + RAG
`wasm-host` (Extism) + `guest-sdk`; portar `sale_create`/reglas a WASM; capacidades host
(`http.fetch` mediado §5.5); CLI completo + firma; `ai_tools` +
`search_docs` (pgvector cloud + degradación local §9.5).

### Fase 6 — Cierre
Conversión de módulos **completada** (27 módulos declarativos; source en `modules-workspace/modules/<id>/`,
cada uno su propio repo git — `hub/modules/` es solo para instalados en runtime).
Queda implementar los handlers Tier 2 WASM + la reubicación del Bridge (§13).

---

## 13. Trabajo pendiente de plataforma (alto nivel)

> La **conversión de módulos** está **hecha**: los 27 módulos son declarativos (2026-06-02); el
> source vive en `modules-workspace/modules/<id>/` (cada uno su propio repo git; `hub/modules/` = instalados).
> Lo que **queda** es implementar los handlers **Rust→WASM Tier 2**
> (documentados en los `WASM-TODO.md` por módulo) y la **reubicación del Bridge** (§2.7).

- **Módulo `warehouse` (WMS avanzado) — a futuro (decisión 2026-06-09).** El **stock básico** vive
  y se queda **dentro de `inventory`** (producto y existencias son un solo agregado: `product.stock`
  + `inventory.stock.*`). La **gestión avanzada de almacén** (multi-almacén/ubicaciones,
  transferencias, lotes/caducidad, números de serie, bins, recuentos cíclicos, valoración FIFO/medio)
  irá en un **módulo `warehouse` SEPARADO que DEPENDE de `inventory`**: llama sus contratos públicos
  (`inventory.products.*`) y escucha sus eventos, **nunca** toca el `product.stock` privado. No se
  implementa ahora; se construye cuando aparezca demanda real (manufactura/distribución).
- **Bridge (§2.7)**: el `bridge/` **no** se retira — es el componente de hardware **standalone
  (red-only)**, alcanzado por localhost HTTP/WS desde la web shell. Su lógica
  (registro/watchdog/cola/routing de impresión) vive en `crates/peripherals`. Resolver
  multi-dispositivo (§2.7b).
- **Agrupación de módulos**: se conserva la misma clasificación/grupos del catálogo; la
  clasificación vive en el SaaS, no en el `module.json` (§2.4).
- **Contrato marketplace intacto**: el SaaS descarga el zip + verifica SHA256; la ruta S3 y la
  integridad no cambian.

### 13.1 Imagen del Hub: canales de release (hub#1170, decisión 2026-08-25)

`build-hub.yml` publica `ghcr.io/erplora/hub` en **tres tags móviles**, siempre acompañados del
`:<sha>` inmutable (pin/rollback). La lógica vive en `scripts/image-tags.sh` (tests de contrato en
`scripts/tests/image-tags.test.sh`) y la **versión que sirve el binario** (`/readyz`,
`/api/hub/context`, latido, `error_sink`) es la que el CI estampa en `Cargo.toml` antes de compilar:

| Canal | Lo dispara | Versión horneada | Tags |
|---|---|---|---|
| **`dev`** | push/dispatch en `develop` — lo despliega **pre** | `X.Y.Z-dev.<n>+g<sha>` — `X.Y.Z` es **un patch por encima** del tag `v*` más nuevo que el repo **tiene** (`git tag --list`; hub#1625: `main` es huérfano y `git describe` se quedaba diez releases atrás); `<n>`/`<sha>` de `git describe --tags --long` | `:dev` |
| **`canary`** | tag `vX.Y.Z-rc.N` — candidata para un **subconjunto** de hubs de prod | `X.Y.Z-rc.N` | `:X.Y.Z-rc.N` `:canary` (NO mueve `:latest`, `:X.Y` ni `:X`) |
| **`stable` = `latest`** | tag `vX.Y.Z` final — lo que estrena todo hub nuevo | `X.Y.Z` | `:X.Y.Z` `:X.Y` `:X` `:latest` `:stable` (alias, mismo digest) |

`main` sigue como hasta ahora (`:latest` + `:<sha>`, versión del Cargo: main = prod). El guard
rechaza un tag no semver, ya publicado, no monótono o una rc de una versión ya cerrada, y en
`develop` se **niega** a publicar sin `git describe` o sin un solo tag `v*` antes que hornear el hueco `1.0.0`. Un tag
`-rc.N` **no** dispara `tauri-release.yml` (las stores son irreversibles).

---

## 14. Riesgos, unknowns y decisiones

| Tema | Estado |
|------|--------|
| **Multi-tenancy** | ✅ **Decidido y completo (ADR-0201, 11/11, 2026-08-06)**: **una BD Postgres por HUB** (`Hub.database_name`), no por organización — la `Organization` **ya no existe**; `hub_id` por fila, scope inyectado por el runtime (§2.5). No es `tenant_id`. |
| **IDs de fila** | ✅ **Decidido (ADR-0035)**: **PK = UUID v4 (`TEXT`) en TODO** el dato de negocio (PostgreSQL per-hub, ADR-0201), no autoincremental; `hub_id` (UUID) sigue siendo el discriminador de tenant. UUID globalmente único (§2.5). |
| **Transporte cloud** | ✅ **Decidido**: HTTP (RPC) + canal de push dedicado (§7.5). WS-only descartado como default. |
| **Canal de eventos (push)** | 🔶 **Abierto**: **WS (actual) vs SSE** para el push servidor→cliente. El push es **unidireccional** (los envíos van por HTTP) ⇒ SSE encaja: da **reconexión + Last-Event-ID gratis** (ayuda con el idle timeout del ALB), mantiene **HTTP estándar** (criterio §7.5) y es el formato natural para el **futuro streaming del assistant**. Plan: implementar **ambos** y elegir por situación; al hacerlo, **unificar la forma del JSON del evento** (`name` server vs `event` cliente — hoy desalineado) entre WS y SSE. |
| **Entrega/fiabilidad de eventos** | ✅ **Decidido (2026-06-09)**: **transactional outbox** — escritura atómica en `_event_outbox`, **relay asíncrono** at-least-once con backoff + dead-letter, idempotencia vía `_event_delivery` (§4.1). Sustituye el dispatch inline. **Implementado + verificado** (`crates/runtime/src/outbox.rs` + relay en server). |
| **Documentos de venta / POS** | ✅ **Decidido (2026-06-09)**: tiquet/factura = **FORMATO** de render (`ok-receipt` 80mm / `ok-invoice` A4 en OutfitKit), no módulo; `sales` = libro mayor; pantallas POS **seleccionables** por el negocio; impresión térmica por bridge ESC/POS (§15). |
| **Red saliente de módulos** | ✅ **Decidido (ADR-0431/0432)**: `http.fetch` **no acota destinos** — el host es un decorador, no un cortafuegos; solo acota **sus propias** credenciales (hosts de confianza) y la identidad de máquina de `cloud_call`/`identity:"machine"` (§5.5). **B (nativo)** sigue para lo crítico-fiscal. |
| **Hardware / periféricos** | ✅ **Decidido (ADR-0196, sustituye a ADR-0050)**: el `bridge/` standalone **se retiró** (hub#340) → el hardware lo aporta la **app instalable** por `invoke` in-process, §2.7.1. ✅ **Tres transportes** (§2.7): red (TCP 9100) en todas las plataformas, **SPP en Android** (ADR-0204, hub#388 — cerrada, `BluetoothSpp.kt` implementado) y la **cola RAW del SO** por USB en escritorio (hub#1083, ADR-0441). Fuera: Windows (hub#1269), USB en Android, `libusb`/WebUSB. Abierto: multi-dispositivo (primary↔satellite). |
| **Modelo de módulos** | ✅ **Decidido**: híbrido (declarativo + WASM + SDK). |
| **Offline** | ✅ **Decidido (ADR-0154): un solo Hub, Cloud/Postgres, online-only.** Se retiró el producto **Hub Local** (SQLite, offline) — ya no hay dos productos ni motor de sync (ADR-0040 «sin sync» sigue en pie). Los backups son responsabilidad del Cloud (pgBackRest/PITR), no del Hub. |
| **Login de usuario** | ✅ **Decidido**: 1er login email+password online → dispositivo de confianza → PIN (offline a futuro); usuarios cloud y solo-locales (§2.9). |
| **Reactividad UI** | ✅ **Decidido**: eventos WS → el WC re-consulta (§7.7). Sustituye a LiveComponent. |
| **ABI WASM** | ✅ **Decidido: Extism.** As-built en `crates/wasm-host` (sandbox real, no hay otra ABI en el árbol); WASI/propia descartadas de facto. |
| **Paridad de framework** | Abierto: slots, hooks/filters, scheduled tasks, i18n → equivalentes declarativos/WASM (§5.6). Multi-fase. |
| **Entitlement en runtime** | Abierto: qué pasa con un módulo (y sus datos) si caduca su suscripción (desactivar / read-only). |
| **Credencial de dispositivo de confianza** | Abierto: formato/rotación de la credencial que habilita el PIN offline (§2.9). |
| **SQL portable** | ✅ **Resuelto (ADR-0154)**: Postgres-only; el dialecto `sqlite` quedó deprecado/ignorado. Sin capa de portabilidad. |
| **RAG / vector** | ✅ **Implementado y en boot**: `PgVectorStore` (`crates/vector/src/pg.rs`) se instancia en `crates/server/src/boot.rs` cuando la BD del hub tiene `pgvector`; si no lo tiene (imagen sin la extensión, o el rol del hub no puede crearla — ADR-0201 da a cada hub su propia BD/rol) el arranque **nunca aborta**: el índice queda `None` y el asistente degrada a ofrecer todas las tools. `MemoryVectorStore` sigue siendo solo referencia/test (§9.5). |
| **UI de módulos (Lit vs Stencil)** | ✅ **Recomendado Lit** (§3.1, default 2026; no necesitamos wrappers multi-framework). Confirmar con PoC de ambos en Fase 0. |
| **Guest WASM lenguaje** | Rust-only (recomendado, WASM pequeño/rápido) vs multi-lenguaje (JS/Go/Python vía Extism, baja la barrera de autoría). |
| **Impresión / primary-satellite** | ✅ Impresoras de red por terminal; hardware vía la **app instalable** (`invoke` in-process, ADR-0196) con **tres transportes** — red, USB (cola RAW del SO) y Bluetooth SPP en Android (§2.7). Abierto: descubrimiento primary↔satellite y promoción si cae el primario (§2.7b). |
| **Agrupación de módulos** | ✅ Se conserva la clasificación/grupos del catálogo (vive en el SaaS, §2.4/§13). |
| **Esfuerzo total** | Cambio de plataforma completo; plan de recursos/tiempo realista. |

**Riesgos concretos a vigilar:**
- **El sync Git del SaaS parsea `module.py`** (§2.6) → sin `manifest_kind`, no ingiere `module.json`.
- **Inmutabilidad S3**: republicar un `v{ver}.zip` rompe SHA256 de clientes (el SaaS lo bloquea).
- **WC dinámico + CSP estricta**: el JS de módulo no puede exigir `unsafe-inline`/`eval`.
  ✅ Validado en `apps/web` (Vue 3 + Ionic 8.8 + Vite + TS + Tailwind + Iconify) +
  `modules/inventory` (Lit + ESM + `import()` dinámico): **0 violaciones de CSP de script** en
  Chrome headless contra el build de prod; el CLI `build` verifica CSP-safe en cada compilación.
  ⚠️ **@ionic/react SÍ requiere `style-src 'self' 'unsafe-inline'`** (estilos inline; riesgo bajo).
- **Determinismo y límites de WASM**: fuel/timeouts/memoria + no-determinismo controlados por el host.
- **Regresión de features vs el hub actual**: LiveComponents (resuelto, §7.7), slots,
  hooks/filters, scheduled tasks, i18n (§5.6), pipeline `@action`→AI-tool. Cerrar el hueco es
  multi-fase, no MVP.

---

## 15. Ventas, documentos de venta y POS (decisiones 2026-06-09)

Consolidación de cómo se vende y cómo salen los comprobantes. **Vinculante.**

### 15.1 `sales` es el libro mayor de ventas
Toda venta —de cualquier canal— se materializa con **`sales.complete_sale`** (Tier 2 WASM), que
calcula líneas/impuestos/total, inserta venta+líneas en una transacción y emite
**`sale.completed`**. `sales_sale` lleva `channel` + `source_module` (texto libre) para trazar el
origen. Escuchan `sale.completed`: `inventory` (stock), `customers`, `cash_register`,
`kitchen_orders`; e **`invoice`** crea el documento fiscal (F1/F2/R1) y `verifactu` el registro
AEAT. La fiabilidad de esa cadena la da el **outbox (§4.1)**.

### 15.2 Canales de venta (todos → `sales`)
| Canal | Estado | Entra a `sales` por |
|-------|--------|---------------------|
| Mostrador táctil | pantalla a construir (`erp-pos-touch`) | UI → `complete_sale` |
| Retail escáner/teclado | pantalla a construir (`erp-pos-desktop`) | UI → `complete_sale` |
| WhatsApp | **existe** (`whatsapp_inbox`) | conversación → request (IA) → `fulfill` → `orders`/`sales` |
| Teléfono / B2B | **existe** | `orders.create` → `complete` → `link_to_sale` |
| Restauración / mesas | parcial | `tables`+`kitchen_orders` → cobro `complete_sale` (`channel='table'`) |
| Carta pública + email | **futuro (no existe)** | catálogo público; pedido por WhatsApp/email |

**No hay e-commerce ni checkout online.** `cart_checkout` es **carrito interno / tickets
aparcados** del POS, no una tienda pública.

### 15.3 Tiquet vs factura = FORMATO de render, no módulo
El comprobante es un **formato de presentación**, no un módulo nuevo:
- **Tiquet 80mm** → `ok-receipt`; **factura A4** → `ok-invoice` (ambos en **OutfitKit**,
  presentacionales y aislados: reciben un JSON `ReceiptData`/`InvoiceData` y lo pintan; reusan
  `ok-qr`). No hablan con el backend.
- La **semántica fiscal** ya vive en `invoice` (F2 = tiquet/simplificada, F1 = completa, R1 =
  rectificativa). "No todos dan tiquet / unos sacan A4" se resuelve **instalando o no
  `invoice`/`verifactu`** + un ajuste de formato. (Excepción consciente a "el dominio vive en los
  módulos": estos dos renderers son **genéricos** y viven en OutfitKit.)

### 15.4 Mismo dato, dos rutas de impresión
Un **único contrato** (`ReceiptData`/`InvoiceData`) alimenta:
- **Tiquet 80mm físico → bridge (ESC/POS)** por `document_type` (`crates/peripherals`,
  `erplora_print`). `ok-receipt` (HTML) se usa para **previsualización/PDF**, no para la térmica.
- **Factura A4 física / PDF → `ok-invoice` (HTML)** vía `window.print()` / WeasyPrint (SaaS).

### 15.5 Pantallas de venta seleccionables por el negocio
El POS no es una sola pantalla: el negocio **elige la que encaja con su negocio**
(`erp-pos-touch` táctil de mostrador, `erp-pos-desktop` con escáner/teclado; futura de
restaurante). Son **componentes separados**, todos llaman al mismo `complete_sale`. La elección
vive en `sales_settings.pos_layout`.

### 15.6 Configuración del POS (`sales_settings`)
La config singleton de `sales` (una fila por `hub_id`) se cablea con `sales.settings.get` +
`sales.settings.update`. Campos de formato: `pos_layout` (`touch|desktop`),
`default_document_format` (`ticket|invoice`), `auto_invoice_with_tax_id` (cliente con NIF →
factura A4). El **override por venta** se registra en `document_type` de la propia venta (atómico
con ella; viaja en `sale.completed` para que `invoice` emita F1/F2).

---

## Resumen mental

```
module.json = contrato del módulo (lo técnico; la clasificación vive en el SaaS)
WebComponent = pantalla del módulo (Lit; §3.1)
Rust = autoridad / runtime genérico (execute_command / execute_query)
PostgreSQL (per-hub en cloud, ADR-0201) = solo Rust accede; hub_id (UUID) por fila + PK = UUID v4 (TEXT)
WASM (Extism) = lógica avanzada y batch, en sandbox (sin red/BD libres)
SDK TS = puente para la UI (HttpWsTransport contra el runtime Axum; sin IpcTransport, ADR-0050)
Hub = un solo producto (ADR-0154): Cloud, PostgreSQL, online-only (PWA + app instalable Tauri). Sin Hub Local ni SQLite ni sync. Backups = responsabilidad del Cloud (pgBackRest/PITR)
Login = email+password online (setup) → dispositivo de confianza → PIN (offline a futuro)
Reactividad = evento (WS; ADR-0050) → el WC re-consulta (no server-render)
Eventos = transactional outbox (escritura atómica + relay async at-least-once + _event_delivery); WS solo push UI (§4.1)
Venta = sales (libro mayor) → sale.completed; tiquet/factura = FORMATO (ok-receipt/ok-invoice), no módulo; pantallas POS seleccionables (§15)
RAG = PgVectorStore implementado y wireado en boot (crates/server/src/boot.rs); sin pgvector en la BD degrada a None → todas las tools
AI = embeddings + generación SIEMPRE por el proxy del SaaS (medido)
Red de módulos = http.fetch ABIERTO (el host no acota destino, solo SUS credenciales — ADR-0431/0432) / nativo para fiscal
1 producto = Hub Cloud (PostgreSQL, PWA, online) — ADR-0154 retiró Hub Local/Tauri-como-backend/SQLite (§1)
Impresión/hardware = app instalable (invoke in-process, ADR-0196), tres transportes: red/USB/Bluetooth Android; §2.7
Primary/Satellite = varios terminales del mismo hub; cobrar/imprimir solo el primario
Migración = gradual, POS-first, manteniendo la agrupación actual de módulos
SaaS (Django) = marketplace + billing + provisioning + proxy AI (no cambia)
hub = el runtime del tenant
```

> ERPlora no instala código backend arbitrario: instala **capacidades declarativas** (y
> WASM en sandbox) que Rust valida, registra y ejecuta. Como WordPress, pero más seguro,
> portable y eficiente.
