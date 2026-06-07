# hub — Arquitectura

> **Documento de diseño.** Define el Hub de
> ERPlora: **Ionic React + Rust/Axum + Tauri + módulos declarativos (module.json) +
> WASM + SDK**, con **SQLite en local** y **PostgreSQL/Aurora en cloud**.
>
> **hub ES el Hub de ERPlora.**
>
> Fuentes: visión [erplora_arquitectura_modular_ionic_rust_tauri.md](../docs/arquitectura/erplora_arquitectura_modular_ionic_rust_tauri.md),
> diseño AI/RAG [PLAN-ASISTENTE-RAG.md](../docs/arquitectura/PLAN-ASISTENTE-RAG.md), mapa del monorepo
> [CLAUDE.md](../CLAUDE.md).
>
> **Estado:** propuesta + scaffolding inicial (`apps/web` Ionic React, primer módulo
> `modules/inventory` con WC Lit; CSP validada — §14). Última actualización: 2026-05-31
> (decisiones fijadas: impresoras **solo LAN**, **IDs numéricos** en el hub / UUID solo en Cloud — §2.5, §2.7, §14).

---

## 0. Propósito

Este documento describe **qué** queremos construir y **por qué**, reconciliando la
visión técnica (Rust/Ionic/Tauri/module.json) con la **realidad de producción** de
ERPlora (Cloud Portal en Django, marketplace, billing Stripe, provisioning AWS,
contrato S3 + SHA256, auth, asistente AI con RAG).

---

## 1. Visión: "un solo modelo mental" — dos ejes ortogonales

hub es **una sola app base** (misma UI, mismo modelo de módulos, mismo runtime). Lo que
varía se reduce a **dos ejes independientes** — *no* una "topología" única. Confundirlos (atar
Tauri↔local↔SQLite y navegador↔cloud↔Aurora en un solo interruptor) es el error que esta sección
corrige:

- **Eje A — Backend de datos** (lo que se compra como producto): `single` (SQLite embebido,
  offline-first, monousuario) · `cloud` (Aurora/Postgres en un contenedor ECS por hub,
  multiusuario/multitienda). Selecciona el *adaptador de BD* y el *transport de datos*.
- **Eje B — Shell / empaquetado** (cómo se ejecuta ese día): `tauri` (desktop/móvil; **da acceso
  a recursos locales** — hardware, filesystem) · `web-pwa` (navegador; sin hardware directo).

Los dos ejes **no están acoplados**: un shell Tauri puede envolver *cualquiera* de los dos
backends. Combos válidos:

```
single + Tauri     IPC → runtime embebido → SQLite        (producto "independiente", offline-first)
cloud  + web-PWA   Browser → Rust/Axum (ECS) → Aurora      (producto "cloud", sin hardware local directo)
cloud  + Tauri     HTTP+WS → Rust/Axum (ECS) → Aurora      (cloud con hardware local vía el shell)
──────────────────────────────────────────────────────────
single + web-PWA   no aplica: `single` exige runtime embebido ⇒ siempre Tauri
```

Asimetría a recordar: **`single` ⟹ Tauri** (forzado); **Tauri no ⟹ single** (puede ser cliente
cloud); **`web-pwa` ⟹ cloud** (forzado).

- **UI idéntica**: Ionic React como *shell*; cada módulo aporta su pantalla como Web
  Component (Lit, §3.1), cargado dinámicamente. El **hardware es una capacidad solo-Tauri**:
  presente en el build Tauri, ausente en el build web (se modela con un *capabilities descriptor*
  que el runtime expone y la UI usa solo para mostrar/ocultar).
- **Transport de datos intercambiable** (Eje A): backend `single` → `Tauri invoke` (IPC) +
  Tauri events; backend `cloud` → **HTTP (RPC) + WebSocket (solo eventos)**. El SDK oculta la
  diferencia y el cambio no requiere nada adicional (§7.5, §7.6).
- **Canal de recursos locales** (Eje B): en cualquier shell Tauri, `invoke` a plugins nativos
  para hardware/FS — **independiente del transport de datos**. En `cloud + Tauri` los datos van
  por HTTP+WS y `invoke` se usa **solo** para este canal local (§2.7, §7.5).
