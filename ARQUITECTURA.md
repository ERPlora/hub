# hub — Arquitectura

> **Documento de diseño.** Define el Hub de
> ERPlora: **Vue 3 + Ionic + Rust/Axum + Tauri + módulos declarativos (module.json) +
> WASM + SDK**, con **SQLite en local** y **PostgreSQL/Aurora en cloud**.
>
> **hub ES el Hub de ERPlora.**
>
> Fuentes: diseño AI/RAG [PLAN-ASISTENTE-RAG.md](../docs/arquitectura/PLAN-ASISTENTE-RAG.md), mapa del monorepo
> [CLAUDE.md](../CLAUDE.md), repo de arquitectura seccionado [architecture/](../architecture/).
>
> **Estado:** propuesta + scaffolding inicial (`apps/web` Vue 3 + Ionic, primer módulo
> `modules/inventory` con WC Lit; CSP validada — §14). Última actualización: 2026-05-31
> (decisiones fijadas: impresoras **solo LAN**, **PK = UUID v4 `TEXT` en todo** el dato de negocio (ADR-0035, sin remapeo) — §2.5, §2.7, §14).

---

## 0. Propósito

Este documento describe **qué** queremos construir y **por qué**, reconciliando la
visión técnica (Rust/Ionic/Tauri/module.json) con la **realidad de producción** de
ERPlora (Cloud Portal en Django, marketplace, billing Stripe, provisioning AWS,
contrato S3 + SHA256, auth, asistente AI con RAG).

---

## 0bis. Decisiones finales del proyecto (2026-06-09) — **fuente de verdad**

> Resumen canónico de las decisiones tomadas por el humano y ya **implementadas + verificadas**.
> Consúltese esto primero para saber "cómo tiene que funcionar". Cada punto enlaza con la sección
> que lo detalla y con los ficheros/endpoints reales. `[✓ verificado]` = probado E2E en este repo.

1. **UI / shell unificado Cloud↔Hub** — mismo esqueleto Ionic canónico (`ion-app > ion-split-pane
   content-id="main" when="lg" > ion-menu (sidebar: brand+nav por secciones+tarjeta de usuario) +
   ion-router-outlet#main`). Componentes **Ionic (`ion-*`)**; OutfitKit (`ok-*`) **solo para huecos**
   (p. ej. `ok-data-table`). `apps/web` = Vue 3 + Ionic Vue + Vite. Rail colapsable por CSS. Dark por
   `.ion-palette-dark`. Detalle de UI en §3.1/§7.7. `[✓ verificado]`

2. **Camino de datos (backend de datos) — local-first, config-driven** — `apps/web` habla con el runtime vía
   `ErploraClient` (`@erplora/module-sdk`, `HttpWsTransport`) → **`erplora-server` (Axum)** en
   `VITE_RUNTIME_URL` (def `http://127.0.0.1:8787`) → **SQLite**; la misma config apunta luego al
   modo `cloud` (Aurora) sin tocar módulos (§7.6). `ModuleView` **inyecta el cliente** en el Web
   Component del módulo (`wc.client`) para que llame `client.query/command`. Endpoints del runtime:
   `POST /api/query`, `POST /api/command`, `GET /api/navigation`, `GET /api/modules`, `GET /ws`.
   `[✓ verificado: query/command ejecutan SQL real con scoping hub_id]`

3. **`hub_id` inyectado por despliegue (1 contenedor = 1 hub)** — el server lee `HUB_ID` del entorno
   y lo expone en **`GET /api/hub/context` → `{hub_id, user}`**; `apps/web` lo resuelve al arrancar
   (`bootHubContext`) y lo envía como **`X-Hub-Id`** en toda llamada. **No hay selector de hub.** Liga
   con la tenancy de §2.5. `[✓ verificado]`

4. **Login de usuario real contra Cloud** — `POST /api/v1/auth/login/` + `GET /api/v1/auth/me/`;
   tokens en `localStorage` (`erplora.access`/`erplora.refresh`); **interceptor refresh-en-401** con
   rotación de ambos tokens y un reintento (`POST /api/v1/auth/refresh/`); `X-Hub-Id` en todas. El
   **fallback demo** queda SOLO tras `VITE_DEMO=1` (producción falla duro). Contrato en §2.3. **Server-side (modelo decidido + implementado, §2.9):** la autoridad de identidad/permisos es **local**. Login por **PIN** o por **JWT de usuario cloud** (verificado RS256 → mapeado a un `hub_user` local) abre una **sesión server-side** (`HUB_AUTH=session`); cada petición lleva `X-Hub-Session` y el runtime resuelve `hub_user` → **permisos del rol** (`role_permissions` de los módulos activos). `hub_id` del despliegue. Verificado vivo: gate por rol real (employee `list`→200, `create`→403). Pendiente menor: argon2id para el PIN; gestión de usuarios/roles (UI admin); credencial de dispositivo de confianza (§14).

5. **Instalación de módulos por el marketplace (API real de Cloud)** — flujo: `GET
   /api/v1/marketplace/modules/{id}/versions/` (sha256) → `GET .../download/?version=` (zip binario) →
   **verificar SHA256** → unzip seguro (anti zip-slip) → `install_from_dir` → `POST .../mark_installed/`.
   En el Hub lo orquesta **`POST /api/modules/request-install {module_id, version}`** (cloud-client +
   source + installer) y emite WS `{"type":"module.installed","module_id"}` → el shell refresca el menú.
   Detalle/contrato en §2.2. **⚠️ Pendiente (Cloud):** `ModuleVersionSerializer` no expone `sha256` por
   `versions/` (solo el endpoint sync) → hoy, si falta, se instala SIN verificación de integridad;
   **arreglar en Cloud** (añadir `sha256` al serializer) para cumplir el contrato §2.2.

6. **El asistente AI es una CAPACIDAD CORE del Hub, no un módulo de marketplace** (ADR-0033,
   2026-06-13; supera la decisión 2026-06-09 de "módulo instalable"). Está **siempre presente** por
   defecto (✨ del topbar): el proxy está **horneado en el binario** (`crates/server/src/assistant.rs`)
   y el RAG en `apps/ai/knowledge/` — no hay `module.zip`, ni install, ni fila `Module` en el catálogo.
   Su billing es **propio** (`AssistantTier`/`AssistantUsage`, capa gratis con tope + upgrade), fuera de
   `ModulePurchase`/`is_module_entitled`. Su WC alcanza el LLM de Cloud por una **capacidad de host**:
   `POST /api/assistant/chat/stream` del runtime, que hace de **proxy SSE** hacia Cloud
   (`/api/v1/hub/device/assistant/chat/stream/`, reenvía `Authorization: Bearer` + `X-Hub-Id`)
   con **ensamblado de tools por permiso** (solo queries/commands con bloque `ai:` que el usuario puede
   ejecutar, §9.2). El Hub nunca habla con el LLM directo (§9.3); embeddings/RAG por el proxy de Cloud
   (§9.4/§9.6). La UI de chat de referencia quedó en `apps/web/src/parked/AssistantChat.vue`.

7. **Modelo de eventos del runtime = Outbox transaccional (entrega asíncrona at-least-once)** — ver
   §4 y §5.4 (actualizados). En corto: el command emisor **solo persiste** cada evento en `_event_outbox`
   **dentro de su misma transacción** (escritura atómica); los listeners NO corren inline — los entrega un
   **relay** en background (`erplora-server`, poll 1s) con backoff + dead-letter. **Idempotencia a nivel
   runtime** vía `_event_delivery (event_id, listener_command)` (exactly-once sin que los módulos sean
   idempotentes). La notificación al WS es inline pero **efímera** (solo UI en vivo). `[✓ verificado:
   command emite → 'pending' → relay → 'delivered']`

---

## 1. Visión: "un solo modelo mental" — dos productos

hub es **una sola app base** (misma UI, mismo modelo de módulos, mismo runtime). Se entrega en
**dos productos** con configuración fija — *no* en una matriz de ejes (framing retirado por
[ADR-0080](../architecture/00-overview/decision-log.md)):

> **Modelo decidido ([ADR-0050](../architecture/00-overview/decision-log.md), app unificada,
> aceptada 2026-06-17):** **un solo runtime Axum en AMBOS productos**, **mismo transporte de datos**
> = **HTTP (RPC) + WebSocket (solo eventos)**. Se **elimina** `invoke`/IPC **para datos**: en Local,
> el runtime Axum corre **embebido como servidor loopback** (`127.0.0.1:8787`) y la UI le habla por
> HTTP+WS igual que la PWA. La **única diferencia** entre productos es el `DatabaseAdapter` (SQLite
> Local ↔ Postgres/Aurora Hub PWA) y el almacenamiento de ficheros (disco local ↔ S3).
> *(pendiente doc↔código: el runtime/shell puede ir aún por el camino híbrido `invoke→HTTP`; la
> migración es columna core.)*

- **Local** (alias **Tauri**) — **1 dispositivo, multiusuario** (varios PINs/roles sobre el mismo
  equipo). **SQLite** embebido como autoridad, **offline**, **gratis**, empaquetado como
  **ejecutable Tauri**. El **puente** (Bridge) viaja **dentro del instalable**: el shell Tauri
  **arranca el bridge embebido** (servidor localhost, mismo canal que la PWA, reusando
  `crates/peripherals`).
  Transport de datos = **HTTP (RPC) + WebSocket (solo eventos)** contra el runtime Axum embebido
  (loopback `127.0.0.1:8787`).
- **Hub PWA** (alias **PWA**) — **multidispositivo, multiusuario**. **Aurora/Postgres** en un
  contenedor ECS por hub, **online-only**, **de pago**, servido como **PWA** en el navegador. El
  **puente** se instala **standalone** (`hub/apps/bridge`, WS `localhost:12321`) para el hardware.
  Transport de datos = **HTTP (RPC) + WebSocket (solo eventos)**.

```
Local (Tauri)   HTTP+WS → runtime Axum embebido (127.0.0.1:8787) → SQLite   1 dispositivo · offline · gratis · puente=bridge embebido
Hub PWA (PWA)   HTTP+WS → Rust/Axum (ECS)                         → Aurora   multidispositivo · online · de pago · puente=standalone
```

Reglas: **`single` ⟺ Local/Tauri** y **`cloud` ⟺ Hub PWA**. **No existe** el combo "shell Tauri
sobre backend cloud" (`cloud + tauri`, retirado en ADR-0080). El término **`dev`/`develop`** se
**reserva** para la app de **desarrollo local**, distinta del producto **Local**.

- **UI idéntica**: Vue 3 + Ionic como *shell*; cada módulo aporta su pantalla como Web
  Component (Lit, §3.1), cargado dinámicamente. El **hardware** lo aporta el **puente** (sidecar en
  Local, standalone en Hub PWA); la UI lo modela con un *capabilities descriptor* que el runtime
  expone y usa solo para mostrar/ocultar.
- **Transport de datos unificado (modelo decidido, [ADR-0050](../architecture/00-overview/decision-log.md))**:
  **los dos productos** usan **HTTP (RPC) + WebSocket (solo eventos)** contra el runtime Axum —
  embebido en loopback `127.0.0.1:8787` en Local, en ECS en Hub PWA. Se **eliminó** `invoke`/IPC
  para datos; el SDK ya no expone `IpcTransport`. La única diferencia es el `DatabaseAdapter` y los
  ficheros (§7.5, §7.6). *(pendiente doc↔código: el runtime/shell puede ir aún por `invoke→HTTP`;
  la migración es columna core.)*
