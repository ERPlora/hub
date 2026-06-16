# Revisión guiada del Hub — paso a paso

Documento vivo para **entender y poder editar** el Hub, revisándolo por subsistemas a lo largo
de varias sesiones. La IA **no escribe el core**: aquí solo se explica, se señala dónde mirar y
se mantiene este `.md`.

## Cómo retomar entre sesiones

1. Invoca el agente **`hub-guide`** y dile algo como *«retomemos la revisión del Hub»*.
2. El agente lee este fichero, mira qué pasos están en `[x]` y te propone el siguiente en `[ ]`.
3. Convención: `[ ]` = pendiente · `[x]` = revisado contigo.
4. Cada paso se redacta con: **Qué es** · **Ficheros clave** (clicables) · **Flujo** (diagrama) ·
   **Dudas / decisiones del humano**.

> Los enlaces son relativos a `hub/`. En VS Code se abren con clic; `#L123` salta a la línea.

---

## Mapa rápido del Hub (orientación)

- **`apps/`** — frontends y shells
  - `web/` — UI Vue 3 + Ionic + OutfitKit (la **misma** UI en Tauri y en web).
  - `tauri/` — shell desktop/Android (embebe el runtime, da hardware).
  - `bridge/` — proceso de hardware standalone (impresoras ESC/POS, cajón).
- **`crates/`** — workspace Rust
  - `server/` — servidor **Axum** (endpoints, auth, install). Es el que embebe Tauri y el que
    corre suelto en ECS.
  - `runtime/` — **dispatcher** genérico (queries/commands) + identidad/sesiones.
  - `db/` — adaptador de BD (`SqliteAdapter`; Postgres a futuro).
  - `cloud-client/` — cliente HTTP del Cloud (firma cabeceras, entitlement, marketplace).
  - `peripherals/` · `vector/` · `installer/` · `wasm-host/` · `sync/` · `verifactu/`.
- **`packages/`** — `outfitkit` (vendor), `module-sdk` (transporte `ErploraTransport`),
  `module-types`.
- **`modules/`** — solo módulos **instalados** en runtime (vacía de source; el source vive en
  `modules-workspace/modules/<id>/` en la raíz del monorepo).

---

## Checklist de subsistemas

1. **[x] Login y sesión local**
2. **[x] Llamadas al Cloud + dónde se guarda el token**
3. **[x] Tauri vs Web server** (diferencias de despliegue)
4. **[ ] Frontend `apps/web`** (shell, transport IPC vs HTTP/WS, módulos en runtime)
5. **[ ] Runtime Rust: dispatcher** (queries/commands declarativos)
6. **[ ] Sistema de módulos** (manifest, install desde marketplace, migraciones)
7. **[ ] Permisos y roles** (role_permissions, gating en cada comando)
8. **[ ] Eventos (outbox transaccional) + scheduled tasks**
9. **[ ] Base de datos** (`SqliteAdapter`, tenancy por `hub_id`)
10. **[ ] cloud-client crate** (entitlement, marketplace, asistente)
11. **[ ] Bridge / peripherals** (impresoras ESC/POS, cajón)
12. **[ ] Build & deploy** (Dockerfile/ECS, packaging Tauri)

---

## Paso 1 — Login y sesión local  `[x]`

### Qué es
- Hay **3 vías de entrada**, excluyentes, en la misma pantalla:
  1. **Email + contraseña** → autentica contra el **Cloud** (devuelve JWT).
  2. **PIN** → identidad **local** del dispositivo (sin Cloud), para el día a día del POS.
  3. **Setup de PIN** → primera vez + casilla «confiar en este dispositivo».
- La **autoridad de identidad es LOCAL**: el runtime valida el JWT del Cloud, pero crea su
  propio `hub_user` y abre una **sesión local** (token opaco). A partir de ahí, todo el POS va
  con esa sesión local, no con el JWT.
- El token de sesión local viaja en cada query/command como cabecera **`X-Hub-Session`**.