- **DB intercambiable**: `DatabaseAdapter` con backends SQLite y PostgreSQL (§8).
- **Offline/online (Fase 1)**: el backend **`single` funciona offline** (SQLite del dispositivo)
  **tras un primer arranque online** (login + provisión + descarga de módulos, §2.8/§2.9); el
  backend **`cloud` es solo online**. **Sin sync de datos de negocio** entre ambos en esta
  fase (§2.8).
- **Rust es la autoridad**: valida permisos, tenant (`hub_id`), payload y ejecuta. La UI
  nunca toca la base de datos.

> El WebComponent no toca la BD. El WebComponent llama al SDK. El SDK llama a Rust.
> Rust valida permisos, payload y tenant, y ejecuta.

---

## 2. Reconciliación con la realidad de producción (sección crítica)

### 2.1 Hay DOS "Clouds" — no confundirlos

| Pieza | Qué es | Tecnología | ¿Cambia? |
|-------|--------|-----------|----------|
| **Cloud Portal** | `erplora.com`: landing, dashboard, **marketplace**, **billing Stripe**, **provisioning** (boto3 → ECS+Aurora), **proxy AI** | Django 6 + Datastar | **NO** |
| **hub (modo cloud)** | El **runtime del tenant** en ECS. Sirve la app Ionic y ejecuta módulos | Rust + Axum | **SÍ** |
| **hub (modo local)** | El mismo runtime **embebido** en un shell Tauri (desktop/móvil), offline-first con SQLite. El shell Tauri también puede actuar como **cliente del modo cloud** (datos en Aurora, hardware local vía `invoke`) — los ejes backend/shell son ortogonales (§1) | Rust + Tauri | Nuevo |

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

> ⚠️ El root `CLAUDE.md` dice que "se eliminó el token de máquina"; **el código actual NO
> lo ha eliminado**. Hoy conviven **tres credenciales** y hub debe replicarlas igual.

1. **Token de aplicación del hub (`cloud_api_token`)** — *el "token del primer login"*. Se
   **genera al registrar el hub** (`Hub.save()` → `secrets.token_hex(32)`, devuelto al
   wizard de setup), guardado **cifrado** en Cloud (`Hub.cloud_api_token`). Viaja como
   header **`X-Hub-Token`** + `X-Hub-Id`. Se usa para el **bootstrap del hub**
   (`GET /api/hubs/{hub_id}/bootstrap/`, validado con `secrets.compare_digest`) y contexto
   máquina (`IsHubMachine`).
2. **JWT del usuario activo** — llamadas iniciadas por un usuario: `Authorization:
   Bearer <access>` + `X-Hub-Id`. Persistido en el hub (`HubConfig.hub_jwt` +
   `hub_refresh_token`) y en memoria (`jwt_holder`); refresh en `POST /api/v1/auth/refresh/`
   (reintento en 401). Autoriza contra membresía de org (`IsHubMember`/`IsHubAdmin`).
3. **`X-Webhook-Secret`** (== `CLOUD_WEBHOOK_SECRET`) + `X-Hub-Id` para M2M de fondo.

> **hub replica esto tal cual**: en el registro/primer contacto obtiene su
> `cloud_api_token`, lo usa para el bootstrap, y luego usa el JWT del usuario.
> *(Pendiente menor: alinear el root `CLAUDE.md`, desactualizado.)*

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
- ✅ **IDs de fila (decidido)**: los datos de negocio del hub (Aurora por-org **y** SQLite local)
  usan **PK numérica autoincremental** (`BIGINT`/`INTEGER`), **no UUID**. El **UUID es exclusivo
  del Cloud Portal** (identificadores de control: `hub_id`, organización…). Así una fila de negocio
  lleva **PK numérica** (única dentro del hub) + discriminador **`hub_id` (UUID)** que viene del
  Cloud. Consecuencia para una futura migración local→cloud (§2.8 / Fase 6): al fusionar un SQLite
  local en la BD compartida de la org, los IDs numéricos **se remapean** (no se conservan tal cual)
  y se reescriben las FKs — porque varios hubs comparten secuencia en esa BD.

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
> transparente) y (b) **instalador standalone opcional** para el combo `cloud + web-PWA`.

**Cómo obtiene hardware cada combo (§1):**
- **`single + Tauri`** y **`cloud + Tauri`**: vía `invoke` → plugins nativos del shell (o el
  Bridge como **sidecar** dentro del binario Tauri). **El shell Tauri *es* el bridge** — no hay
  proceso aparte ni segundo install. (En `cloud + Tauri` los datos van por HTTP+WS; `invoke` es
  **solo** el canal de hardware.)