- **DB intercambiable**: `DatabaseAdapter` con backends SQLite (Local) y PostgreSQL (Hub PWA) (§8).
- **Offline (modelo decidido, ADR-0040 — sin sync)**: **dos productos sin puente de datos**.
  Un dispositivo ⇒ **Local** (SQLite local = autoridad, gratis, 100% offline); ¿varios? ⇒ **Hub PWA**
  (ECS + Aurora por org, multidispositivo/web, **online-only**). **No hay sincronización local↔cloud**;
  el respaldo del Local es el módulo `backup` premium (export lógico cifrado a S3, no es sync). Se
  retiró el tier "Cloud DB local-first + sync" y el motor de sync (ver §2.8, OBSOLETO).
- **Rust es la autoridad**: valida permisos, tenant (`hub_id`), payload y ejecuta. La UI
  nunca toca la base de datos.

> El WebComponent no toca la BD. El WebComponent llama al SDK. El SDK llama a Rust.
> Rust valida permisos, payload y tenant, y ejecuta.

---

## 2. Reconciliación con la realidad de producción (sección crítica)

### 2.1 Hay DOS "Clouds" — no confundirlos

| Pieza | Qué es | Tecnología | ¿Cambia? |
|-------|--------|-----------|----------|
| **Cloud Portal** | `erplora.com`: landing, dashboard, **marketplace**, **billing Stripe**, **provisioning** (boto3 → ECS+Aurora), **proxy AI** | Django 6 + htmx | **NO** |
| **hub (modo cloud)** | El **runtime del tenant** en ECS. Sirve la app Ionic y ejecuta módulos | Rust + Axum | **SÍ** |
| **hub (modo local)** | El mismo runtime **embebido** en un shell Tauri (desktop/móvil), offline-first con SQLite. Es el producto **Local** (1 dispositivo, multiusuario por PINs/roles); el hardware local va por sidecar Bridge (§1, §2.7) | Rust + Tauri | Nuevo |

> El Cloud Portal **orquesta y cobra**; hub **ejecuta** el negocio del tenant. El
> "Axum cloud" de la visión es hub en modo cloud, **no** el Portal.

### 2.2 La instalación de módulos pasa por el marketplace del Cloud Portal

La visión describe un `/api/modules/install` contra un "registry" genérico. En ERPlora
hay un **marketplace con compra, entitlement y reparto de ingresos** (Stripe Connect).
hub respeta ese contrato:

1. El admin instala desde el marketplace.
2. hub pide al **Cloud Portal** la instalación → el Portal valida **compra/
   suscripción** y devuelve la **URL S3 firmada** + metadatos (versión, SHA256).
3. hub descarga el zip, **verifica SHA256**, descomprime, valida manifest, resuelve
   dependencias, aplica migraciones, registra capacidades, monta UI.
4. hub reporta estado al Portal (instalado/activo/error).

**Contrato S3 fijo** (producción, no se cambia): ruta inmutable `modules/{module_id}/v{version}.zip`,
integridad por `ModuleVersion.sha256`, README extraído a `s3://erplora-docs/...`.

### 2.3 Autenticación Hub ↔ Cloud (verificado en código)

> El token de máquina **no se eliminó: se cableó** (ADR-0003, 2026-06-10) como identidad de la
> propia máquina del hub para las llamadas **hub-scoped**. Conviven **tres credenciales**, cada
> una para su plano.

1. **Token de máquina del hub (`cloud_api_token`)** — identidad de la **propia máquina**. Se
   **genera al crear el hub** (`Hub.save()` → `secrets.token_hex(32)`), guardado **cifrado** en
   Cloud (`Hub.cloud_api_token`), validado con `compare_digest` (`IsHubMachine`). Viaja como
   header **`X-Hub-Token`** + `X-Hub-Id`. Es la credencial **por defecto de todo lo hub-scoped**:
   marketplace (browse/versions/download/mark_installed), entitlement, install, asistente,
   métricas — endpoints ampliados a `IsHubMember | IsHubMachine`. Necesario porque el día a día
   es sesión local/PIN (con usuarios solo-locales) y offline-first: casi nunca hay un JWT cloud
   fresco, pero el hub debe poder hablar con Cloud **a sí mismo**.
   - **Es un secreto del hub**: vive solo en el runtime Rust (`HubConfig.cloud_api_token`), **nunca
     en el navegador**. El web pega a rutas proxy del runtime (`/api/entitlement`,
     `/api/marketplace/catalog`) y el runtime firma hacia Cloud (`auth::hub_scoped_auth`).
   - **Entrega:** env `HUB_CLOUD_API_TOKEN` (ECS); `GET /api/v1/hub/device/enroll/`
     (owner/admin) para Tauri/local. Un hub pertenece siempre a una **organización**.
2. **JWT del usuario activo** — **solo** llamadas atribuidas a usuario: compra, checkout, billing,
   reviews. `Authorization: Bearer <access>` + `X-Hub-Id`; refresh en `POST /api/v1/auth/refresh/`
   (reintento en 401). Autoriza contra membresía de org (`IsHubMember`/`IsHubAdmin`). También es el
   **fallback** hub-scoped si el hub aún no está enrolado (dev/local).
3. **`X-Webhook-Secret`** (== `CLOUD_WEBHOOK_SECRET`) + `X-Hub-Id` para M2M de fondo
   (`IsInternalCaller`).

### 2.4 La clasificación del marketplace NO vive en el módulo

`sectors`, `business_types`, `functional_unit`, subcategorías, `pricing`, `is_published`…
se editan en el **vendor portal del Cloud** y **se preservan entre syncs**. El
`module.json` declara **solo lo técnico** (capacidades, permisos, dependencias, UI, AI
tools). Igual que la política actual con `module.py`.

### 2.5 Multi-tenancy y modelo de datos (corrección sobre la visión)

> ✅ **La visión acierta en el fondo (id por fila), pero el id correcto es `hub_id`, no
> `tenant_id`.** El modelo de producción —que **ya funciona así**— es:
> - **Una base de datos por organización** (Aurora por org).
> - **Varios hubs de la misma organización pueden COMPARTIR esa base de datos.**
> - Por eso **cada fila de negocio lleva `hub_id`** y el runtime **inyecta/scope `hub_id`
>   en cada query y command**. **No es opcional**: aísla los datos entre hubs que comparten BD.

- **Jerarquía**: organización → (uno o varios) hubs → **BD compartida de la organización**.
- **Confirmado en código**: la base `HubModel` lleva `hub_id` (+ soft-delete
  `is_deleted`/`deleted_at` + auditoría `created_by`/`updated_by`); un `HubQuery` añade
  `WHERE hub_id = :hub_id` (y excluye borrados) en **cada lectura automáticamente**; el
  `hub_id` se resuelve por dependencia (`settings.HUB_ID` en ECS single-hub → sesión →
  `HubConfig`). **El runtime de hub debe ofrecer el mismo automatismo**: el autor del
  módulo nunca filtra `hub_id` a mano.
- **Topología confirmada**: **un contenedor ECS por hub**, BD **por organización**
  (`Organization.database_name`, p. ej. `org_abc123…`) compartida por los hubs de la org.
- **Estado de módulos** (igual que hoy): `hub_module` (instalado/activo/... +
  `checksum_sha256` + `manifest` + `version`) y `hub_module_version` (catálogo del Portal).
- **Local (Tauri/SQLite)**: un solo hub por dispositivo; `hub_id` se mantiene por
  consistencia (un módulo corre igual en local y en cloud).
- ✅ **IDs de fila (decidido — ADR-0035, supera la PK numérica de ADR-0007/§2.5)**: los datos de
  negocio del hub (Aurora por-org **y** SQLite local) usan **PK = UUID v4 (`TEXT`) en TODO** — el
  runtime ya inyecta `:new_id` como UUID v4. **No** hay autoincremental numérico. El `hub_id` (UUID,
  viene del Cloud) sigue siendo el **discriminador de tenant** por fila. Como el UUID es
  **globalmente único**, **NO hay remapeo de PKs ni reescritura de FKs** al fusionar local↔cloud:
  los ids se conservan tal cual aunque varios hubs compartan la BD de la org. El append offline
  (pedidos creados sin red) **no colisiona** por construcción. *(Esto resuelve el punto abierto del
  motor de sync que §2.8/ADR-0031 tenían sobre el remapeo de PKs numéricas.)*

### 2.6 El sync Git del Cloud lee `module.json` (formato único)

**Decisión (2026-06-01): no hay formato legacy.** Todos los módulos son declarativos
(`module.json`). El sync Git del Cloud lee **solo `module.json`**:

- Se eliminó el discriminador `manifest_kind` (modelo, schema, parser TS/Rust) y todo el
  parser Python del Cloud (`parse_module_py`/`parse_ai_context_py`/`_extract_ast_value`).
  `parse_module_json` es el único parser; el sync ya no hace fallback a `module.py`.
- El contexto RAG (`ai_context`) ahora vive como campo de `module.json` (antes salía del
  `CONTEXT` de `ai_context.py`).
- **Inmutabilidad S3**: el publish debe usar la ruta versionada *create-only*
  (`ModuleVersion.create_from_zip`); reescribir un `v{ver}.zip` existente rompe el SHA256
  de clientes desplegados (el Cloud ya lo bloquea).

### 2.7 Periféricos / hardware local — el Bridge pasa a componente compartido

> ✅ **Decisión (actualizada): el `bridge/` NO se elimina.** Deja de ser un *producto separado de
> instalación obligatoria* y pasa a ser un **componente de hardware compartido**, enviado de dos
> formas con **un solo código**: (a) **sidecar** empotrado en el shell Tauri (install único,
> transparente) y (b) **instalador standalone opcional** para **Hub PWA**.

**Cómo obtiene hardware cada producto (§1):** modelo decidido
[ADR-0050](../architecture/00-overview/decision-log.md) — el bridge usa el **mismo canal localhost
(HTTP/WS) en los dos productos**. *(pendiente doc↔código: el shell puede ir aún por el camino
híbrido `invoke→HTTP`; la migración es columna core.)*

- **Local (Tauri)**: el shell Tauri **arranca el bridge embebido** (servidor localhost, mismo canal
  que la PWA, reusando `crates/peripherals`) — **no** por handlers `invoke`. **El shell Tauri *es* el
  bridge** — no hay proceso aparte ni segundo install.
- **Hub PWA**: el navegador **no puede** abrir TCP crudo (puerto 9100), USB ni
  Bluetooth clásico. Si ese usuario necesita hardware físico, instala el **Bridge standalone**
  (opcional); la PWA lo detecta por WebSocket en `localhost`. Si no lo necesita, imprime por
  PDF/email o impresora **ePOS-HTTP** (alcanzable por navegador). *Pega conocida: una PWA
  `https://` ↔ `ws://localhost` arrastra fricción de mixed-content/pairing — el bridge embebido del
  shell Tauri (loopback) no la tiene.*

