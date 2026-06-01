# Demo: hot-plug de módulos (instalar / activar / desactivar / desinstalar)

Prueba el **ciclo de vida de módulos** del runtime Rust real, tal como se verá en el
dashboard ("Mis módulos"). La imagen del hub **no trae módulos horneados** (§sistema de
módulos): se instalan en caliente.

## Qué demuestra
1. Server arranca **sin módulos** (`/api/modules` → `[]`).
2. Se **instalan en caliente** `inventory` y `notes` (POST `/api/modules/install`).
3. El **menú** (`/api/navigation`) ahora incluye ambos → aparecen en el dashboard.
4. **Desactivar** `notes` → desaparece del menú y sus queries/commands dan 404 (sus datos
   permanecen en BD).
5. **Reactivar** → vuelve a estar disponible.

## Correrlo

```sh
# prueba por HTTP (rápida, sin navegador):
HUB_SQLITE_PATH=/tmp/hub.db HUB_BIND=127.0.0.1:8801 cargo run -p erplora-server &
curl -s localhost:8801/api/modules
curl -s -X POST localhost:8801/api/modules/install -H 'content-type: application/json' -d '{"dir":"modules/notes"}'
curl -s localhost:8801/api/navigation
curl -s -X POST localhost:8801/api/modules/notes/deactivate
curl -s localhost:8801/api/navigation     # notes ya no aparece

# demo visual (grid de módulos + screenshots, requiere Chrome):
node demos/hotplug/run.mjs                 # → demos/hotplug/snapshots/*.png
```

`run.mjs` arranca el server Rust, instala los 2 módulos, sirve `index.html` (proxy `/api`
al server, mismo origen) y captura el grid en 2 estados (todo activo / notes desactivado).

> Es un demo del **runtime**; en producción este grid es la vista "Mis módulos" de `apps/web`
> hablando con `crates/server`. El módulo de ejemplo `notes` vive en `../../modules/notes/`.
