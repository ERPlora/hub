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

## Receta autónoma: contratos del runtime

Desde la raíz de `hub`:

```bash
pnpm test:e2e:runtime-contracts
```

La receta crea un Postgres efímero en Docker, construye y arranca Axum, arranca Vite, espera ambos
servicios, ejecuta únicamente `ModuleRuntimeContracts.spec.ts` en Chromium y limpia procesos,
contenedor y fixtures aunque falle. Reserva puertos locales dedicados, por lo que puede convivir con
otros worktrees. No depende de un Hub ya levantado ni reutiliza su base de datos.

La autenticación de prueba es deliberada y visible: Axum arranca con `HUB_AUTH=dev` y el spec manda
siempre el UUID de Hub de desarrollo, `X-User-Id: playwright` y `X-Permissions: *`. Nunca se usa
esta receta para producción ni se obtiene una sesión real. Para probar contra un Postgres dedicado
ya existente se puede fijar `HUB_RUNTIME_CONTRACT_DATABASE_URL`; esa base debe ser vacía y exclusiva
del test.

Mientras el commit de `schedules` esté en un worktree antes de integrarse, se puede seleccionarlo
sin alterar el workspace principal:

```bash
ERPLORA_SCHEDULES_MODULE_DIR=/ruta/al/worktree/schedules pnpm test:e2e:runtime-contracts
```