**Transportes de impresora** — ✅ **Decidido: SOLO RED (TCP/IP ESC/POS, puerto 9100) — 100% LAN.**
USB y Bluetooth **se descartan**: exigen drivers + mantenimiento por dispositivo/SO que no compensa.
La red es además el caso más simple (un socket TCP, trivial en Rust) y el más estable; en **Local
(Tauri)** el runtime abre el socket al puerto 9100 directamente. El Bridge es **red-only por
construcción**: el crate `crates/peripherals` no incluye USB ni Bluetooth. Consecuencia para **Hub
PWA**: como el navegador no abre TCP crudo, **imprimir requiere el Bridge** (sidecar Tauri o
standalone) o una impresora **ePOS-HTTP**; no hay atajo WebUSB/WebBluetooth porque el hardware es
de red.

**Qué se conserva** (en el componente Bridge —sidecar/standalone— y/o el runtime Tauri, **no** en
un proceso de instalación obligatoria):
- **Descubrimiento de dispositivos en red + watchdog** (NECESARIO): detectar impresoras en la
  LAN (escaneo de subred / mDNS), seguir su estado (online/offline) y **re-localizarlas si su
  IP cambia por DHCP**. Sin esto, el usuario tendría que configurar IPs a mano y se rompería la
  impresión al renovar DHCP. → tarea async en el runtime/Tauri o en el Bridge.
- **Config de impresoras por terminal** (IP, rol recibo/cocina/barra), persistida.
- **Cola de impresión + reintentos** (impresora apagada / sin papel).
- **Enrutado por rol** (recibo vs cocina) cuando un terminal tiene varias configuradas.

**Lo que sí cambia vs el análisis anterior**: ya no hay un *proceso Bridge separado de
instalación obligatoria* — el hardware viaja **dentro** del shell Tauri (sidecar) y el Bridge
standalone queda **opcional**, solo para **Hub PWA**. El escáner por HID lo maneja el
SO/navegador como teclado.

> El escenario **Hub PWA + hardware físico** ya **no** queda fuera de alcance: se cubre
> con el **Bridge standalone opcional**. El POS en navegador es un producto de primera clase (§1),
> no una excepción.

#### 2.7.1 Estado de implementación (2026-06-09) — el Bridge ya es **Rust** (fuente de verdad)

> ✅ **Decisiones finales** (columna del humano: lenguaje, estructura, naming, empaquetado, CI).
> Esta sub-sección es lo que debe consultar cualquiera para saber cómo funciona el Bridge hoy.

- **Lenguaje y código único.** El Bridge se reescribió de Python/Kotlin/Ionic a **Rust**. La lógica
  vive una sola vez en el crate compartido **`hub/crates/peripherals`** (red-only, ESC/POS sobre
  TCP:9100), con módulos `protocol · discovery · escpos · drawer · queue · registry`. *Por qué Rust:*
  la decisión **red-only** elimina lo único que hacía fuertes a Python/Kotlin (drivers USB/serial/HID);
  con solo red, el Bridge es un socket TCP + un server WS, trivial en Rust, y se comparte con el shell
  Tauri.
- **Dos entregas, un crate:**
  - **Standalone** `hub/apps/bridge` — binario **Axum** que expone `GET /status` + `WS /ws` en
    `localhost:12321`. Es el de **Hub PWA**.
  - **Bridge embebido en Tauri** `hub/apps/tauri` — el shell **arranca el bridge embebido** (servidor
    localhost, mismo canal HTTP/WS que la PWA, reusando el mismo crate), **no** por handlers `invoke`
    (modelo decidido [ADR-0050](../architecture/00-overview/decision-log.md); `invoke` solo nativo).
    Es el de **Local (Tauri)**. *(pendiente doc↔código: el shell puede ir aún por `invoke→HTTP`; la
    migración es columna core.)*
- **Contrato WS estable.** Mismo JSON que consume el frontend (`bridge.js`/cliente del Hub). Se
  **dejan de exponer** USB/BT y el escáner (`barcode`/`toggle_keyboard`): el escáner HID lo maneja el
  SO/navegador como teclado. `printer_id` es siempre `network:{ip}:{port}`.
- **Android.** App **Kotlin fina** (foreground service) en `bridge/ERPlora-Bridge-android`, recortada
  a red-only. Un servicio de fondo en Android exige JVM; **comparte el protocolo JSON, no el código**.
- **Borrados (Fase 1, mínimo ruido):** `bridge/ERPlora-Bridge-desktop` (Python) y `bridge/ERPloraKiosk`
  (Ionic/Capacitor — redundante con PWA + Tauri). **Sin Python, sin Ionic/Capacitor.**
- **Plataformas distribuidas:** **Windows + Linux + Android**. **macOS = solo desarrollo local**
  (`cargo build`), no se distribuye (se quitó de la web `/bridge/` del Cloud).
- **Empaquetado (v1):** **binarios sueltos** (`erplora-bridge.exe`, `erplora-bridge-linux`). Instalador
  (.msi/.deb) + **bandeja del sistema** + **autostart** + **firma de código** quedan como pulido
  posterior.
- **CI / release (GitHub Actions):**
  - Desktop → `hub/.github/workflows/bridge-release.yml`: matrix Windows+Linux. Push a `main`/`develop`
    publica en `s3://erplora-downloads/bridge/latest/`; tag `v*` publica en `bridge/v{tag}/` y refresca
    `latest/`. Auth AWS por **OIDC** (rol `github-actions-deploy`). **Acción pendiente (infra):** ampliar
    el *trust policy* del rol a `repo:ERPlora/hub:*` (vive en `aws/`, Terraform) — hasta entonces el job
    `upload-s3` falla.
  - Android → su propio repo (`build.yml`): APK/AAB **firmado** → mismo bucket, con claves AWS estáticas.
- **Descarga desde el Cloud (siempre la última):** `GET /bridge/download/<platform>/`
  (`cloud/apps/public/bridge`) redirige a `bridge/latest/<fichero>` en S3. El CI rellena ese `latest/`.
- **Detección en el Hub (PWA):** `hub/apps/web/src/lib/bridge-client.ts` — `detectBridge()` sondea
  `localhost:12321/status`; `bridgeDownloadUrl()` apunta al Cloud. `SystemPage.vue` muestra estado real
  (Conectado/Desconectado + versión) y los botones de descarga (Windows/Linux/Android).
- **Mixed-content:** una PWA `https://` puede llamar a `http://localhost:12321` porque los navegadores
  tratan `localhost`/`127.0.0.1` como **origen seguro** (exento del bloqueo). **iOS/Safari queda fuera
  de alcance** (no se soporta el Bridge ahí; en iOS solo Tauri o impresora ePOS-HTTP).
- **Pendiente:** trust OIDC a `ERPlora/hub`; instalador+bandeja+autostart+firma; **transporte de
  hardware en el `module-sdk`** para que los módulos impriman/abran cajón desde la UI; multi-terminal
  **primario↔satélite** (§2.7b).

### 2.7b Hubs primario y satélites (multi-terminal de un mismo hub)

> Nuevo requisito. Un mismo punto de venta puede tener **varios terminales** (instancias de
> hub) trabajando a la vez. Se introduce un rol de instancia:

- Un hub se puede marcar como **primario (primary)** y los demás como **satélites (satellite)**.
- **Acciones privilegiadas restringidas al primario**: cobrar, imprimir tique, cerrar caja,
  y similares **solo las ejecuta el primario**. Los satélites operan el resto (tomar comandas,
  consultar, preparar venta) y **delegan** esas acciones en el primario.
- **Cómo encaja con el modelo de datos** (§2.5): todos comparten la BD de la organización con
  el mismo `hub_id`; el rol primary/satellite es una **propiedad de la instancia** (config),
  no un tenant distinto.
- **Implementación**: el rol se declara en config de instancia; el runtime **gatea las
  acciones privilegiadas** (un permiso/condición "requires_primary"). En cloud, los terminales
  son sesiones contra el mismo runtime; en local (varios Tauri en LAN), los satélites enrutan
  las acciones privilegiadas al primario.
- *Decisión abierta (§14)*: descubrimiento primario↔satélite en LAN, y qué pasa si el primario
  cae (¿se puede promover un satélite?).

### 2.8 Modelo offline — dos productos, SIN sync en fase 1 (ADR-0040)

> ⛔ **ACTUALIZADO — ADR-0040 (2026-06-13): NO hay sincronización en fase 1.** Se **retiró** el modelo
> "local-first + sync" (ADR-0031), el tier intermedio "Cloud DB" (ADR-0029) y **todo el motor de sync**
> (`crates/datasync`, relay, LWW, conflictos de stock, remapeo). Lo de abajo (tres tiers, sync, LWW)
> queda **histórico**; borrado físico en [`todo/F-remove-sync-clouddb-execution.md`](../todo/F-remove-sync-clouddb-execution.md).

> ✅ **Decisión (ADR-0040): dos productos sin puente.** **Local** (`single`+Tauri, SQLite local =
> autoridad, gratis, 100% offline, **un dispositivo**) y **Cloud** (`cloud`: ECS hub + Aurora por org,
> **online-only**, multi-dispositivo/web). Un dispositivo ⇒ Local; ¿necesitas varios? ⇒ Cloud (online).
> **No se sincroniza dato** entre ambos en fase 1. El respaldo del Local es el módulo **`backup`** premium
> (export lógico cifrado a S3 vía endpoint Cloud, [modules/backup.md](../architecture/modules/backup.md)) —
> copia unidireccional, **no** sync.

**Dos productos** (detalle en [overview.md](../architecture/hub/overview.md)):

| Producto | Datos | Multi-device | Offline |
| --- | --- | --- | --- |
| **Local — gratis** | SQLite local (autoridad) + `backup` a S3 | No | Sí (100%) |
| **Cloud — starter/standard** | ECS hub + Aurora por org | Sí | **Online-only** |

---

#### (histórico — retirado por ADR-0040) Modelo local-first + sync de ADR-0031

> Lo que sigue describía el motor de sync **ya retirado**. Se conserva como contexto por si el sync se
> reabre en el futuro (sería un ADR nuevo).

| Tier (histórico) | Datos | Multi-device | Offline |
| --- | --- | --- | --- |
| **Local — gratis** | SQLite local | No | Sí |
| **Cloud DB — 14,99 €/hub** | SQLite local **+ sync** a Aurora | Sí (sync rápido) | Sí |
| **Cloud completo — starter/standard** | ECS hub + Aurora | Sí | Nativo=local-first; PWA/iOS=online |

- **Topología = estrella, el nodo cloud (ECS/Aurora) es el master** (sin caja-master física → sin
  SPOF). La convergencia LAN-offline entre cajas de una tienda = fase posterior.
- **Conflictos = Last-Write-Wins por timestamp con autoridad del servidor** (`now` que el runtime
  ya inyecta, no el reloj del dispositivo → evita clock-skew). Limpio para **append** (pedidos: el
  caso del comercial sin cobertura). El **stock** es **hub-scoped** y **se sincroniza como cualquier
  otra tabla** en fase 1 (ADR-0035, rebaja el "server-autoritativo, no sincronizar" de ADR-0031);
  límite conocido = LWW ciego entre varios dispositivos offline del **mismo** hub (futuro), y el
  stock único multi-tienda = futuro (módulo `warehouse`, §13).
