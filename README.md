# hub-next

Próxima generación del Hub de ERPlora: **Ionic React + Rust/Axum + Tauri + módulos
declarativos (`module.json`) + WASM + SDK**, SQLite (local) / Postgres-Aurora (cloud).
Reemplazará progresivamente al Hub actual (`../hub`).

> 📖 Diseño completo y decisiones: **[ARQUITECTURA.md](ARQUITECTURA.md)**.
> Guía para Claude: [CLAUDE.md](CLAUDE.md).

## Estado

Lo que **ya funciona** (validado en Chrome headless; sin Rust todavía):

- **App web navegable** ([apps/web](apps/web)): **Ionic React 8.8 + Vite + TS + Tailwind v4
  + react-icons** (componentes Ionic reales, **sin Capacitor**), tematizada a la marca por
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
  web/           Ionic React 8.8 + Vite + TS + Tailwind + react-icons (13 vistas)    [real]
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
pnpm -F @erplora/module-cli build:inventory   # compila el WC del módulo a ESM (CSP-safe)
pnpm -F @erplora/web dev                        # Vite dev (http://localhost:5173)
pnpm -F @erplora/web snapshot                   # build prod + headless: snapshots + verifica CSP
pnpm -F @erplora/web typecheck                  # TS estricto
```

## Decisiones fijadas (ver §14–15 del doc)

- **TypeScript** en todo · **Ionic React 8.8 + Tailwind + react-icons** (sin Capacitor; nativo = Tauri).
- **Lit** para los Web Components de módulos · **pnpm** + Cargo workspaces (raíz compartida).
- **Dos ejes ortogonales** (§1): backend `single` (SQLite) / `cloud` (Aurora) × shell `tauri` / `web-pwa`.
- Transporte de datos **HTTP (RPC) + WS (eventos)** con backend cloud / **IPC** con backend single.
- Multi-tenant **`hub_id` por fila**, BD por organización. Hardware vía **shell Tauri** (Bridge como sidecar) o **Bridge standalone opcional** para `cloud + web-PWA` (§2.7).
- Red de módulos: **`http.fetch` mediado** (Opción A). Migración **POS-first**, gradual.
- Auth: email (1er login) → dispositivo de confianza → PIN; usuarios cloud y solo-locales.
