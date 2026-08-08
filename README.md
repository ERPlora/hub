# hub

El Hub de ERPlora: **Vue 3 + Ionic + Rust/Axum + módulos
declarativos (`module.json`) + WASM + SDK**. **Hub Cloud**: PWA/web shell + runtime Axum +
**una BD Postgres por hub** (ADR-0201; los hubs pre-0201 siguen en la BD de su org hasta migrar);
el hardware lo da **la app instalable** (escritorio/Android/iOS — ADR-0196).

> 📖 Diseño completo y decisiones: **[ARQUITECTURA.md](ARQUITECTURA.md)**.
> Guía para Claude: [CLAUDE.md](CLAUDE.md).
> Patrones aprobados y regresión: [UI_UX_QA_GUIDE.md](UI_UX_QA_GUIDE.md).

## Estado

Lo que **ya funciona** (validado en Chrome headless; el workspace Rust compila y pasa tests —
ver más abajo):

- **App web navegable** ([apps/web](apps/web)): **Vue 3 + Ionic (`@ionic/vue` 8.8) + vue-router
  + Vite + TS + Tailwind v4 + Iconify (`unplugin-icons`)** (componentes Ionic reales, **sin
  Capacitor**), tematizada a la marca por
  variables `--ion-*` (brand `#1496d6`, crema, dark por `.ion-palette-dark`). **14 vistas / 16
  rutas** ([apps/web/src/router/index.ts](apps/web/src/router/index.ts)): login
  (email/**PIN**/setup), dashboard, empleados (+ alta/edición), billing, **/apps** (tienda de
  módulos; `/marketplace` es solo un redirect de compat), archivos (`/files`), perfil
  (`/profile`), doc de la API (`/api-docs`), activación (`/activation`), ajustes, sistema y la
  **vista de módulo (WC Lit en runtime)**. Paneles/pestañas que **no** son vistas propias:
  **roles y permisos** (pestaña `#permisos` de empleados) y el **asistente AI**
  (`components/AssistantDrawer.vue`, panel paralelo en escritorio/tablet y superpuesto en
  móvil). Tema claro/oscuro. CSP estricta validada históricamente (§14); hoy los gates vivos
  son vitest + 4 specs Playwright (`apps/web/tests/e2e/`).