- **Qué SÍ necesita internet incluso en local** (degradan, no rompen el flujo de caja):
  instalación de módulos desde el marketplace, **AI** (embeddings + generación, §9.3) y el
  **primer login/configuración** (§2.9).
- **Durabilidad del dato local**: además del sync, backup **SQLite → S3** (como ya hace el hub).
- **PWA web (thin-client a ECS/Aurora) = solo iOS + acceso web, online-only**; `sqlite-wasm`/OPFS
  para offline en iOS = fase posterior.

> **El motor de sync es columna del humano** (sync local/cloud · offline son núcleo, ver
> [hub/CLAUDE.md](CLAUDE.md)). Aquí se documenta el **modelo decidido**, no el motor: su diseño e
> implementación están **pendientes**. Puntos abiertos (transporte por tier DB-to-DB vs replay,
> convergencia LAN) siguen en ADR-0031. La **identidad/PK** quedó fijada en **UUID-TEXT sin remapeo** y
> el **stock** acotado a **hub-scoped en fase 1** (multi-tienda/multi-almacén = futuro módulo
> `warehouse`) por **ADR-0035**; el campo `offline: queue|forbid` por comando está **scaffoldeado sin
> enforcement**. Diseño y casos difíciles en
> [`architecture/hub/sync-hard-cases.md`](../architecture/hub/sync-hard-cases.md). **Ojo:** el crate
> `sync` (§11) es el **cliente WS de eventos en vivo**, **no** este motor de datos — serán componentes
> distintos.

### 2.9 Login de usuario, dispositivos de confianza y tipos de usuario

> Esto es la **auth de usuario** (distinta de la auth máquina Hub↔Cloud, §2.3). Hereda y
> extiende el modelo actual del hub (PIN local + JWT de usuario).

Flujo:
1. **Primera configuración (requiere internet)**: el usuario se loguea con **email +
   password** contra el Cloud Portal → se establece la sesión y se **marca el dispositivo
   como de confianza**, provisionando la identidad en el hub local.
2. **Dispositivo de confianza → PIN**: una vez confiable, el acceso diario es por **PIN**
   local (rápido, como hoy).
3. **Offline (objetivo)**: en el futuro el PIN funciona **sin conectarse al cloud** (auth
   100% local en dispositivo de confianza).
4. **Refresh de tokens**: si hay internet, los tokens del usuario **se refrescan de forma
   oportunista** cuando el usuario hace alguna petición al cloud (no en un ciclo aparte).

**Dos tipos de usuario**:
- **Usuarios cloud**: gestionados en el Cloud Portal (miembros de la org); identidad/roles
  vienen del cloud. Pueden operar en varios hubs de la org.
- **Usuarios solo-locales**: existen **únicamente en el hub** (no en el cloud); útiles para
  personal de tienda que nunca necesita el portal.

**Implicaciones para hub**:
- El runtime mantiene una **tabla local de usuarios/roles/PIN** (equivalente al `LocalUser`
  actual) + el vínculo opcional con la identidad cloud.
- El **gate de permisos es local** (mismo gate para UI, API y AI tools, §9.2); la pertenencia
  a la org se valida contra cloud solo cuando hay red.
- "Dispositivo de confianza" = credencial de dispositivo persistida tras el primer login
  online (habilita PIN offline). *Decisión abierta: formato/rotación de esa credencial (§14).*

**Origen de la credencial de máquina por producto** (§1 — y la respuesta a
"¿el local necesita login?": **sí, una vez y online**, porque es lo que provisiona la identidad y
los entitlements para descargar módulos):
- **Local (Tauri)**: la app **es el hub**. El primer login online **auto-provisiona** su
  identidad de máquina (el `cloud_api_token` / `X-Hub-Token` de §2.3) en el dispositivo y la
  persiste como credencial de dispositivo (*decisión abierta §14*). Tras eso opera offline.
- **Hub PWA**: el hub remoto lo provisiona el Portal (boto3 → ECS+Aurora) y el despliegue
  **inyecta** el `cloud_api_token` en ECS (env `HUB_CLOUD_API_TOKEN`), nunca en el navegador. El
  navegador solo autentica al **usuario** (JWT + `X-Hub-Id`); el hardware local va por el Bridge
  standalone (§2.7). → el "origen de la credencial de máquina" depende del **producto**.

### 2.9b Tenencia: organización por usuario y un hub por dispositivo (decisión 2026-06-09)

> Aclara el vínculo **hub↔usuario↔organización** para la app gratuita, coherente con §2.5
> (BD por organización, compartida por varios hubs). **No** se añade `Hub.owner` FK: la tenencia
> sigue siendo por organización.

- **La organización es la frontera de datos** (§2.5): **una BD por organización** (hoy SQLite local;
  en el futuro una **Aurora en la nube vendida vía Cloud-proxy**, nunca expuesta directamente — el
  Cloud hace de proxy). **Varios hubs comparten la BD de su organización**, discriminados por `hub_id`
  por fila. Por eso el vínculo natural es hub→organización, no hub→usuario.
- **Org por defecto al crear la cuenta**: cuando un usuario **crea su cuenta** se le crea una
  **organización personal por defecto** (editable después: nombre, datos fiscales…). No se espera al
  primer arranque del hub. *(Hoy se crea de forma perezosa en el primer login desde Tauri —
  `_register_hub` en `cloud/apps/auth/users/api/serializers.py`; la decisión lo adelanta al signup —
  `apps/auth/users/services.py::create_user`, reutilizando
  `organizations.services.lifecycle.create_organization`.)*
- **Un hub por dispositivo**: cada instalación Tauri (desktop/Android) registra **su propio `hub_id`**
  bajo la organización del usuario, por **identidad de dispositivo**. El shell Tauri genera y persiste
  un id estable por instalación en `app_data_dir` y lo expone por el comando `device_context`
  (`apps/tauri/src-tauri/src/lib.rs`); el frontend lo lee (`apps/web/src/lib/device.ts`) y lo manda en
  el login como `X-Client-Type` + **`X-Device-Id`**. El Cloud hace get-or-create por `(org, device_id)`
  (`_register_hub`), con fallback legacy por `(org, deployment_mode)` para clientes sin device-id. Dos
  máquinas del mismo usuario = **dos hubs** que **comparten la BD de la org** → habilita el
  multi-terminal primary/satélite (§2.7b) de forma natural.
- **Requisito único para usar el hub local = tener cuenta** (la app no se compra, §2.10).

### 2.10 App Tauri **gratuita** y entitlement por tiers de módulo (decisión 2026-06-09)

> Sustituye la idea de una "licencia standalone de pago". La app de escritorio/Android **no se vende**:
> es la **versión ligera** (gratis, publicitaria) para captar clientes; el upsell es **subir a cloud**
> (donde está el multidevice). Lo que abre funcionalidad es un **entitlement por tiers de módulo**.

**Tiers de módulo** (`Module.tier` en el Cloud, `cloud/apps/public/modules/models.py`; se edita en el
vendor portal como el resto de la clasificación, §2.4):

| Tier | Qué es | Local (Tauri gratis) | Cloud (ECS/Aurora) |
|------|--------|----------------------|--------------------|
| `basic` | Núcleo POS + **compliance** (operar y cumplir normativa vigente) | **Gratis** | **Gratis** |
| `standard` | Funcionalidad extra que **sí corre en local** | **Suscripción**, comprada desde la propia app (Fase 2) | **Gratis** (incluida en el plan cloud) |
| `premium` | Módulos con **API a cloud** que nos cuestan dinero (asistente, WhatsApp…) | **No disponible** (solo-cloud) | **De pago** (compra/suscripción) |

**Dos ejes independientes** (clave, no confundir):
- **Disponibilidad** = `tier` + `deployment_mode`: `premium` es **solo-cloud**; `basic`/`standard`
  corren en ambos.
- **Pago** = `module_type` (`free`/`one_time`/`subscription`): los `free` no requieren compra; los de
  pago sí — con una **excepción de bundle**: `standard` va **incluido gratis en hubs cloud**.
- **Fuente única de verdad**: `is_module_entitled(hub, module)` en
  `cloud/apps/public/modules/entitlement.py`, reutilizada por el permiso de descarga
  (`CanDownloadModule`) y por el listado del marketplace (los hubs locales no ven `premium`).

**Gate de arranque (la app pregunta "¿qué puedo montar?")**:
1. Tras el login del usuario, el hub pide `GET /api/v1/hub/device/entitlement/` (user-JWT + `X-Hub-Id`,
   permiso `IsHubMember`). El Cloud devuelve un **token firmado RS256** con el **mismo par de claves que
   el JWT de usuario** (`settings.PRIVATE_KEY/PUBLIC_KEY`; pública en `/api/v1/auth/public-key/`), con la
   lista de módulos permitidos + `exp` (24 h) y `grace_until` (gracia offline, 7 d).
2. El hub **cachea** token + clave pública y los **verifica OFFLINE**
   (`crates/cloud-client/src/entitlement.rs::verify_entitlement`), de modo que opera sin red dentro de la
   ventana de gracia (coherente con el offline-first, §2.8).
3. Sin token válido ni cacheado → **pantalla de login/activación** (`apps/web/src/views/ActivationPage.vue`):
   el shell arranca pero **no monta el runtime de negocio**. Con token válido → monta **solo** los
   módulos del entitlement. El cableado del frontend vive en `apps/web/src/lib/entitlement.ts`
   (resuelve en boot/login: comando Tauri si lo hay, si no el endpoint Cloud), `lib/module-loader.ts`
   (filtra los instalados a los entitled) y el guard del `router`.
4. Glue Tauri: `apps/tauri/src-tauri` (comando `validate_entitlement`). *(El crate aún no está en el
   workspace Cargo: requiere toolchain Tauri v2 + el `dist` de `apps/web`.)*

**Estado**: Fase 1 implementada y verificada (campo `tier` + migración + backfill, servicio/endpoint de
entitlement firmado, gating por `deployment_mode`, `entitlement()` + verificación offline en
`cloud-client`, scaffold de `apps/tauri`, y **gate cableado en el frontend** `apps/web` — boot/login →
filtro de módulos + pantalla de activación; typecheck + build verdes).

**Fase 2 (diferida — decisión explícita: no complicar la Fase 1)**:
- **Compra in-app de módulos `standard`** desde la app Tauri (deep-link al checkout Stripe del Cloud)
  ejecutándose en local; al volver, re-`entitlement()`.
- **Eje `requires_cloud`** como flag separado de `tier` (hoy se deriva: `premium ⇒ solo-cloud`).
- **Clasificación por "tipo de hub"**: registrar el tipo de hub y casar tipo↔módulos de pago, si
  compensa frente a la simplicidad de `tier + deployment_mode`.

---

## 3. Stack y decisiones de tecnología