- **`cloud + web-PWA`**: el navegador **no puede** abrir TCP crudo (puerto 9100), USB ni
  Bluetooth clásico. Si ese usuario necesita hardware físico, instala el **Bridge standalone**
  (opcional); la PWA lo detecta por WebSocket en `localhost`. Si no lo necesita, imprime por
  PDF/email o impresora **ePOS-HTTP** (alcanzable por navegador). *Pega conocida: una PWA
  `https://` ↔ `ws://localhost` arrastra fricción de mixed-content/pairing — el camino `invoke`
  de Tauri no la tiene.*

**Transportes de impresora** — ✅ **Decidido: SOLO RED (TCP/IP ESC/POS, puerto 9100) — 100% LAN.**
USB y Bluetooth **se descartan**: exigen drivers + mantenimiento por dispositivo/SO que no compensa.
La red es además el caso más simple (un socket TCP, trivial en Rust) y el más estable; en `single +
Tauri` el runtime abre el socket al puerto 9100 directamente. El Bridge actual
(`bridge/…/protocol.py`) soporta USB/BT, pero **hub no los expone**. Consecuencia para `cloud +
web-PWA`: como el navegador no abre TCP crudo, **imprimir requiere el Bridge** (sidecar Tauri o
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
standalone queda **opcional**, solo para `cloud + web-PWA`. El escáner por HID lo maneja el
SO/navegador como teclado.

> El escenario **`cloud + web-PWA` + hardware físico** ya **no** queda fuera de alcance: se cubre
> con el **Bridge standalone opcional**. El POS en navegador es un combo de primera clase (§1),
> no una excepción.

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

### 2.8 Modelo offline (local) vs online (cloud) — alcance de la Fase 1

> ✅ **Decisión (Fase 1): NO hay motor de sincronización de datos de negocio entre local
> y cloud.** Son **dos modos de despliegue** del mismo código, no dos copias de un mismo dato:
> - **Local (Tauri)**: **funciona offline**. Sus datos viven en el **SQLite del dispositivo**
>   y operan sin internet. Autónomo para el día a día (ventas, caja, inventario).
> - **Cloud (Axum/Aurora)**: **solo online**. En esta primera fase **no** hay alternativa
>   para que el cloud opere sin internet.

- **Qué SÍ necesita internet incluso en local** (degradan, no rompen el flujo de caja):
  instalación de módulos desde el marketplace, **AI** (embeddings + generación, §9.3) y el
  **primer login/configuración** (§2.9). Sin red, el negocio sigue operando con lo instalado;
  esas funciones quedan en espera.
- **Durabilidad del dato local**: backup **SQLite → S3** (como ya hace el hub actual en
  planes Lite), **no** un sync bidireccional.
- **Futuro (fuera de Fase 1)**: un eventual sync local↔cloud (cola de cambios + resolución
  de conflictos / CRDTs) sería un proyecto aparte. El crate `sync` (§11) queda para **eventos
  en vivo**, no para replicación de datos de negocio en Fase 1.

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

**Tauri-como-hub vs Tauri-como-cliente** (consecuencia de los dos ejes, §1 — y la respuesta a
"¿el local necesita login?": **sí, una vez y online**, porque es lo que provisiona la identidad y
los entitlements para descargar módulos):
- **`single + Tauri`**: la app **es el hub**. El primer login online **auto-provisiona** su
  identidad de máquina (el `cloud_api_token` / `X-Hub-Token` de §2.3) en el dispositivo y la
  persiste como credencial de dispositivo (*decisión abierta §14*). Tras eso opera offline.
- **`cloud + Tauri`**: la app es **cliente de un hub remoto** ya provisionado por el Portal
  (boto3 → ECS+Aurora). **No** auto-provisiona identidad de máquina: solo autentica al **usuario**
  (JWT + `X-Hub-Id`) y usa `invoke` para hardware local. El `cloud_api_token` vive en ECS, no en
  el dispositivo. → el "origen de la credencial de máquina" depende del **Eje A**, no de que sea Tauri.

---

## 3. Stack y decisiones de tecnología

| Capa | Elección | Motivo |
|------|----------|--------|
| Shell frontend | **Ionic React 8.8 + Vite + TS + Tailwind v4 + react-icons** | Componentes Ionic reales; **sin Capacitor** (runtime nativo = Tauri). Tematizado por `--ion-*` (§3.1, §15) |
| UI de módulos | **Web Components** (Lit recomendado, §3.1) | WC estándar, cargables dinámicamente; default 2026 |
| Runtime/backend | **Rust + Axum** | Runtime ligero/portátil, una sola autoridad, sin Node en prod local |
| Desktop/móvil | **Tauri v2** | Empaqueta la misma UI; binario pequeño; `invoke` = transport de datos (backend `single`) **y/o** canal de hardware local (cualquier backend, §2.7); puede actuar como cliente del backend cloud |
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
> React/Vue/Angular — que **NO es nuestro caso** (nuestro shell es solo Ionic React).

| | **Lit** (Google) | **Stencil** (OutSystems/Ionic) |
|---|---|---|
| Qué es | Librería ~5 KB en runtime sobre WC nativos | **Compilador** → WC optimizados + wrappers React/Vue/Angular |
| Pros | Ligero, cercano al estándar, sin paso de compilación, **default 2026**, respaldo Google | Muy optimizado (lazy-load, scoped CSS, prerender), wrappers multi-framework |
| Contras | Menos "baterías incluidas" | "Caja negra", más complejo; su killer-feature (multi-framework) **no la usamos** |

- **Por qué Lit aquí**: el único consumidor es **Ionic React**; la ventaja única de Stencil
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
`permissions`, `commands`, `queries`, `events`, `ui`, `wasm`, `errors`.

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
// IpcTransport    → invoke('erplora_query', { name, params }) + Tauri events       (local)
// HttpWsTransport → HTTP POST query/command + WebSocket solo para eventos          (cloud)
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

**No.** El IPC local ya son **dos mecanismos**: `invoke` (RPC) + Tauri events (push). El
espejo fiel en cloud es **HTTP para RPC + WebSocket solo para eventos**, no "todo por un WS".
WS-only obligaría a reimplementar el framing RPC (correlación de IDs, timeouts, replay) que
HTTP da gratis.

Esta tabla es por **backend de datos** (Eje A, §1), **no** por shell. La columna "single" usa
IPC porque `single ⟹ Tauri`; pero un shell Tauri sobre backend `cloud` usa la columna "cloud".

| Qué | Backend `single` (IPC) | Backend `cloud` (Axum) |
|-----|------------------------|------------------------|
| `query` / `command` (RPC) | `invoke` | **HTTP POST** (`/api/query`, `/api/command`) |
| Eventos / push | Tauri events | **WebSocket** (`/ws`, solo push) |
| App Ionic + assets | filesystem | **HTTP/CDN** |
| Bundles UI de módulos | filesystem | **HTTP/CDN** |
| Descarga `module.zip` | **HTTP** (S3) | **HTTP** (S3) |
| Exports PDF/Excel | **HTTP** | **HTTP** |
| Cloud Portal (marketplace, billing, embeddings/LLM) | **HTTP REST** (user-JWT + `X-Hub-Id`) | **HTTP REST** |

> **Ortogonal a la tabla — canal de recursos locales (Eje B):** en cualquier shell Tauri,
> `invoke` a plugins nativos para **hardware/FS** (impresora, cajón, escáner). Está **siempre**
> disponible si el shell es Tauri, **independientemente del backend**. En `cloud + Tauri` los
> datos van por la columna "cloud" (HTTP+WS) y `invoke` se usa **solo** para este canal local
> (§2.7). En `cloud + web-PWA` ese canal lo aporta el **Bridge standalone opcional** por
> `ws://localhost`.

**Escala**: un hub tiene **1–5 usuarios (máx ~30)**, con tolerancia a crecer. A esa escala
el rendimiento **no decide**; deciden resiliencia y simplicidad:

- **Degradación elegante (clave para un TPV)**: si el WebSocket cae, las **ventas siguen
  por HTTP**; solo se pierden las actualizaciones en vivo. Con WS-only, si el socket falla, **todo** falla.
- **Más simple**: HTTP no necesita framing RPC sobre WS. **Tooling estándar** (reintentos,
  idempotencia, `curl`, proxies/CDN). WebSocket queda **solo para push**.
- **En local NO hay WebSocket**: `invoke` (IPC directo) + Tauri events.

> **Decisión: cloud = HTTP (RPC) + WebSocket (solo eventos).** WS-only queda como
> alternativa (todo por un solo canal), pero no por defecto.

### 7.6 Garantía: cambiar de IPC a HTTP/WS no requiere nada adicional

1. **Envelope único agnóstico al cable** (`schemas/envelope.schema.json`):
   `Request{ id, kind, name, params }`, `Response{ id, ok, data|error }`, `Event{ name, payload }`.
2. **Core del runtime agnóstico al transporte**: `handle(Request) -> Response` + stream
   `events`. No sabe si lo invocó IPC, HTTP o WS.
3. **Una sola interfaz** `ErploraTransport` con 3 impls (`IpcTransport`, `HttpWsTransport`, `WsTransport`).
4. **Flag de arranque para el transport de datos** `RUNTIME_TRANSPORT=ipc|http+ws|ws` (Eje A).
   Ningún campo de `module.json`, ni código de módulo, ni lógica de permisos depende del transporte.
5. **El shell (Eje B) es una dimensión de *build/boot* independiente**: el mismo frontend se
   empaqueta como Tauri o como web-PWA. `cloud + Tauri` = transport `http+ws` **+** shell Tauri
   (con su canal `invoke` de hardware, §2.7). **No hay acoplamiento shell↔backend.**

→ El mismo módulo y la misma UI corren con **cualquier** combinación de backend (Eje A) y shell
(Eje B) **cambiando solo los adaptadores en el boot**. Cero trabajo adicional.

### 7.7 Reactividad de la UI (decidido: eventos WS → el WC re-consulta)

> ✅ **Decisión.** El Web Component mantiene su **estado en el cliente**. Cuando llega un
> **evento** relevante (p. ej. `inventory.stock.updated`) por **WebSocket (cloud)** o **Tauri
> events (local)**, el WC **vuelve a hacer la query** afectada y se repinta.

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
2. **Tauri v2 `invoke` → crate `runtime` compartido**: que `apps/tauri` y `crates/server`
   llamen al **mismo** runtime.
3. **`DatabaseAdapter` + `VectorStore`** con el mismo contrato en SQLite y Postgres
   (incluida la degradación vectorial local).
4. **Handshake con el contrato del Cloud**: cliente Rust que se autentique (`X-Hub-Token`
   bootstrap + `Bearer`), liste el marketplace y **descargue + verifique SHA256** un zip real.
5. **ABI WASM con Extism** [spike]: un command WASM que reciba JSON y devuelva *intenciones*
   ejecutadas en transacción (`sale_lines`).

### Fase 1 — Walking skeleton (lo mínimo end-to-end)
1 módulo + menú dinámico + 1 query + 1 command + 1 evento, sobre SQLite, con Tauri `invoke`
+ Axum sirviendo Ionic. Prueba el modelo completo en pequeño.
- 🟡 **Runtime Rust implementado (code-complete, sin compilar aún)**: `crates/db` (SQLite vía
  rusqlite) + `crates/runtime` (manifest → migraciones idempotentes → registry → permisos →
  queries/commands en transacción → bus de eventos), con **scope `hub_id`** e inyección de
  `:hub_id/:current_user_id/:now/:new_id`. Módulo `modules/inventory` con SQL real (migración,
  query, 2 commands, listener). Ejemplo `walking_skeleton` + tests de integración. **Falta
  compilar/ejecutar** (no hay toolchain Rust en el entorno; el sandbox bloquea rustup).
- Pendiente de la fase: `apps/tauri` (`invoke` → mismo `runtime`) y `crates/server` (Axum).

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
Conversión de módulos **completada** (99 módulos declarativos en `hub/modules/`).
Queda implementar los handlers Tier 2 WASM + la reubicación del Bridge (§13).

---

## 13. Trabajo pendiente de plataforma (alto nivel)

> La **conversión de módulos** está **hecha**: los 99 módulos viven en `hub/modules/`
> (declarativos, 2026-06-02). Lo que **queda** es implementar los handlers **Rust→WASM Tier 2**
> (documentados en los `WASM-TODO.md` por módulo) y la **reubicación del Bridge** (§2.7).

- **Reubicación del Bridge (§2.7)**: el `bridge/` **no** se retira — se convierte en componente de
  hardware compartido (**sidecar** en Tauri | **standalone opcional** para `cloud + web-PWA`).
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
| **IDs de fila** | ✅ **Decidido**: datos del hub (Aurora por-org + SQLite local) con **PK numérica**; **UUID solo en el Cloud Portal** (`hub_id`, org). Migración local→cloud **remapea** IDs (§2.5). |
| **Transporte cloud** | ✅ **Decidido**: HTTP (RPC) + canal de push dedicado (§7.5). WS-only descartado como default. |
| **Canal de eventos (push)** | 🔶 **Abierto**: **WS (actual) vs SSE** para el push servidor→cliente. El push es **unidireccional** (los envíos van por HTTP) ⇒ SSE encaja: da **reconexión + Last-Event-ID gratis** (ayuda con el idle timeout del ALB), mantiene **HTTP estándar** (criterio §7.5) y es el formato natural para el **futuro streaming del assistant**. Plan: implementar **ambos** y elegir por situación; al hacerlo, **unificar la forma del JSON del evento** (`name` server vs `event` cliente — hoy desalineado) entre WS y SSE. |
| **Red saliente de módulos** | ✅ **Decidido (Opción A)**: `http.fetch` mediado (allowlist + creds inyectadas + auditoría §5.5) para terceros; **B (nativo)** para fiscal. |
| **Hardware / Bridge** | ✅ **Decidido**: el `bridge/` **no** se elimina → componente de hardware compartido (sidecar en Tauri \| standalone opcional para `cloud + web-PWA`), §2.7. ✅ **Transporte: solo RED/LAN** (USB/Bluetooth **descartados** por drivers/mantenimiento). Abierto: multi-dispositivo (primary↔satellite). |
| **Modelo de módulos** | ✅ **Decidido**: híbrido (declarativo + WASM + SDK). |
| **Offline/sync** | ✅ **Decidido (Fase 1)**: local offline (SQLite), cloud solo online; sin sync de datos de negocio entre ambos (§2.8). |
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
  ✅ Validado en `apps/web` (Ionic React 8.8 + Vite + TS + Tailwind + react-icons) +
  `modules/inventory` (Lit + ESM + `import()` dinámico): **0 violaciones de CSP de script** en
  Chrome headless contra el build de prod; el CLI `build` verifica CSP-safe en cada compilación.
  ⚠️ **@ionic/react SÍ requiere `style-src 'self' 'unsafe-inline'`** (estilos inline; riesgo bajo).
- **Determinismo y límites de WASM**: fuel/timeouts/memoria + no-determinismo controlados por el host.
- **Regresión de features vs el hub actual**: LiveComponents (resuelto, §7.7), slots,
  hooks/filters, scheduled tasks, i18n (§5.6), pipeline `@action`→AI-tool. Cerrar el hueco es
  multi-fase, no MVP.

---

## Resumen mental

```
module.json = contrato del módulo (lo técnico; la clasificación vive en el Cloud Portal)
WebComponent = pantalla del módulo (Lit; §3.1)
Rust = autoridad / runtime genérico (execute_command / execute_query)
SQLite (local) / Postgres-Aurora (cloud) = solo Rust accede; hub_id (UUID) por fila + PK numérica
WASM (Extism) = lógica avanzada y batch, en sandbox (sin red/BD libres)
SDK TS = puente para la UI (IpcTransport local / HttpWsTransport cloud)
Offline/online = local offline (SQLite) / cloud solo online; sin sync de negocio (Fase 1)
Login = email+password online (setup) → dispositivo de confianza → PIN (offline a futuro)
Reactividad = evento (WS/Tauri) → el WC re-consulta (no server-render)
RAG = solo conocimiento (docs); vector en cloud (pgvector), degradado en local
AI = embeddings + generación SIEMPRE por el proxy del Cloud Portal (medido)
Red de módulos = http.fetch mediado por el host (Opción A) / nativo para fiscal
2 ejes = backend (single/SQLite · cloud/Aurora) × shell (Tauri/hardware · web-PWA); ortogonales (§1)
Impresión/hardware = vía shell Tauri (Bridge como sidecar) o Bridge standalone opcional (web-PWA); §2.7
Primary/Satellite = varios terminales del mismo hub; cobrar/imprimir solo el primario
Migración = gradual, POS-first, manteniendo la agrupación actual de módulos
Cloud Portal (Django) = marketplace + billing + provisioning + proxy AI (no cambia)
hub = el runtime del tenant
```

> ERPlora no instala código backend arbitrario: instala **capacidades declarativas** (y
> WASM en sandbox) que Rust valida, registra y ejecuta. Como WordPress, pero más seguro,
> portable y eficiente — y con el mismo modelo en local y en cloud.