### Ficheros clave
- UI (3 pasos `email`/`pin`/`setup`):
  [apps/web/src/views/LoginPage.vue#L386](apps/web/src/views/LoginPage.vue#L386) (`submitEmail`),
  step en [L344](apps/web/src/views/LoginPage.vue#L344), PIN en
  [L498](apps/web/src/views/LoginPage.vue#L498).
- Cliente Cloud + puentes al runtime:
  [apps/web/src/lib/cloud.ts#L355](apps/web/src/lib/cloud.ts#L355) (`cloudLogin`),
  [L217](apps/web/src/lib/cloud.ts#L217) (`runtimeCloudSession`),
  [L222](apps/web/src/lib/cloud.ts#L222) (`runtimePinLogin`),
  [L227](apps/web/src/lib/cloud.ts#L227) (`runtimeSetPin`).
- Sesión local en el navegador:
  [apps/web/src/lib/session.ts#L18](apps/web/src/lib/session.ts#L18) (`erplora.hub_session`).
- Endpoints Rust:
  [crates/server/src/lib.rs#L331](crates/server/src/lib.rs#L331) (rutas),
  [L840](crates/server/src/lib.rs#L840) (`auth_pin`),
  [L876](crates/server/src/lib.rs#L876) (`auth_cloud`),
  [L960](crates/server/src/lib.rs#L960) (`auth_set_pin`),
  [L986](crates/server/src/lib.rs#L986) (`mint_session`).
- Middleware auth: [crates/server/src/auth.rs](crates/server/src/auth.rs).
- Identidad/sesiones SQLite:
  [crates/runtime/src/identity.rs#L25](crates/runtime/src/identity.rs#L25) (tabla `hub_user`),
  [L175](crates/runtime/src/identity.rs#L175) (`verify_pin`, argon2id),
  [L262](crates/runtime/src/identity.rs#L262) (`create_session`),
  [L280](crates/runtime/src/identity.rs#L280) (`resolve_session`),
  [L230](crates/runtime/src/identity.rs#L230) (`get_or_link_cloud_user`).

### Dónde se guarda qué (navegador, `localStorage`)
- `erplora.access` / `erplora.refresh` → **JWT del Cloud** (para billing/marketplace de usuario).
- `erplora.hub_session` → **token de sesión local** (el que importa en el POS; `X-Hub-Session`).
- `erplora.trusted_users` → usuarios que pueden entrar con PIN en este dispositivo.
- Tablas SQLite del runtime: `hub_user`, `hub_session` (TTL 30d), `hub_trusted_device`.

### Flujo
```
LOGIN EMAIL (1ª vez + "confiar")
Browser (LoginPage.vue)
  │ email + password
  ├─ cloudLogin ──────────▶ Cloud  POST /api/v1/auth/login/
  │                         ◀── {access, refresh, user}
  │   setTokens() ▶ localStorage(erplora.access/refresh)
  │
  ├─ runtimeCloudSession ─▶ Hub  POST /api/auth/cloud   (Authorization: Bearer JWT)
  │     runtime: verifica JWT RS256 → get_or_link_cloud_user → create_session
  │                         ◀── {token, user}
  │   setHubSession() ▶ localStorage(erplora.hub_session)
  │
  └─ (si "confiar") setup PIN ─▶ POST /api/auth/set-pin (X-Hub-Session) → set_pin (argon2id)

LOGIN PIN (siguientes veces, mismo dispositivo)
Browser ─ runtimePinLogin ─▶ Hub POST /api/auth/pin {name, pin}
          runtime: verify_pin (argon2id) → create_session ◀── {token, user}

QUERY/COMMAND (ya autenticado)
Browser ─ X-Hub-Session ─▶ Hub /api/query|/api/command
          auth.rs: resolve_session → permisos del rol → ejecuta (hub_id inyectado)
```

### Dudas / decisiones del humano
- (apuntar aquí lo que quieras revisar/cambiar del flujo de login)

---

## Paso 2 — Llamadas al Cloud + dónde se guarda el token  `[x]`

### Qué es
- Hay **dos** credenciales hacia el Cloud, cada una para su plano:
  - **JWT de usuario** (`Authorization: Bearer`) → compras/billing atribuibles a una persona.
    Vive en el **navegador** (localStorage).
  - **`cloud_api_token` = identidad de máquina del hub** (`X-Hub-Token`) → marketplace,
    entitlement, install, asistente, métricas. **Vive SOLO en el runtime Rust**, nunca en el
    navegador.
- Por eso el web **no habla con el Cloud directamente** para lo hub-scoped: pega a **rutas proxy
  del runtime**, y es el runtime quien **re-firma** con el token de máquina.
- Todo lleva además **`X-Hub-Id`**, que lo inyecta el despliegue (no es spoofable por el cliente).

### Ficheros clave
- Token de máquina (celda hot-reload, lectura):
  [crates/server/src/state.rs#L99](crates/server/src/state.rs#L99) (lee env `HUB_CLOUD_API_TOKEN`),
  [L226](crates/server/src/state.rs#L226) (`machine_token()`).
- Firma de cabeceras hacia Cloud:
  [crates/cloud-client/src/lib.rs#L38](crates/cloud-client/src/lib.rs#L38) (`Auth::headers()`),
  variantes en [L41](crates/cloud-client/src/lib.rs#L41) (`X-Hub-Token`),
  [L44](crates/cloud-client/src/lib.rs#L44) (`Bearer`),
  [L47](crates/cloud-client/src/lib.rs#L47) (`X-Webhook-Secret`).
- Rutas proxy del runtime + re-firma:
  [crates/server/src/lib.rs#L479](crates/server/src/lib.rs#L479) (`proxy_cloud_get`),
  [L324](crates/server/src/lib.rs#L324) (`/api/entitlement`),
  [L325](crates/server/src/lib.rs#L325) (`/api/marketplace/catalog`),
  [L322](crates/server/src/lib.rs#L322) (`/api/modules/request-install`),
  [L336](crates/server/src/lib.rs#L336) (`/api/assistant/chat/stream`),
  decisor máquina-vs-JWT en [auth.rs#L118](crates/server/src/auth.rs#L118) (`hub_scoped_auth`).
- JWT de usuario (refresh con reintento en 401):
  [apps/web/src/lib/cloud.ts#L38](apps/web/src/lib/cloud.ts#L38) (`setTokens`),
  [L82](apps/web/src/lib/cloud.ts#L82) (`refreshTokens` → `POST /api/v1/auth/refresh/`).

### Dónde se guarda el token (resumen)
| Token | Para qué | Dónde vive |
|---|---|---|
| `cloud_api_token` (máquina) | marketplace, entitlement, install, asistente | **solo Rust**: env ECS `HUB_CLOUD_API_TOKEN` o enroll en Tauri |
| JWT usuario `access`/`refresh` | compras/billing de la persona | navegador `localStorage` (`erplora.access/refresh`) |
| `hub_session` (sesión local) | autorizar queries/commands del POS | navegador `erplora.hub_session` + tabla `hub_session` |

### Flujo
```
WEB pide algo hub-scoped (ej. catálogo del marketplace)
Browser ─▶ Hub  GET /api/marketplace/catalog       (NO toca el Cloud)
            runtime: hub_scoped_auth() → ¿enrolado? usa X-Hub-Token : usa Bearer JWT
            proxy_cloud_get() ─▶ Cloud GET /api/v1/marketplace/modules/  (X-Hub-Id + X-Hub-Token)
                                 ◀── catálogo
        ◀── catálogo (el token de máquina nunca salió de Rust)

REFRESH del JWT de usuario
authedFetch → 401 → refreshTokens() ─▶ Cloud POST /api/v1/auth/refresh/ {refresh}
                                       ◀── {access, refresh}  (rota ambos; dedup si varias en vuelo)
```

### Dudas / decisiones del humano
- (apuntar aquí)

---

## Paso 3 — Tauri vs Web server  `[x]`

### Qué es
- **El mismo runtime** (`erplora_server::serve()`) corre en los dos sitios. La UI `apps/web` es
  idéntica. Cambian el **empaquetado**, **de dónde salen `hub_id` y el token**, y el **transporte**
  que usa el frontend para hablar con el runtime.
- **Tauri** = app local (1 hub por dispositivo), embebe el server por loopback y **es** el bridge
  de hardware. **Web/ECS** = SaaS (1 contenedor por hub), server Axum suelto que además sirve el
  frontend estático.

### Ficheros clave
- Tauri (shell + runtime embebido):
  [apps/tauri/src-tauri/src/lib.rs#L199](apps/tauri/src-tauri/src/lib.rs#L199) (nota loopback),
  [L220](apps/tauri/src-tauri/src/lib.rs#L220) (`127.0.0.1:8787`),
  [L272](apps/tauri/src-tauri/src/lib.rs#L272) (`erplora_query` → reenvía a `/api/query`),
  [L180](apps/tauri/src-tauri/src/lib.rs#L180) (gate de entitlement),
  [L298](apps/tauri/src-tauri/src/lib.rs#L298) (`device.id`).
- Web server: [crates/server/src/main.rs#L17](crates/server/src/main.rs#L17)
  (`serve(ServeConfig::from_env())`), config en
  [crates/server/src/state.rs](crates/server/src/state.rs), imagen en
  [docker/Dockerfile](docker/Dockerfile).
- Transporte del frontend (mismo interfaz, dos implementaciones):
  `packages/module-sdk/src/index.ts` → `IpcTransport` (Tauri) y `HttpWsTransport` (web).

### Contraste
| Aspecto | **Tauri** | **Web / ECS** |
|---|---|---|
| Proceso runtime | embebido en hilo | Axum standalone (contenedor) |
| Bind | `127.0.0.1:8787` (loopback) | `0.0.0.0:8787` (tras ALB) |
| `hub_id` | fichero local (`hub.id`) | env `HUB_ID` (no spoofable) |
| `cloud_api_token` | keychain/fichero, **hot-reload** | env `HUB_CLOUD_API_TOKEN` (sin hot-reload) |
| SQLite | `app_data_dir/erplora.db` | volumen montado (ej. `/data/erplora.db`) |
| Frontend | webview local | Axum lo sirve estático (`HUB_WEB_DIR=/app/web`) |
| Transporte UI↔runtime | **IPC** (`invoke`) | **HTTP + WebSocket `/ws`** |
| Hardware | la app **es** el bridge | bridge aparte (`:12321`), opcional |
| Entitlement | gate al arrancar (gracia offline 7d) | sin gate (auth = JWT + membresía org) |
| Escala | 1 hub / dispositivo | 1 contenedor / hub |

### Flujo
```
TAURI                                   WEB / ECS
webview (apps/web)                       browser (apps/web servido por Axum)
  │ invoke('erplora_query')                │ fetch POST /api/query  (+ WS /ws para eventos)
  ▼ IPC                                     ▼ HTTP
Tauri lib.rs ─ loopback ─▶ :8787          Axum server :8787 (mismo proceso)
  runtime embebido                          runtime
  token: keychain (hot-reload)              token: env HUB_CLOUD_API_TOKEN
```

### Dudas / decisiones del humano
- (apuntar aquí)

---

## Pasos 4–12 — pendientes

> Esqueleto a rellenar cuando abordemos cada uno (con el agente `hub-guide`):
> **Qué es** · **Ficheros clave** (clicables) · **Flujo** (diagrama) · **Dudas / decisiones**.

- **4. Frontend `apps/web`** — shell, selección de transporte (IPC vs HTTP/WS), carga de módulos.
- **5. Runtime: dispatcher** — cómo se ejecutan queries/commands declarativos.
- **6. Sistema de módulos** — manifest, install desde marketplace, migraciones por dialecto.
- **7. Permisos y roles** — `role_permissions`, gate en cada comando.
- **8. Eventos** — outbox transaccional + scheduled tasks.
- **9. Base de datos** — `SqliteAdapter`, tenancy por `hub_id`.
- **10. cloud-client** — entitlement, marketplace, asistente.
- **11. Bridge / peripherals** — impresoras ESC/POS, cajón.
- **12. Build & deploy** — Dockerfile/ECS, packaging Tauri.