| Capa | Elección | Motivo |
|------|----------|--------|
| Shell frontend | **Vue 3 + Ionic (`@ionic/vue` 8.8) + vue-router + Vite + TS + Tailwind v4 + Iconify (`unplugin-icons`, build-inline)** | Componentes Ionic reales; **sin Capacitor** (runtime nativo = Tauri). Tematizado por `--ion-*` (§3.1, §15) |
| UI de módulos | **Web Components** (Lit recomendado, §3.1) | WC estándar, cargables dinámicamente; default 2026 |
| Runtime/backend | **Rust + Axum** | Runtime ligero/portátil, una sola autoridad, sin Node en prod local |
| Desktop/móvil | **Tauri v2** | Empaqueta la misma UI; binario pequeño. **Modelo decidido ([ADR-0050](../architecture/00-overview/decision-log.md)):** el shell **arranca el runtime Axum embebido** (loopback `127.0.0.1:8787`) y el **bridge embebido**; la UI le habla por **HTTP+WS** (no por `invoke` para datos ni hardware). `invoke` queda **solo** para lo nativo sin equivalente HTTP (keychain, device_id, ciclo de vida, §2.7). *(pendiente doc↔código: puede ir aún por `invoke→HTTP`; migración = core.)* |
| DB local | **SQLite** | Offline-first, embebible en Tauri |
| DB cloud | **PostgreSQL / Aurora** | Igual que hoy; soporta `pgvector` (clave para RAG, §9) |
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
3. Verificar firma + SHA256
4. Descomprimir en el store de módulos
5. Leer y validar module.json
6. Comprobar depends_on (orden topológico)
7. Aplicar migrations (por dialecto: sqlite/postgres)
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
(SQLite + Postgres, las crea el runtime, no un módulo): `_event_outbox` y `_event_delivery`.

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
├─ migrations/{sqlite,postgres}/001_init.sql
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
  "migrations": { "sqlite": ["migrations/sqlite/001_init.sql"],
                  "postgres": ["migrations/postgres/001_init.sql"] },
  "queries": {
    "inventory.products.list": {
      "permission": "inventory.products.read",
      "sql": "queries/products_list.sql", "schema": "schemas/products_list.json"
    }
  },
  "commands": {
    "inventory.stock.decrease": {
      "permission": "inventory.stock.update", "transaction": true,
      "sql": ["commands/stock_decrease.sql"],          // declarativo …
      // "handler": { "type": "wasm", "file": "logic/stock_rules.wasm", "function": "decrease_stock" },
      "emit": ["inventory.stock.updated"]
    }
  },
  "events": { "listen": { "pos.sale.completed": { "command": "inventory.stock.decrease" } } },
  "ai_tools": {
    "inventory_adjust_stock": {
      "permission": "inventory.stock.update", "description": "Adjust stock for a product",
      "command": "inventory.stock.decrease", "schema": "schemas/stock_decrease.json"
    }
  },
  "scheduled_tasks": []
}
```

**Equivalencias con `module.py`**: `MODULE_ID`→`id`, `MODULE_VERSION`→`version`,
`DEPENDENCIES`→`depends_on`, `PERMISSIONS`→`permissions`, `ROLE_PERMISSIONS`→`role_permissions`,
`NAVIGATION`/`MENU`→`navigation`, `SCHEDULED_TASKS`→`scheduled_tasks`. Lo nuevo:
`queries`/`commands`/`events`/`ai_tools` declarativos (hoy son código Python).

### 5.3 Niveles de potencia (paga complejidad solo cuando la necesitas)

- **Tier 0 — Declarativo (sin código):** tablas, queries de lista/get, CRUD de una fila,
  permisos/roles, menú, `ai_tools`, scheduled tasks. ~30% de módulos. Máxima seguridad, cero compilación.
- **Tier 1 — Declarativo + capacidades del host:** `render.pdf`/`render.xlsx` (plantilla),
  forma *for-each* para batch sencillo, `http.fetch` **mediado** (§5.5). Cubre mucho sin WASM.
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

### 5.5 Capacidades del host (Tier 1) — incl. `http.fetch` mediado (Opción A, decidida)

El host (Rust) expone un conjunto **cerrado** de capacidades que un módulo Tier 0/1 puede
usar de forma declarativa, sin WASM y sin acceso crudo a recursos:

- **`render.pdf` / `render.xlsx`**: el módulo declara una plantilla; el host genera el
  documento (sustituye a `fpdf2`/`openpyxl`/`weasyprint`).
- **`http.fetch` mediado (red saliente, Opción A — decidida en §6):**
  1. El módulo declara en `module.json` una **allowlist** de dominios + los secretos que
     necesita (por nombre lógico, **nunca** el valor):
     ```jsonc
     "network": { "allow": ["api.stripe.com", "graph.facebook.com"], "secrets": ["stripe_api_key"] }
     ```
  2. El usuario/admin **concede** el permiso al instalar.
  3. En runtime el módulo llama `host.http_fetch({ url, method, headers, body, secret_ref })`.
     **El host hace la llamada**: valida el dominio contra la allowlist, **inyecta la
     credencial** desde el almacén cifrado (`secret_ref` → valor; el módulo **nunca** ve el
     secreto), aplica timeouts/rate-limit y **audita** (módulo, destino, resultado).
  4. El secreto vive cifrado (Fernet/KMS) y solo lo desreferencia el host.

Así un **tercero puede publicar integraciones** (pago, envío, mensajería) sin abrir red
arbitraria ni exponer secretos.

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
| **PDF / Excel** | ❌ | Capacidad host `render.pdf`/`render.xlsx` (Tier 1) |
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
// Modelo decidido (ADR-0050): el SDK ya NO tiene IpcTransport (eliminado); AMBOS productos
// usan HTTP+WS contra el runtime Axum — embebido en loopback 127.0.0.1:8787 (Local) o ECS (PWA).
// HttpWsTransport → HTTP POST query/command + WebSocket solo para eventos          (Local y Hub PWA)
// (WsTransport — todo por un WS — queda como alternativa, no por defecto; §7.5)
// (pendiente doc↔código: el runtime/shell puede ir aún por invoke→HTTP; la migración es columna core.)
```

> `hasPermission` en JS es **solo** para mostrar/ocultar UI. La seguridad real está siempre
> en Rust, que revalida en cada query/command.

### 7.2 `@erplora/module-types` (tipos + JSON Schema)

Tipos TS del manifest + JSON Schema de `module.json`, **generados desde
`schemas/module.schema.json`** (fuente única del contrato, compartida por Rust/TS/CLI).

### 7.3 `crates/guest-sdk` — SDK *guest* para WASM (Rust)

Crate que usan los autores de lógica WASM: macro `#[command]`/`#[query]`, serialización
JSON in/out (ABI Extism), y **host functions** (ejecutar un query/command permitido, emitir
evento, `render.pdf`, `http.fetch` en allowlist). El guest devuelve *intenciones*; nunca
toca la BD. Sin esto, escribir WASM es inviable.

> **Guest = el código que corre DENTRO del sandbox** (el "invitado"), frente al **host**
> (Rust, el "anfitrión"). Extism permite escribir el guest en **Rust/JS/Go/Python**:
> - **Rust-only (recomendado para empezar)**: el autor escribe la lógica en Rust → WASM más
>   pequeño y rápido, un solo toolchain. Contra: excluye a quien no sabe Rust.
> - **Multi-lenguaje**: permite JS/Go/Python → baja la barrera de autoría (más gente puede
>   publicar módulos con lógica), a cambio de WASM más grande y más toolchains que soportar.
> Por defecto **Rust-first**, con la puerta abierta a más lenguajes sin rediseñar el host
> (decisión en §14).

### 7.4 CLI `erplora module …`

```
erplora module create <id>      # scaffolding (module.json + carpetas + ejemplo WC/WASM)
erplora module build <id>       # compila WC (Lit) + WASM, valida SQL/schema
erplora module validate <id>    # valida manifest contra JSON Schema + linters
erplora module pack <id>        # genera manifest.lock + module.zip
erplora module sign <id>        # firma + SHA256
erplora module publish <id>     # sube al marketplace del Cloud Portal (§2.2)
```

### 7.5 Transporte y comunicación — ¿todo por WebSocket?

**No.** El transporte de datos es **HTTP para RPC + WebSocket solo para eventos**, no "todo por un
WS". WS-only obligaría a reimplementar el framing RPC (correlación de IDs, timeouts, replay) que
HTTP da gratis.

**Modelo decidido ([ADR-0050](../architecture/00-overview/decision-log.md)):** **AMBOS productos**
usan el **mismo transporte de datos** (HTTP+WS) contra el runtime Axum; en **Local** ese runtime
corre **embebido como servidor loopback** (`127.0.0.1:8787`), en **Hub PWA** en ECS. Se **eliminó**
`invoke`/IPC para datos. La diferencia entre productos es **solo** el `DatabaseAdapter` (SQLite ↔
Aurora) y los ficheros (disco ↔ S3). *(pendiente doc↔código: el runtime/shell puede ir aún por el
camino híbrido `invoke→HTTP`; la migración es columna core.)*

| Qué | Local — runtime Axum embebido (loopback) | Hub PWA — Axum (ECS) |
|-----|------------------------|------------------------|
| `query` / `command` (RPC) | **HTTP POST** (`/api/query`, `/api/command`) | **HTTP POST** (`/api/query`, `/api/command`) |
| Eventos / push | **WebSocket** (`/ws`, solo push) | **WebSocket** (`/ws`, solo push) |
| App Ionic + assets | filesystem | **HTTP/CDN** |
| Bundles UI de módulos | filesystem | **HTTP/CDN** |
| Descarga `module.zip` | **HTTP** (S3) | **HTTP** (S3) |
| Exports PDF/Excel | **HTTP** | **HTTP** |
| Cloud Portal (marketplace, billing, embeddings/LLM) | **HTTP REST** (user-JWT + `X-Hub-Id`) | **HTTP REST** |

> **Canal de hardware (modelo decidido, [ADR-0050](../architecture/00-overview/decision-log.md)):**
> el bridge usa el **mismo canal localhost (HTTP/WS) en los dos productos**. En **Local (Tauri)** el
> shell **arranca el bridge embebido** (servidor localhost, mismo canal que la PWA, reusando
> `crates/peripherals`) — **NO** por handlers `invoke`. En **Hub PWA** ese canal lo aporta el
> **Bridge standalone opcional** por `ws://localhost` (§2.7). `invoke` queda **solo** para lo nativo
> sin equivalente HTTP (keychain, device_id, ciclo de vida), no para hardware.

**Escala**: un hub tiene **1–5 usuarios (máx ~30)**, con tolerancia a crecer. A esa escala
el rendimiento **no decide**; deciden resiliencia y simplicidad:

- **Degradación elegante (clave para un TPV)**: si el WebSocket cae, las **ventas siguen
  por HTTP**; solo se pierden las actualizaciones en vivo. Con WS-only, si el socket falla, **todo** falla.
- **Más simple**: HTTP no necesita framing RPC sobre WS. **Tooling estándar** (reintentos,
  idempotencia, `curl`, proxies/CDN). WebSocket queda **solo para push**.
- **Mismo transporte en Local y Hub PWA** (modelo decidido, ADR-0050): HTTP (RPC) + WebSocket
  (solo push) contra el runtime Axum, embebido en loopback en Local. *(pendiente doc↔código: el
  runtime/shell puede ir aún por `invoke→HTTP`; la migración es columna core.)*

> **Decisión: ambos productos = HTTP (RPC) + WebSocket (solo eventos).** WS-only queda como
> alternativa (todo por un solo canal), pero no por defecto.

