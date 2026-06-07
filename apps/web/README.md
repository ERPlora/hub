# apps/web

Shell web de hub: **Vite + React + TypeScript + @ionic/react**, **sin Capacitor**
(el runtime nativo es **Tauri**, §1/§3 del doc). Construye el menú desde los `module.json`
de los módulos instalados y **carga sus Web Components (Lit) en runtime** con `import()`
dinámico. Será la UI tanto en cloud (servida por `crates/server`) como en local (Tauri).

## De-risk #1 (riesgo nº1 del doc) — VALIDADO: WC dinámico + Ionic bajo CSP estricta

```sh
# desde la raíz de hub/
pnpm install
pnpm -F @erplora/module-cli build:inventory   # compila el WC del módulo (CSP-safe)
pnpm -F @erplora/web dev                        # Vite dev (http://localhost:5173)
pnpm -F @erplora/web verify                     # build de prod + headless: 0 violaciones CSP
```

- `sync-modules.mjs` copia `modules/*/dist` + `module.json` a `public/modules/` (Vite los
  sirve en `/modules/**`). En producción esto lo hará el runtime (crates/server), no el shell.
- `verify` prueba el **build de producción** servido con CSP estricta (no `vite dev`, que usa
  HMR con inline/eval). Confirma que Ionic + el WC Lit cargado dinámicamente cumplen
  `script-src 'self'; style-src 'self'` sin `unsafe-inline`/`unsafe-eval`.
- Requiere Google Chrome instalado (para `verify`).

> Decisiones: **TypeScript en todo**; **Vite + @ionic/react sin Capacitor** (§14 del doc).
