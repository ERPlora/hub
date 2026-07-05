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
> `modules/inventory` con WC Lit; CSP validada — §14). Última actualización: 2026-06-30
> (decisiones fijadas: impresoras **solo LAN**, **PK = UUID v4 `TEXT` en todo** el dato de negocio (ADR-0035, sin remapeo) — §2.5, §2.7, §14).

---

## 0. Propósito

Este documento describe **qué** queremos construir y **por qué**, reconciliando la
visión técnica (Rust/Ionic/Tauri/module.json) con la **realidad de producción** de
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
   y el RAG en `apps/ai/knowledge/` — no hay `module.zip`, ni install, ni fila `Module` en el catálogo.
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

## 1. Visión: "un solo modelo mental" — dos productos

hub es **una sola app base** (misma UI, mismo modelo de módulos, mismo runtime). Se entrega en
**dos productos** con configuración fija — *no* en una matriz de ejes (framing retirado por
[ADR-0080](../architecture/00-overview/decision-log.md)):

> **Modelo decidido ([ADR-0050](../architecture/00-overview/decision-log.md), app unificada,
> aceptada 2026-06-17):** **un solo runtime Axum en AMBOS productos**, **mismo transporte de datos**
> = **HTTP (RPC) + WebSocket (solo eventos)**. Se **elimina** `invoke`/IPC **para datos**: en Hub Local,
> el runtime Axum corre **embebido como servidor loopback** (`127.0.0.1:8787`) y la UI le habla por
> HTTP+WS igual que la PWA shell. La **única diferencia** entre productos es el `DatabaseAdapter` (SQLite
> Hub Local ↔ Postgres/Aurora Hub Cloud) y el almacenamiento de ficheros (disco local ↔ S3).
> *(estado código 2026-06-30: data-IPC eliminado —SDK `IpcTransport` + handlers `invoke` de datos del shell `erplora_query`/`erplora_command`—; pendiente, columna core: en Hub Local el front y el runtime embebido deben compartir ORIGEN —el runtime sirve el `dist/` y la ventana Tauri carga de `127.0.0.1:8787`— para que `HttpWsTransport` alcance el loopback sin CORS.)*

- **Hub Local (Tauri)**: el shell Tauri **arranca el bridge embebido** (servidor localhost, mismo canal
  que la PWA shell, reusando `crates/peripherals`) — **no** por handlers `invoke`. **El shell Tauri *es* el
  bridge** — no hay proceso aparte ni segundo install.
- **Hub Cloud**: el navegador **no puede** abrir TCP crudo (puerto 9100), USB ni
  Bluetooth clásico. Si ese usuario necesita hardware físico, instala el **Bridge standalone**
  (opcional); la PWA shell lo detecta por WebSocket en `localhost`. Si no lo necesita, imprime por
  PDF/email o impresora **ePOS-HTTP** (alcanzable por navegador). *Pega conocida: una PWA
  `https://` ↔ `ws://localhost` arrastra fricción de mixed-content/pairing — el bridge embebido del
  shell Tauri (loopback) no la tiene.*