### 7.6 Garantía: el mismo módulo corre en ambos productos sin trabajo adicional

> **Modelo decidido ([ADR-0050](../architecture/00-overview/decision-log.md)):** ambos productos
> usan **HTTP+WS** contra el runtime Axum (embebido en loopback en Local). El SDK ya **no** tiene
> `IpcTransport`. *(pendiente doc↔código: el runtime/shell puede ir aún por `invoke→HTTP`; la
> migración es columna core.)*

1. **Envelope único agnóstico al cable** (`schemas/envelope.schema.json`):
   `Request{ id, kind, name, params }`, `Response{ id, ok, data|error }`, `Event{ name, payload }`.
2. **Core del runtime agnóstico al transporte**: `handle(Request) -> Response` + stream
   `events`. No sabe si lo invocó HTTP o WS.
3. **Una sola interfaz** `ErploraTransport`: el impl por defecto es `HttpWsTransport` (HTTP RPC +
   WS push), usado por **los dos** productos; `WsTransport` (todo por un WS) queda como alternativa.
   `IpcTransport` se **eliminó** (ADR-0050).
4. **Flag de arranque** `RUNTIME_TRANSPORT=http+ws|ws` (detalle de impl del transporte, no de
   negocio). Ningún campo de `module.json`, ni código de módulo, ni lógica de permisos depende del
   transporte.
5. **El mismo frontend se empaqueta como Tauri (Local) o como PWA (Hub PWA)**: el shell es una
   dimensión de *build/boot*. **Local (Tauri)** arranca el runtime Axum embebido (loopback
   `127.0.0.1:8787`) y el bridge embebido; **Hub PWA** apunta al Axum en ECS. `invoke` queda **solo**
   para lo nativo (keychain, device_id, ciclo de vida, §2.7), no para datos ni hardware.

→ El mismo módulo y la misma UI corren en **los dos productos** (Local y Hub PWA)
**cambiando solo los adaptadores en el boot**. Cero trabajo adicional.

### 7.7 Reactividad de la UI (decidido: eventos WS → el WC re-consulta)

> ✅ **Decisión.** El Web Component mantiene su **estado en el cliente**. Cuando llega un
> **evento** relevante (p. ej. `inventory.stock.updated`) por **WebSocket** (mismo canal en ambos
> productos, modelo decidido [ADR-0050](../architecture/00-overview/decision-log.md); en Local el WS
> va contra el runtime Axum embebido en loopback), el WC **vuelve a hacer la query** afectada y se
> repinta.

- Es el modelo natural del SDK (§7.1): `erplora.on(evento, …)` → `erplora.query(…)` → render.
- **No hay render en servidor**: la UI es cliente (Lit) y el servidor solo emite eventos
  y responde queries/commands.
- **Granularidad**: los eventos llevan el mínimo (`{ name, payload }`); el WC decide qué
  re-consultar. Evita empujar estado completo por el socket.
- **Coalescing**: el cliente puede agrupar refrescos (debounce) ante ráfagas de eventos.

---

## 8. Base de datos, adapters y migraciones

```
trait DatabaseAdapter  (async, #[async_trait])
├─ SqliteAdapter   → sqlx::SqlitePool   (local / Tauri)
└─ PgAdapter       → sqlx::PgPool       (cloud / Aurora)
```

### 8.1 Motor único: SQLx (decisión 2026-06-02)

**SQLx es el único motor de base de datos** para ambos backends — se eliminan `rusqlite`
y `rust-postgres`. Razón: el producto que se vende es **cloud + Aurora**, donde lo que
importa es **pool de conexiones + async + TLS**, y SQLx lo trae probado para Postgres y
SQLite con la **misma API** (`sqlx::query(...)`). Un solo crate, un solo modelo mental;
el día que se añada sync/replicación/workers se sigue con la misma librería.

Matices que esta decisión **NO** cambia (siguen siendo trabajo propio, ortogonal al motor):

- **El SQL es dinámico** (viene de `module.json` / `queries/*.sql` en runtime), así que
  `query_as::<T>` **no aplica** — no hay struct en compile-time. Se usa `sqlx::query(sql)`
  y se convierte `Row → serde_json::Value` a mano (decode dirigido por tipo de columna),
  igual que antes. `query_as` sólo para tablas internas con struct fijo (sessions, hub_module).
- **Los módulos escriben siempre params nombrados `:id`** (nunca `$1` ni `?1`, para no
  acoplar el módulo a un dialecto). Un **translator** reescribe `:id` → `$1` (Postgres) o
  `?1` (SQLite) según el dialecto del adapter activo. SQLx **no** abstrae el placeholder,
  así que el translator se queda.
- **Portabilidad SQL SQLite↔Postgres**: SQLx ejecuta el SQL que se le da, no traduce
  dialectos → **migrations por dialecto** (decisión abierta §14, sin cambios).
- **Decode `Row → JSON` dirigido por tipo de columna** (riesgo abierto, marcado como TODO en
  `crates/db`): hoy se cubre lo escalar (int/float/bool/text). **NUMERIC (dinero)**,
  `TIMESTAMPTZ`, `UUID` y `JSONB` caen a string/`null` → para el ERP fiscal hay que activar
  las features SQLx (`bigdecimal`/`rust_decimal`, `chrono`/`time`, `uuid`) y decodificarlos
  explícitamente. Validar contra Aurora real en Fase 0. Relacionado: el bind de `NULL` en
  Postgres se tipa hoy como TEXT y puede chocar con columnas de otro tipo — verificar igual.

> SQLx sobre SQLite no es async real (SQLite es síncrono; SQLx lo corre en un threadpool).
> En local da igual: 1 POS, 1 usuario, `SqlitePool` con `max_connections(1)`.

### 8.2 Tipos de retorno envueltos (no `Vec<Json>` pelado)

El trait **no** devuelve `Vec<Json>`/`Json` directos, sino envoltorios para poder crecer
(`execution_time`, `warnings`, paginación) sin romper la API:

```rust
pub struct QueryResult   { pub rows: Vec<Json>, pub warnings: Vec<String> }
pub struct CommandResult { pub affected: u64, pub returning: Option<Vec<Json>>, pub warnings: Vec<String> }
```

Estos envoltorios son lo que viaja dentro de `data` del `envelope.schema.json` (§7.6) —
single-source-of-truth compartido por Rust, el SDK TS y el CLI. Lo que se añada se añade
en un sitio.

### 8.3 Configuración por entorno (como el transporte §7.6)

El adapter se elige y configura **en el boot** desde variables de entorno/config:

- **Cloud (ECS)**: cada hub recibe su **DSN de Postgres en `HUB_DATABASE_URL`** (inyectada
  por ECS al crear la task). Los hubs de la **misma organización comparten el mismo DSN**
  (misma Aurora de la org); `hub_id` desambigua por fila (§2.5).
- **Local (Tauri)**: recibe el **path del fichero SQLite** (p. ej. `HUB_SQLITE_PATH`).
- Misma interfaz `DatabaseAdapter`; **solo cambia la config del entorno**.

**Sizing del `PgPool` (`max_connections`, etc.) — decisión abierta.** Depende del plan
contratado y del modelo "una Aurora compartida por org / un contenedor ECS por hub": el
límite real es agregado (`Σ pools de los hubs de la org ≤ conexiones de su Aurora`). El
Cloud Portal ya gestionaba esto con la app FastAPI; **a revisar cómo se traslada a
hub** (probablemente env inyectada por el provisioning + clamp/fail-fast al boot,
y `acquire_timeout`/`max_lifetime`/`idle_timeout` fijos por ser operacionales, no de plan).
Pendiente, no bloquea la Fase 0/1.

- Estado de módulos + integridad (SHA256) + versión instalada por hub.
- Riesgo (decisión abierta, §14): SQL compatible SQLite↔Postgres es trabajo; valorar capa
  de query mínima o dialecto canónico.

---

## 9. AI, RAG y base vectorial

Hereda el diseño actual (ya sofisticado) y lo adapta a Rust + SQLite/Postgres. Cambio clave:
**la base vectorial solo existe en cloud (pgvector); en local hay que degradar.**

### 9.1 Tres caminos de información (no confundir)

1. **Datos vivos** ("¿cuánto stock?") → tools `query`/`command` → SQL **local**. Sin RAG.
   Nunca se embeben datos del tenant (cambian, son caros, son PII).
2. **Conocimiento** ("¿cómo anulo una factura?") → tool `search_docs` → **búsqueda
   vectorial** sobre la documentación de los módulos instalados **a su versión**.
3. **Capacidades** → texto en el prompt (módulos + `ai_tools`). No es RAG.

### 9.2 AI tools por módulo (en `module.json`) — bloque `ai` inline (decisión 2026-06-04)

**Un AI tool ES una `query`/`command` que ya existe en el manifest** (declarativo). No hay una
sección de tools aparte: para exponer una operación al asistente, se le añade un bloque `ai`
**inline** con solo su descripción legible:

```json
"inventory.products.list": {
  "permission": "inventory.view_product",
  "sql": "queries/products_list.sql",
  "ai": { "description": "Lista productos y su stock actual" }
}
```

- **El `permission` (y el `schema` de input y el `sql`) se HEREDAN de la operación** — no se
  redeclaran en `ai`. Esto cierra por construcción el invariante del gate: el tool no puede
  tener un permiso distinto al de la operación, porque **es** la misma operación.
- Una operación **sin** bloque `ai` no se expone a la IA (sigue disponible para la UI). Así se
  cura, por operación, qué es invocable por IA. Las **internas** (`_`-prefijadas) nunca se exponen.
- La "lista de tools" no se declara: **se deriva** (todo query/command con bloque `ai`).
- **Idioma: `ai.description` (y `agent.description`) van SIEMPRE en INGLÉS** — son texto canónico
  orientado al LLM, que el usuario **nunca ve**. No se traducen ni se almacenan en N idiomas. La
  app es multilingüe en **otra capa**: la IA **responde en el idioma del usuario** porque la
  orquestación inyecta el **locale del usuario en el system prompt**, no porque las descripciones
  estén traducidas. Una sola descripción en inglés por tool.

**La IA no ejecuta SQL ni lo ve.** El LLM recibe (del hub, que parsea el manifest de forma
determinista) tool-specs = `nombre + ai.description + schema de args`. Decide *qué tool llamar
con qué args* y devuelve un tool-call. **El runtime** busca la operación, valida `permission` +
`hub_id` + payload, carga el `sql` y lo ejecuta vía `DatabaseAdapter` — **idéntico camino que
la UI**. La IA es solo otro llamante del mismo dispatcher (`execute_query`/`execute_command`).
Sin text-to-SQL (§9.3). Acciones destructivas → confirmación/draft.

> **Capacidades declarativas ⇒ sin reentreno.** Como las tools se leen en vivo del manifest
> (no se embeben), cargar/cambiar un módulo NO requiere reindexar nada: el `module.json` está
> siempre al día por definición. RAG (§9.4) es solo para el **conocimiento** (docs), no para
> las capacidades. (Routing multi-módulo a escala → por **búsqueda vectorial**, ver §9.2b.)