- **AUTH** ([apps/web/src/views/LoginPage.vue](apps/web/src/views/LoginPage.vue) + `src/lib/session.ts`):
  email (1er login) → dispositivo de confianza (enforce, sin bypass — hub#330) → PIN con
  rate-limit (hub#329); fallback demo SOLO bajo `VITE_DEMO=1`
  (`apps/web/src/lib/config.ts`).
- **Piezas propias mínimas**: logo (imagen inline con fallback al logo local de ERPlora) y el
  PIN vía `ok-pinpad` (OutfitKit) — lo único que Ionic no trae. El resto es **Ionic + Tailwind**.
- **CLI de módulos**: el CLI vivo es **`@erplora/module-toolkit`** (`erplora
  build/dev/validate/pack/sign/publish`), desarrollado en `module-toolkit/` en la raíz del
  monorepo. El antiguo [packages/module-cli](packages/module-cli) está **deprecado**
  (ver su `DEPRECATED.md`).
- **Contrato** ([schemas/](schemas)): `module.schema.json` + `envelope.schema.json`.

- **Runtime Rust** ([crates/runtime](crates/runtime) + [crates/db](crates/db)): host genérico
  (manifest → migraciones → queries/commands/eventos con scope `hub_id`) + adaptador PostgreSQL
  (`PgAdapter`). Módulos de ejemplo viven hoy en `modules-workspace/modules/` (fuente), no en
  `hub/modules/`. **Compila y pasa tests**: `cargo check --workspace` en verde y
  `cargo test --workspace` corre cientos de tests en las crates + `apps/tauri/src-tauri`, contra un
  **Postgres real** (schema efímero por test vía `erplora_db::testutil`; CI con service container
  `postgres:18`). Ver [crates/README.md](crates/README.md) y
  [REPASO-MOTOR-RUST.md](REPASO-MOTOR-RUST.md).

## Estructura

```
apps/
  web/           Vue 3 + Ionic 8.8 + Vite + TS + Tailwind + Iconify (14 vistas)       [real]
  tauri/         app instalable com.erplora.app (escritorio/Android/iOS): la misma
                 web + hardware por invoke in-process (ADR-0196/0180)                [real]
  bridge/        Bridge standalone (red-only): hardware POS por localhost HTTP/WS     [en retirada, ADR-0196]
packages/
  module-cli/    erplora module build|validate                                       [deprecado, ver DEPRECATED.md — usa @erplora/module-toolkit]
  module-sdk/    SDK TS frontend (HttpWsTransport contra el runtime Axum)            [interfaz]
  module-types/  tipos del contrato (manifest/envelope)                             [parcial]
modules/         módulos instalados en runtime (vacío de source; el source vive en
                 modules-workspace/modules/ en la raíz del monorepo)
crates/          runtime Rust (host genérico) y soporte, 13 crates                  [real, compila y pasa tests]
schemas/         contrato compartido                                               [real]
docker/          Dockerfile (multi-stage: frontend Vite → builder Rust →
                 debian-slim con erplora-server)                                   [real] imagen del runtime del tenant
```

## Requisitos

- **Node 20+** (hay Node 24) + **pnpm 10+** (`corepack enable pnpm`).
- **Playwright** (specs e2e en `apps/web/tests/e2e/`) y **vitest** para el web.
- **Rust** para `crates/*` y `apps/tauri/src-tauri` (`cargo check --workspace` /
  `cargo test --workspace`).
- **PostgreSQL** (los tests corren contra un Postgres real; en CI, service container `postgres:18`).

> El registry npm del repo es el público (`.npmrc`); el `~/.npmrc` global apunta a un
> CodeArtifact privado de otro proyecto.

## Arranque rápido

```sh
pnpm install
pnpm dev                                         # ⭐ turnkey: runtime (Axum :8787) + web (Vite :5173)
                                                  # (apps/web/sync-modules.mjs copia los WC ya
                                                  # compilados desde modules-workspace/modules/*/dist/
                                                  # vía hooks predev/prebuild; ya no hay `pnpm build:modules`)
```

### Arranque turnkey (`pnpm dev`) — runtime + web de un comando

`pnpm dev` (orquestador [scripts/dev.mjs](scripts/dev.mjs), sin dependencias npm extra) levanta
**a la vez**:

- el **runtime** Rust (`cargo run -p erplora-server`) en `http://127.0.0.1:8787` (API + WS), que
  instala al arrancar los módulos de `HUB_MODULES_DIR` (topo-orden por `depends_on`), y
- el **shell web** (`pnpm -F @erplora/web dev`) en `http://localhost:5173`. El shell pega al runtime
  por el proxy de Vite (`/api` + `/ws` → :8787; ver [apps/web/vite.config.ts](apps/web/vite.config.ts)),
  así que no hay CORS ni cableado manual.

Ctrl-C (o que uno de los dos muera) baja a ambos. La salida va prefijada `[runtime]` / `[web]`.

**Defaults de entorno** (todos sobreescribibles exportando la variable antes de invocar):

| Variable | Default | Qué es |
| --- | --- | --- |
| `HUB_DATABASE_URL` | — (**requerido**) | DSN de Postgres (`postgres://…`); el runtime **falla duro** sin él |
| `HUB_MODULES_DIR` | `../modules-workspace/modules` | Fuente de módulos de dev (los mismos que el shell carga como WC). **Solo se escanea con `HUB_DEV_MODE`** |
| `HUB_DEV_MODE` | `1` (solo en `pnpm dev`) | **Modo desarrollo explícito** (hub#239): habilita las vías de carga de código LOCAL — escaneo de `HUB_MODULES_DIR` al arrancar y `POST /api/modules/install {dir}` (confinado al staging). El provisioning **nunca** lo inyecta: en producción esas vías están apagadas y los módulos vienen del marketplace con su SHA256 verificado (ADR-0015) |
| `HUB_BIND` | `127.0.0.1:8787` | Bind del runtime Axum |
| `VITE_RUNTIME_URL` | `''` (proxy de Vite) | Cómo el shell alcanza el runtime |

Atajos para arrancar solo una mitad: `pnpm dev:web` (Vite) · `pnpm dev:runtime` (Axum).

```sh
pnpm -F @erplora/web test                       # vitest (unit/componentes)
pnpm -F @erplora/web exec playwright test -c tests/playwright.config.ts   # 4 specs e2e
pnpm -F @erplora/web typecheck                  # TS estricto
```

## Decisiones fijadas (ver §14–15 del doc)

- **TypeScript** en todo · **Vue 3 + Ionic 8.8 + Tailwind + Iconify** (sin Capacitor).
- **Lit** para los Web Components de módulos · **pnpm** + Cargo workspaces (raíz compartida).
- **Un solo Hub** (§1; ADR-0154): **Hub Cloud** — PWA/web shell + **PostgreSQL por hub** (ADR-0201; migración en curso). Se retiró Hub Local (Tauri) y el backend SQLite; ya no hay ejes `single`/`cloud`.
- Transporte de datos **HTTP (RPC) + WS (eventos)** contra el runtime Axum (ADR-0050; no hay `invoke`/IPC para datos).
- Multi-tenant **`hub_id` por fila**, **una BD por hub** (ADR-0201). Hardware por la **app instalable** vía `invoke` in-process (ADR-0196); cola de impresión en el hub (§6); en Android vuelve el Bluetooth SPP (ADR-0204, pendiente hub#388).
- Red de módulos: **`http.fetch` mediado** (Opción A). Migración **POS-first**, gradual.
- Auth: email (1er login) → dispositivo de confianza (enforce, sin bypass — hub#330) → PIN con rate-limit (hub#329); usuarios cloud y solo-locales.