**Transportes de impresora** — ✅ **Decidido: SOLO RED (TCP/IP ESC/POS, puerto 9100) — 100% LAN.**
USB y Bluetooth **se descartan**: exigen drivers + mantenimiento por dispositivo/SO que no compensa.
La red es además el caso más simple (un socket TCP, trivial en Rust) y el más estable; en **Hub Local
(Tauri)** el runtime abre el socket al puerto 9100 directamente. El Bridge es **red-only por
construcción**: el crate `crates/peripherals` no incluye USB ni Bluetooth. Consecuencia para **Hub
Cloud**: como el navegador no abre TCP crudo, **imprimir requiere el Bridge** (sidecar Tauri o
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
standalone queda **opcional**, solo para **Hub Cloud**. El escáner por HID lo maneja el
SO/navegador como teclado.

> El escenario **Hub Cloud + hardware físico** ya **no** queda fuera de alcance: se cubre
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
    `localhost:12321`. Es el de **Hub Cloud**.
  - **Bridge embebido en Tauri** `hub/apps/tauri` — el shell **arranca el bridge embebido** (servidor
    localhost, mismo canal HTTP/WS que la PWA shell, reusando el mismo crate), **no** por handlers `invoke`
    (modelo decidido [ADR-0050](../architecture/00-overview/decision-log.md); `invoke` solo nativo).
    Es el de **Hub Local (Tauri)**. *(estado código 2026-06-30: data-IPC eliminado —SDK `IpcTransport` + handlers `invoke` de datos del shell `erplora_query`/`erplora_command`—; pendiente, columna core: en Hub Local el front y el runtime embebido deben compartir ORIGEN —el runtime sirve el `dist/` y la ventana Tauri carga de `127.0.0.1:8787`— para que `HttpWsTransport` alcance el loopback sin CORS.)* |
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
// usan HTTP+WS contra el runtime Axum — embebido en loopback 127.0.0.1:8787 (Hub Local) o ECS (Hub Cloud).
// HttpWsTransport → HTTP POST query/command + WebSocket solo para eventos          (Hub Local y Hub Cloud)
// (WsTransport — todo por un WS — queda como alternativa, no por defecto; §7.5)
// (estado código 2026-06-30: data-IPC eliminado; pendiente —columna core—: en Hub Local el front y el runtime embebido comparten ORIGEN para que HttpWsTransport alcance el loopback.)
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
erplora module publish <id>     # sube al marketplace del SaaS (§2.2)
```

### 7.5 Transporte y comunicación — ¿todo por WebSocket?

**No.** El transporte de datos es **HTTP para RPC + WebSocket solo para eventos**, no "todo por un
WS". WS-only obligaría a reimplementar el framing RPC (correlación de IDs, timeouts, replay) que
HTTP da gratis.

**Modelo decidido ([ADR-0050](../architecture/00-overview/decision-log.md)):** **AMBOS productos**
usan el **mismo transporte de datos** (HTTP+WS) contra el runtime Axum; en **Hub Local** ese runtime
corre **embebido como servidor loopback** (`127.0.0.1:8787`), en **Hub Cloud** en ECS. Se **eliminó**
`invoke`/IPC para datos. La diferencia entre productos es **solo** el `DatabaseAdapter` (SQLite ↔
Aurora) y los ficheros (disco ↔ S3). *(estado código 2026-06-30: data-IPC eliminado —SDK `IpcTransport` + handlers `invoke` de datos del shell `erplora_query`/`erplora_command`—; pendiente, columna core: en Hub Local el front y el runtime embebido deben compartir ORIGEN —el runtime sirve el `dist/` y la ventana Tauri carga de `127.0.0.1:8787`— para que `HttpWsTransport` alcance el loopback sin CORS.)*

| Qué | Hub Local — runtime Axum embebido (loopback) | Hub Cloud — Axum (ECS) |
|-----|------------------------|------------------------|
| `query` / `command` (RPC) | **HTTP POST** (`/api/query`, `/api/command`) | **HTTP POST** (`/api/query`, `/api/command`) |
| Eventos / push | **WebSocket** (`/ws`, solo push) | **WebSocket** (`/ws`, solo push) |
| App Ionic + assets | filesystem | **HTTP/CDN** |
| Bundles UI de módulos | filesystem | **HTTP/CDN** |
| Descarga `module.zip` | **HTTP** (S3) | **HTTP** (S3) |
| Exports PDF/Excel | **HTTP** | **HTTP** |
| SaaS (marketplace, billing, embeddings/LLM) | **HTTP REST** (user-JWT + `X-Hub-Id`) | **HTTP REST** |

> **Canal de hardware (modelo decidido, [ADR-0050](../architecture/00-overview/decision-log.md)):**
> el bridge usa el **mismo canal localhost (HTTP/WS) en los dos productos**. En **Hub Local (Tauri)** el
> shell **arranca el bridge embebido** (servidor localhost, mismo canal que la PWA shell, reusando
> `crates/peripherals`) — **NO** por handlers `invoke`. En **Hub Cloud** ese canal lo aporta el
> **Bridge standalone opcional** por `ws://localhost` (§2.7). `invoke` queda **solo** para lo nativo
> sin equivalente HTTP (keychain, device_id, ciclo de vida), no para hardware.

**Escala**: un hub tiene **1–5 usuarios (máx ~30)**, con tolerancia a crecer. A esa escala
el rendimiento **no decide**; deciden resiliencia y simplicidad:

- **Degradación elegante (clave para un TPV)**: si el WebSocket cae, las **ventas siguen
  por HTTP**; solo se pierden las actualizaciones en vivo. Con WS-only, si el socket falla, **todo** falla.
- **Más simple**: HTTP no necesita framing RPC sobre WS. **Tooling estándar** (reintentos,
  idempotencia, `curl`, proxies/CDN). WebSocket queda **solo para push**.
- **Mismo transporte en Hub Local y Hub Cloud** (modelo decidido, ADR-0050): HTTP (RPC) + WebSocket
  (solo push) contra el runtime Axum, embebido en loopback en Hub Local. *(estado código 2026-06-30: data-IPC eliminado —SDK `IpcTransport` + handlers `invoke` de datos del shell `erplora_query`/`erplora_command`—; pendiente, columna core: en Hub Local el front y el runtime embebido deben compartir ORIGEN —el runtime sirve el `dist/` y la ventana Tauri carga de `127.0.0.1:8787`— para que `HttpWsTransport` alcance el loopback sin CORS.)*

> **Decisión: ambos productos = HTTP (RPC) + WebSocket (solo eventos).** WS-only queda como
> alternativa (todo por un solo canal), pero no por defecto.

### 7.6 Garantía: el mismo módulo corre en ambos productos sin trabajo adicional

> **Modelo decidido ([ADR-0050](../architecture/00-overview/decision-log.md)):** ambos productos
> usan **HTTP+WS** contra el runtime Axum (embebido en loopback en Hub Local). El SDK ya **no** tiene
> `IpcTransport`. *(estado código 2026-06-30: data-IPC eliminado —SDK `IpcTransport` + handlers `invoke` de datos del shell `erplora_query`/`erplora_command`—; pendiente, columna core: en Hub Local el front y el runtime embebido deben compartir ORIGEN —el runtime sirve el `dist/` y la ventana Tauri carga de `127.0.0.1:8787`— para que `HttpWsTransport` alcance el loopback sin CORS.)*
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

### Fase 4 — Hub Cloud
Axum + PostgresAdapter + Docker + transport HTTP/WS, integrado con el SaaS sin
cambios. Instalación desde el marketplace real (`source/s3_source` + `cloud-client`).
- **SaaS-side**: enseñar al **sync Git a leer `module.json`** (`manifest_kind`, §2.6) y
  enchufar instalaciones en `Module`/`ModulePurchase`/`HubModuleInstallation`. Exponer
  `ai_tools` por el proxy de asistente existente.

### Fase 5 — WASM + tooling + RAG
`wasm-host` (Extism) + `guest-sdk`; portar `sale_create`/reglas a WASM; capacidades host
(`render.pdf`/`render.xlsx`, `http.fetch` mediado §5.5); CLI completo + firma; `ai_tools` +
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
- **Reubicación del Bridge (§2.7)**: el `bridge/` **no** se retira — se convierte en componente de
  hardware compartido (**sidecar** en Tauri/Hub Local | **standalone opcional** para Hub Cloud).
  Migrar su lógica (registro/watchdog/cola/routing de impresión) al shell Tauri y empaquetarla
  como sidecar; mantener el standalone para el combo navegador. Resolver multi-dispositivo (§2.7b).
- **Agrupación de módulos**: se conserva la misma clasificación/grupos del catálogo; la
  clasificación vive en el SaaS, no en el `module.json` (§2.4).
- **Contrato marketplace intacto**: el SaaS descarga el zip + verifica SHA256; la ruta S3 y la
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
| **Hardware / Bridge** | ✅ **Decidido**: el `bridge/` **no** se elimina → componente de hardware compartido (sidecar en Tauri/Hub Local \| standalone opcional para Hub Cloud), §2.7. ✅ **Transporte: solo RED/LAN** (USB/Bluetooth **descartados** por drivers/mantenimiento). Abierto: multi-dispositivo (primary↔satellite). |
| **Modelo de módulos** | ✅ **Decidido**: híbrido (declarativo + WASM + SDK). |
| **Offline** | ✅ **Decidido (ADR-0040): dos productos, SIN sync.** **Hub Local** (SQLite local autoridad, gratis, 100% offline, un dispositivo) y **Hub Cloud** (ECS+Aurora, online-only, multi-dispositivo). Sin puente; respaldo del Hub Local = módulo `backup` (export cifrado a S3, no sync). Retira el motor de sync y el tier "Cloud DB" de ADR-0029/0031 (§2.8). |
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
SQLite (local) / Postgres-Aurora (cloud) = solo Rust accede; hub_id (UUID) por fila + PK = UUID v4 (TEXT)
WASM (Extism) = lógica avanzada y batch, en sandbox (sin red/BD libres)
SDK TS = puente para la UI (HttpWsTransport en AMBOS productos; IpcTransport eliminado por ADR-0050; en Hub Local va contra el runtime Axum embebido en loopback 127.0.0.1:8787)
Offline = dos productos SIN sync (ADR-0040): Hub Local (SQLite local autoridad, gratis, offline, un dispositivo) y Hub Cloud (ECS+Aurora, online-only, multi-dispositivo); sin puente. Respaldo del Hub Local = módulo `backup` (export cifrado a S3). Retira el motor de sync y el tier Cloud DB de ADR-0029/0031
Login = email+password online (setup) → dispositivo de confianza → PIN (offline a futuro)
Reactividad = evento (WS, mismo canal en ambos productos; ADR-0050) → el WC re-consulta (no server-render)
Eventos = transactional outbox (escritura atómica + relay async at-least-once + _event_delivery); WS solo push UI (§4.1)
Venta = sales (libro mayor) → sale.completed; tiquet/factura = FORMATO (ok-receipt/ok-invoice), no módulo; pantallas POS seleccionables (§15)
RAG = solo conocimiento (docs); vector en cloud (pgvector), degradado en local
AI = embeddings + generación SIEMPRE por el proxy del SaaS (medido)
Red de módulos = http.fetch mediado por el host (Opción A) / nativo para fiscal
2 productos = Hub Local (single/SQLite, Tauri, offline, gratis) · Hub Cloud (cloud/Aurora, PWA, online, de pago) (§1)
Impresión/hardware = Hub Local: Bridge como sidecar Tauri · Hub Cloud: Bridge standalone opcional; §2.7
Primary/Satellite = varios terminales del mismo hub; cobrar/imprimir solo el primario
Migración = gradual, POS-first, manteniendo la agrupación actual de módulos
SaaS (Django) = marketplace + billing + provisioning + proxy AI (no cambia)
hub = el runtime del tenant
```

> ERPlora no instala código backend arbitrario: instala **capacidades declarativas** (y
> WASM en sandbox) que Rust valida, registra y ejecuta. Como WordPress, pero más seguro,
> portable y eficiente — y con el mismo modelo en local y en cloud.