> Histórico: la sección `ai_tools` (con `permission` redeclarado) quedó obsoleta y se eliminó
> del schema el 2026-06-04 — ningún módulo la usaba. Reemplazada por el bloque `ai` inline.

### 9.2b Routing de módulos por vectores (nivel 1) — decisión 2026-06-05

**Problema:** con muchos módulos instalados, mandar TODOS los tools (`ai`) al LLM en cada
petición no escala (prompt enorme, caro). **Solución:** el hub elige dinámicamente **qué
módulo(s) cargar** según el contexto de la petición — uno o varios, no todos.

**Mecanismo = búsqueda vectorial** (reusa la infra de §9.4/§9.5, no es infra nueva):

1. **Al instalar un módulo** (lifecycle, §9.6): se calcula el *embedding* de su
   `agent.description` (vía el proxy Cloud, §9.3) y se **registra** en el índice vectorial.
2. **En cada petición**: se embebe lo que pide el usuario → se **busca** en el índice → salen
   los **1–N módulos relevantes** → solo de esos se cargan los tools `ai`.

El **tool-assembly** queda en dos fases:
- **(router)** embeber petición → buscar en el índice → top módulos.
- **(assembler)** de esos módulos: filtrar tools por **permiso del usuario** → empaquetar en el
  formato function-calling del Cloud (`{type:function, function:{name, description, parameters}}`,
  ver contrato §9.3) → enviar.

**Dos usos del vector — NO confundir** (misma infraestructura, distinto contenido):

| Uso | Qué se embebe | Para qué |
|-----|---------------|----------|
| **Routing** (§9.2b) | descripciones de **módulos/tools** (`agent.description`) | elegir **qué módulo** cargar |
| **RAG** (§9.4, aún sin diseñar) | la **documentación** de los módulos (`ai_context`) | responder preguntas de **conocimiento** |

Routing decide *qué herramientas*; RAG responde *cómo se hace algo*.

**Coste honesto:** embeber necesita el Cloud (§9.3), así que el routing añade una llamada de
embedding **por petición** antes de la principal. Con **pocos** módulos instalados es más barato
mandar las `agent.description` como texto y que el LLM elija; el **vector gana a escala** (muchos
módulos). El `keywords` opcional de `agent` permite un pre-filtro léxico barato antes del vector.

> **Pendiente de construir** (lo escribe el humano; la IA solo guía): el crate/módulo de
> tool-assembly (router + assembler), el registro de embeddings de módulos al instalar, y la
> búsqueda en query-time. La infra vectorial (`erplora-vector` local / pgvector cloud) ya existe.

### 9.3 El hub NUNCA habla con LLMs directamente

**Embeddings** (ingesta + pregunta) y **generación** van por el **proxy del Cloud Portal**,
medido en `AssistantUsage` (`POST /api/v1/hub/device/assistant/embeddings/` + orquestador
two-step multi-provider, cuotas por hub/mes).

> **El asistente es una CAPACIDAD CORE del Hub (ADR-0033, 2026-06-13; supera la decisión
> 2026-06-09 de "módulo instalable").** Siempre presente por defecto (✨ del topbar), con el proxy
> horneado en el binario (`crates/server/src/assistant.rs`) y el RAG en `apps/ai/knowledge/`; no hay
> `module.zip`, ni install, ni fila `Module`. Billing propio (`AssistantTier`, fuera de
> `ModulePurchase`/`is_module_entitled`). Su WC alcanza a Cloud por una **capacidad de host** del
> runtime: `POST /api/assistant/chat/stream` (proxy SSE → `/api/v1/hub/device/assistant/chat/stream/`,
> reenvía `Bearer` + `X-Hub-Id`), con **ensamblado de tools por permiso** (queries/commands con bloque
> `ai:` que el usuario puede ejecutar). Así se mantiene "el hub nunca habla con el LLM directamente".
> Ver §0bis (punto 6).

### 9.4 Base vectorial: SOLO cloud (pgvector)

Cloud (Aurora): tabla `knowledge_chunk` con `embedding vector(1536)` + índice **HNSW**
`vector_cosine_ops`, por hub y **por versión** (los docs viajan en el `module.zip`; se
indexan en install/update). Evita el *version skew* entre tenants.

### 9.5 Local (SQLite) no tiene base vectorial — estrategia de degradación

- **Opción A (recomendada offline):** índice vectorial **embebido en Rust** — vectores en
  BLOB de SQLite + coseno por fuerza bruta (corpus pequeño) o crate HNSW (`hnsw_rs`/
  `instant-distance`). Cumple "sin pgvector en local" y mantiene RAG sobre lo ya indexado.
- **Opción B:** búsqueda **léxica/BM25** totalmente offline (sin embeddings).
- **Opción C:** RAG **requiere conectividad** (vector store solo en cloud).

> La **generación de embeddings siempre necesita Cloud** (claves LLM). Sin red no hay
> embeddings nuevos; A/B permiten buscar lo ya indexado; sin índice previo, degrada con
> aviso ("no inventar"). `query`/`command` siguen 100% locales.

**Recomendación:** A en local, pgvector en cloud, tras un trait `VectorStore` con dos
implementaciones (`SqliteVectorStore`, `PgVectorStore`) — como `DatabaseAdapter`.

### 9.6 Ingesta enganchada al lifecycle del módulo

install/activate/update → (re)indexar README/`ai_context` de esa versión; uninstall → borrar
sus chunks; boot/cambio de core → reindexar corpus global. Solo se embeben chunks
nuevos/cambiados (dedup por hash).

---

## 10. Seguridad de módulos

- `module.zip` **firmado** + **SHA256** (reusa `ModuleVersion.sha256`).
- Manifest validado contra JSON Schema antes de cargar.
- Permisos **declarativos y namespaced** (`pos.sale.create`).
- **Sin SQL arbitrario** desde el frontend; la UI solo llama queries/commands declarados.
- **WASM sandboxed** (Extism): sin BD/red libres; solo host functions permitidas (allowlist).
- **CSP estricta** (heredada); sin handlers inline.
- Rust **revalida** permisos/tenant/payload en cada ejecución.

---

## 11. Estructura de carpetas de `hub/` (objetivo, no se crea ahora)

> `schemas/` se sube a nivel raíz porque el JSON Schema del manifest es el **contrato
> compartido** por Rust (validación), TS (codegen) y el CLI (validate).

```
hub/
├─ ARQUITECTURA.md
├─ crates/
│  ├─ server/                 # Axum: sirve Ionic + /api/query|command (HTTP) + /ws (eventos) + assets
│  ├─ runtime/                # host genérico (manifest, loader, commands, queries, …)
│  ├─ db/                     # DatabaseAdapter (sqlite, postgres)
│  ├─ vector/                 # VectorStore (sqlite-bruteforce/HNSW, pgvector)
│  ├─ source/                 # adquisición de artefactos: S3 + SHA256 + cache local
│  ├─ cloud-client/           # cliente HTTP del Cloud Portal (JWT+X-Hub-Id, marketplace, assistant)
│  ├─ guest-sdk/              # SDK guest WASM (macro #[command] + host functions)
│  ├─ wasm-host/              # host Extism (sandbox, capacidades, fuel/timeouts)
│  └─ sync/                   # WebSocket / sync
├─ apps/
│  ├─ web/                    # Vite + React + TS + @ionic/react (carga WCs de módulos; sin Capacitor)
│  └─ tauri/                  # empaquetado desktop/móvil (src-tauri/)
├─ packages/
│  ├─ module-sdk/             # SDK TS frontend (transport Tauri/HTTP+WS)
│  ├─ module-types/           # tipos TS generados desde schemas/module.schema.json
│  └─ module-cli/             # erplora module create/build/validate/pack/sign/publish
├─ schemas/                   # ⭐ fuente única del contrato
│  ├─ module.schema.json      # JSON Schema del manifest
│  └─ envelope.schema.json    # request/response de query/command
├─ modules/                   # módulos de ejemplo (inventory, pos)
├─ docker/                    # Dockerfile multi-stage (frontend + binario Rust)
├─ Cargo.toml                 # workspace Rust
└─ package.json               # workspace JS/TS
```

---

## 12. Roadmap por fases ("qué se necesita para empezar")

### Fase 0 — De-risk (validar lo más arriesgado primero)
1. ✅ **Carga dinámica de Web Components con CSP estricta** (riesgo nº1) — **VALIDADO** en la
   estructura real: la app [apps/web/](apps/web/) (**Vite + React + TS + @ionic/react, sin
   Capacitor**) carga con `import()` dinámico el WC **Lit 3** de
   [modules/inventory/](modules/inventory/), compilado a ESM por [packages/module-cli/](packages/module-cli/)
   (`build` → 22.6 KB, **sin `eval`/`new Function`**, CSP-safe). Verificado contra el **build de
   producción de Vite** servido con CSP estricta (`default-src 'none'; script-src 'self';
   style-src 'self'; …`) en **Chrome headless: menú Ionic, WC montado, shadow DOM, 3 productos,
   0 violaciones de CSP** (`pnpm -F @erplora/web verify`). Hallazgos: **@ionic/react no rompe
   CSP estricta** y **Lit** queda confirmado como UI de módulos (§3.1).
2. **Runtime Axum embebido (loopback) ↔ Axum (ECS) sobre el crate `runtime` compartido**: que
   `apps/tauri` (Axum embebido en `127.0.0.1:8787`) y `crates/server` sirvan el **mismo** runtime por
   HTTP+WS (modelo decidido [ADR-0050](../architecture/00-overview/decision-log.md), sin `invoke` para
   datos). *(pendiente doc↔código: el shell puede ir aún por `invoke→HTTP`; la migración es columna
   core.)*
3. **`DatabaseAdapter` + `VectorStore`** con el mismo contrato en SQLite y Postgres
   (incluida la degradación vectorial local).
4. **Handshake con el contrato del Cloud**: cliente Rust que se autentique (`X-Hub-Token`
   bootstrap + `Bearer`), liste el marketplace y **descargue + verifique SHA256** un zip real.
5. **ABI WASM con Extism** [spike]: un command WASM que reciba JSON y devuelva *intenciones*
   ejecutadas en transacción (`sale_lines`).

### Fase 1 — Walking skeleton (lo mínimo end-to-end)
1 módulo + menú dinámico + 1 query + 1 command + 1 evento, sobre SQLite, por **HTTP+WS contra el
runtime Axum embebido** (loopback `127.0.0.1:8787`; modelo decidido
[ADR-0050](../architecture/00-overview/decision-log.md), sin `invoke` para datos) sirviendo Ionic.
Prueba el modelo completo en pequeño. *(pendiente doc↔código: el runtime/shell puede ir aún por
`invoke→HTTP`; la migración es columna core.)*
- 🟡 **Runtime Rust implementado (code-complete, sin compilar aún)**: `crates/db` (SQLite vía
  rusqlite) + `crates/runtime` (manifest → migraciones idempotentes → registry → permisos →
  queries/commands en transacción → bus de eventos), con **scope `hub_id`** e inyección de
  `:hub_id/:current_user_id/:now/:new_id`. Módulo `modules/inventory` con SQL real (migración,
  query, 2 commands, listener). Ejemplo `walking_skeleton` + tests de integración. **Falta
  compilar/ejecutar** (no hay toolchain Rust en el entorno; el sandbox bloquea rustup).
