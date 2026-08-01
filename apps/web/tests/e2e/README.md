# E2E web

La suite usa Vite y un runtime Axum reales; no intercepta ni simula `/api`.

Los casos generales esperan el runtime en `HUB_RUNTIME_URL` (por defecto `:8787`) y Vite en
`HUB_WEB_URL` (por defecto `:5173`). `ModuleRuntimeContracts.spec.ts` es una suite de integración
ampliada: se habilita con `HUB_RUNTIME_CONTRACT_E2E=1` y requiere arrancar el runtime en modo dev
con un `HUB_MODULES_DIR` que contenga:

- `schedules`, compilado con su handler WASM;
- `w140`, enlace al fixture `crates/runtime/tests/fixture_w140`.

Así el flujo ejercitado es navegador → SDK → HTTP → runtime → WASM/SQL → Postgres. Sin la variable,
esos casos se omiten para que la suite normal siga representando un hub vacío.
