# hub

Próxima generación del Hub de ERPlora: **Vue 3 + Ionic + Rust/Axum + Tauri + módulos
declarativos (`module.json`) + WASM + SDK**, SQLite (local) / Postgres-Aurora (cloud).
Reemplazará progresivamente al Hub actual (`../hub`).

> 📖 Diseño completo y decisiones: **[ARQUITECTURA.md](ARQUITECTURA.md)**.
> Guía para Claude: [CLAUDE.md](CLAUDE.md).

## Estado

Lo que **ya funciona** (validado en Chrome headless; sin Rust todavía):

- **App web navegable** ([apps/web](apps/web)): **Vue 3 + Ionic (`@ionic/vue` 8.8) + vue-router
  + Vite + TS + Tailwind v4 + Iconify (`unplugin-icons`)** (componentes Ionic reales, **sin
  Capacitor**), tematizada a la marca por
  variables `--ion-*` (brand `#1496d6`, crema, dark por `.ion-palette-dark`). **13 pantallas**:
  login (email/**PIN**/setup), dashboard, empleados (+ alta/edición), roles y permisos,
  billing, marketplace, ajustes, sistema, **vista de módulo (WC Lit en runtime)** y
  **asistente AI** (drawer). Tema claro/oscuro. **0 violaciones de CSP de script**. Capturas
  en `apps/web/snapshots/`.
- **AUTH** ([apps/web/src/pages/auth](apps/web/src/pages/auth) + `src/lib/auth.tsx`):
  email+password (1er login) → dispositivo de confianza → PIN + setup. Degrada a modo demo
  si el Cloud no es accesible.
- **Piezas propias mínimas** ([apps/web/src/ui](apps/web/src/ui)): `Logo` (SVG inline) y
  `PinPad` — lo único que Ionic no trae. El resto es **Ionic + Tailwind**.
  (`packages/ui` queda solo como **ejemplo**, no es dependencia.)
- **CLI de módulos** ([packages/module-cli](packages/module-cli)): `build`/`validate`
  (compila el WC a ESM y verifica CSP-safe).
- **Contrato** ([schemas/](schemas)): `module.schema.json` + `envelope.schema.json`.

- **Runtime Rust** ([crates/runtime](crates/runtime) + [crates/db](crates/db)): host genérico
  (manifest → migraciones → queries/commands/eventos con scope `hub_id`) + adaptador SQLite.
  Módulo [modules/inventory](modules/inventory) con SQL real + ejemplo `walking_skeleton` y tests.
  ⚠️ **Code-complete pero sin compilar** (no hay toolchain de Rust en el entorno; el sandbox
  bloquea rustup). Ver [crates/README.md](crates/README.md).

**Stub** (requieren toolchain de Rust o trabajo posterior): `apps/tauri`, `crates/{vector,
source,cloud-client,guest-sdk,wasm-host,server,sync}`, WASM.

## Estructura

```
apps/
  web/           Vue 3 + Ionic 8.8 + Vite + TS + Tailwind + Iconify (13 vistas)       [real]
  tauri/         empaquetado desktop/móvil                                          [stub]
packages/
  ui/            (ejemplo, NO usado por apps/web) componentes React+Tailwind         [ejemplo]
  module-cli/    erplora module build|validate                                       [real]
  module-sdk/    SDK TS frontend (transport IPC/HTTP+WS)                             [interfaz]
  module-types/  tipos del contrato (manifest/envelope)                             [parcial]
modules/
  inventory/     módulo de ejemplo (manifest + WC Lit)                              [real]
crates/          runtime Rust (host genérico) y soporte                            [stub]
schemas/         contrato compartido                                               [real]
docker/          Dockerfile.planned                                                [stub]
```

## Requisitos

- **Node 20+** (hay Node 24) + **pnpm 10+** (`corepack enable pnpm`).
- **Google Chrome** para `snapshot`/`verify` (headless).
- **Rust** (aún no instalado) para `crates/*` y `apps/tauri`.

> El registry npm del repo es el público (`.npmrc`); el `~/.npmrc` global apunta a un
> CodeArtifact privado de otro proyecto.

## Arranque rápido

```sh
pnpm install
pnpm build:modules                              # compila los WC de los módulos a ESM (CSP-safe)
pnpm dev                                         # ⭐ turnkey: runtime (Axum :8787) + web (Vite :5173)
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
| `HUB_SQLITE_PATH` | `/tmp/erplora-hub-dev.db` | BD local efímera (bórrala para empezar de cero) |
| `HUB_MODULES_DIR` | `../modules-workspace/modules` | Fuente de módulos de dev (los mismos que el shell carga como WC) |
| `HUB_BIND` | `127.0.0.1:8787` | Bind del runtime Axum |
| `VITE_RUNTIME_URL` | `''` (proxy de Vite) | Cómo el shell alcanza el runtime |

Atajos para arrancar solo una mitad: `pnpm dev:web` (Vite) · `pnpm dev:runtime` (Axum).

```sh
pnpm -F @erplora/web snapshot                   # build prod + headless: snapshots + verifica CSP
pnpm -F @erplora/web typecheck                  # TS estricto
```

## Decisiones fijadas (ver §14–15 del doc)

- **TypeScript** en todo · **Vue 3 + Ionic 8.8 + Tailwind + Iconify** (sin Capacitor; nativo = Tauri).
- **Lit** para los Web Components de módulos · **pnpm** + Cargo workspaces (raíz compartida).
- **Dos productos** (§1; ADR-0080): **Local** (backend `single`/SQLite + shell `tauri`) y **Hub PWA** (backend `cloud`/Aurora + shell `web-pwa`). `single ⟺ Local/Tauri`, `cloud ⟺ Hub PWA`.
- Transporte de datos **HTTP (RPC) + WS (eventos)** en **Hub PWA** (`cloud`) / **IPC** en **Local** (`single`).
- Multi-tenant **`hub_id` por fila**, BD por organización. Hardware vía **shell Tauri** (Bridge como sidecar) en **Local**, o **Bridge standalone opcional** en **Hub PWA** (§2.7).
- Red de módulos: **`http.fetch` mediado** (Opción A). Migración **POS-first**, gradual.
- Auth: email (1er login) → dispositivo de confianza → PIN; usuarios cloud y solo-locales.