- Pendiente de la fase: `apps/tauri` (Axum embebido en loopback → mismo `runtime`, sin `invoke` para
  datos; ADR-0050) y `crates/server` (Axum).

### Fase 2 — Núcleo declarativo
commands/queries/permisos/migrations/eventos + validación por schema + topo-sort/lifecycle.
**Decidir e implementar el modelo de tenancy** (§2.5, ya fijado: hub_id + DB-por-org).
**Auth de usuario** (§2.9): tabla local de usuarios/roles/PIN, primer login email+password
online + dispositivo de confianza, refresh oportunista de tokens. **Adelantar el `validate`
del CLI** (lint SQL + namespacing + predicado `hub_id`).

### Fase 3 — Cross-módulo (Inventory + POS)
POS usa `inventory.products.list`, emite `pos.sale.completed`, Inventory descuenta stock.
Primer WASM (batch `sale_lines`) o forma *for-each* Tier 1.

### Fase 4 — Modo cloud
Axum + PostgresAdapter + Docker + transport HTTP/WS, integrado con el Cloud Portal sin
cambios. Instalación desde el marketplace real (`source/s3_source` + `cloud-client`).
- **Cloud-side**: enseñar al **sync Git a leer `module.json`** (`manifest_kind`, §2.6) y
  enchufar instalaciones en `Module`/`ModulePurchase`/`HubModuleInstallation`. Exponer
  `ai_tools` por el proxy de asistente existente.

### Fase 5 — WASM + tooling + RAG
`wasm-host` (Extism) + `guest-sdk`; portar `sale_create`/reglas a WASM; capacidades host
(`render.pdf`/`render.xlsx`, `http.fetch` mediado §5.5); CLI completo + firma; `ai_tools` +
`search_docs` (pgvector cloud + degradación local §9.5).

### Fase 6 — Cierre
Conversión de módulos **completada** (99 módulos declarativos; source en `modules-workspace/modules/<id>/`,
cada uno su propio repo git — `hub/modules/` es solo para instalados en runtime).
Queda implementar los handlers Tier 2 WASM + la reubicación del Bridge (§13).

---

## 13. Trabajo pendiente de plataforma (alto nivel)

> La **conversión de módulos** está **hecha**: los 99 módulos son declarativos (2026-06-02); el
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
- **Reubicación del Bridge (§2.7)**: el `bridge/` **no** se retira — se convierte en componente de
  hardware compartido (**sidecar** en Tauri/Local | **standalone opcional** para Hub PWA).
  Migrar su lógica (registro/watchdog/cola/routing de impresión) al shell Tauri y empaquetarla
  como sidecar; mantener el standalone para el combo navegador. Resolver multi-dispositivo (§2.7b).
- **Agrupación de módulos**: se conserva la misma clasificación/grupos del catálogo; la
  clasificación vive en el Cloud Portal, no en el `module.json` (§2.4).
- **Contrato marketplace intacto**: el Portal descarga el zip + verifica SHA256; la ruta S3 y la
  integridad no cambian.

---

## 14. Riesgos, unknowns y decisiones

| Tema | Estado |
|------|--------|
| **Multi-tenancy** | ✅ **Decidido**: BD por **organización** compartida entre hubs; `hub_id` por fila, scope inyectado por el runtime (§2.5). No es `tenant_id`. |
| **IDs de fila** | ✅ **Decidido (ADR-0035)**: **PK = UUID v4 (`TEXT`) en TODO** el dato de negocio (Aurora por-org + SQLite local), no autoincremental; `hub_id` (UUID) sigue siendo el discriminador de tenant. UUID globalmente único ⇒ **NO hay remapeo** al fusionar local↔cloud (§2.5). |
| **Transporte cloud** | ✅ **Decidido**: HTTP (RPC) + canal de push dedicado (§7.5). WS-only descartado como default. |
| **Canal de eventos (push)** | 🔶 **Abierto**: **WS (actual) vs SSE** para el push servidor→cliente. El push es **unidireccional** (los envíos van por HTTP) ⇒ SSE encaja: da **reconexión + Last-Event-ID gratis** (ayuda con el idle timeout del ALB), mantiene **HTTP estándar** (criterio §7.5) y es el formato natural para el **futuro streaming del assistant**. Plan: implementar **ambos** y elegir por situación; al hacerlo, **unificar la forma del JSON del evento** (`name` server vs `event` cliente — hoy desalineado) entre WS y SSE. |
| **Entrega/fiabilidad de eventos** | ✅ **Decidido (2026-06-09)**: **transactional outbox** — escritura atómica en `_event_outbox`, **relay asíncrono** at-least-once con backoff + dead-letter, idempotencia vía `_event_delivery` (§4.1). Sustituye el dispatch inline. **Implementado + verificado** (`crates/runtime/src/outbox.rs` + relay en server). |
| **Documentos de venta / POS** | ✅ **Decidido (2026-06-09)**: tiquet/factura = **FORMATO** de render (`ok-receipt` 80mm / `ok-invoice` A4 en OutfitKit), no módulo; `sales` = libro mayor; pantallas POS **seleccionables** por el negocio; impresión térmica por bridge ESC/POS (§15). |
| **Red saliente de módulos** | ✅ **Decidido (Opción A)**: `http.fetch` mediado (allowlist + creds inyectadas + auditoría §5.5) para terceros; **B (nativo)** para fiscal. |
| **Hardware / Bridge** | ✅ **Decidido**: el `bridge/` **no** se elimina → componente de hardware compartido (sidecar en Tauri/Local \| standalone opcional para Hub PWA), §2.7. ✅ **Transporte: solo RED/LAN** (USB/Bluetooth **descartados** por drivers/mantenimiento). Abierto: multi-dispositivo (primary↔satellite). |
| **Modelo de módulos** | ✅ **Decidido**: híbrido (declarativo + WASM + SDK). |
| **Offline** | ✅ **Decidido (ADR-0040): dos productos, SIN sync.** **Local** (SQLite local autoridad, gratis, 100% offline, un dispositivo) y **Cloud** (ECS+Aurora, online-only, multi-dispositivo). Sin puente; respaldo del Local = módulo `backup` (export cifrado a S3, no sync). Retira el motor de sync y el tier "Cloud DB" de ADR-0029/0031 (§2.8). |
| **Login de usuario** | ✅ **Decidido**: 1er login email+password online → dispositivo de confianza → PIN (offline a futuro); usuarios cloud y solo-locales (§2.9). |
| **Reactividad UI** | ✅ **Decidido**: eventos WS/Tauri → el WC re-consulta (§7.7). Sustituye a LiveComponent. |
| **ABI WASM** | Extism (recomendado) vs WASI vs propia. Validar en Fase 0. |
| **Paridad de framework** | Abierto: slots, hooks/filters, scheduled tasks, i18n → equivalentes declarativos/WASM (§5.6). Multi-fase. |
| **Entitlement en runtime** | Abierto: qué pasa con un módulo (y sus datos) si caduca su suscripción (desactivar / read-only). |
| **Credencial de dispositivo de confianza** | Abierto: formato/rotación de la credencial que habilita el PIN offline (§2.9). |
| **SQL portable** | SQLite↔Postgres: ¿dialecto canónico, capa de query, o migrations por dialecto? |
| **RAG local** | A (embebido Rust, recomendado) vs B (BM25) vs C (solo cloud) (§9.5). |
| **UI de módulos (Lit vs Stencil)** | ✅ **Recomendado Lit** (§3.1, default 2026; no necesitamos wrappers multi-framework). Confirmar con PoC de ambos en Fase 0. |
| **Guest WASM lenguaje** | Rust-only (recomendado, WASM pequeño/rápido) vs multi-lenguaje (JS/Go/Python vía Extism, baja la barrera de autoría). |
| **Impresión / primary-satellite** | ✅ Impresoras de red por terminal; hardware vía shell Tauri (sidecar) o Bridge standalone opcional (§2.7). Abierto: descubrimiento primary↔satellite y promoción si cae el primario (§2.7b). |
| **Agrupación de módulos** | ✅ Se conserva la clasificación/grupos del catálogo (vive en el Cloud Portal, §2.4/§13). |
| **Esfuerzo total** | Cambio de plataforma completo; plan de recursos/tiempo realista. |

**Riesgos concretos a vigilar:**
- **El sync Git del Cloud parsea `module.py`** (§2.6) → sin `manifest_kind`, no ingiere `module.json`.
- **Inmutabilidad S3**: republicar un `v{ver}.zip` rompe SHA256 de clientes (el Cloud lo bloquea).
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
- **Factura A4 física / PDF → `ok-invoice` (HTML)** vía `window.print()` / WeasyPrint (Cloud).

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
module.json = contrato del módulo (lo técnico; la clasificación vive en el Cloud Portal)
WebComponent = pantalla del módulo (Lit; §3.1)
Rust = autoridad / runtime genérico (execute_command / execute_query)
SQLite (local) / Postgres-Aurora (cloud) = solo Rust accede; hub_id (UUID) por fila + PK = UUID v4 (TEXT)
WASM (Extism) = lógica avanzada y batch, en sandbox (sin red/BD libres)
SDK TS = puente para la UI (HttpWsTransport en AMBOS productos; IpcTransport eliminado por ADR-0050; en Local va contra el runtime Axum embebido en loopback 127.0.0.1:8787)
Offline = dos productos SIN sync (ADR-0040): Local (SQLite local autoridad, gratis, offline, un dispositivo) y Cloud (ECS+Aurora, online-only, multi-dispositivo); sin puente. Respaldo del Local = módulo `backup` (export cifrado a S3). Retira el motor de sync y el tier Cloud DB de ADR-0029/0031
Login = email+password online (setup) → dispositivo de confianza → PIN (offline a futuro)
Reactividad = evento (WS, mismo canal en ambos productos; ADR-0050) → el WC re-consulta (no server-render)
Eventos = transactional outbox (escritura atómica + relay async at-least-once + _event_delivery); WS solo push UI (§4.1)
Venta = sales (libro mayor) → sale.completed; tiquet/factura = FORMATO (ok-receipt/ok-invoice), no módulo; pantallas POS seleccionables (§15)
RAG = solo conocimiento (docs); vector en cloud (pgvector), degradado en local
AI = embeddings + generación SIEMPRE por el proxy del Cloud Portal (medido)
Red de módulos = http.fetch mediado por el host (Opción A) / nativo para fiscal
2 productos = Local (single/SQLite, Tauri, offline, gratis) · Hub PWA (cloud/Aurora, PWA, online, de pago) (§1)
Impresión/hardware = Local: Bridge como sidecar Tauri · Hub PWA: Bridge standalone opcional; §2.7
Primary/Satellite = varios terminales del mismo hub; cobrar/imprimir solo el primario
Migración = gradual, POS-first, manteniendo la agrupación actual de módulos
Cloud Portal (Django) = marketplace + billing + provisioning + proxy AI (no cambia)
hub = el runtime del tenant
```

> ERPlora no instala código backend arbitrario: instala **capacidades declarativas** (y
> WASM en sandbox) que Rust valida, registra y ejecuta. Como WordPress, pero más seguro,
> portable y eficiente — y con el mismo modelo en local y en cloud.
