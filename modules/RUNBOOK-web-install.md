# Runbook — flujo de instalación web de un módulo hub-next (repo → Cloud → S3 → Hub)

Para publicar un módulo nuevo (`module-<id>`) y que un hub lo instale en runtime.
**Acciones marcadas (TÚ)** requieren acceso que el asistente no tiene (GitHub org, Aurora, deploy).

## Prerrequisito único (una vez): desplegar el soporte de `module.json` al Cloud
El Cloud ya tiene el código (esta sesión): `parse_module_json` + campo `manifest_kind`,
busca `module.json` antes que `module.py`. Falta aplicarlo a producción:

1. **(TÚ)** Desplegar `cloud/` a prod (incluye `apps/public/modules/migrations/0021_module_manifest_kind.py`
   y los cambios en `apps/dashboard/commerce/catalog/modules/repository/services.py`).
2. **(TÚ)** Correr la migración en Aurora: `python manage.py migrate public_modules`.
   Sin esto, el campo `manifest_kind` no existe en la BD y el import falla.

## Por cada módulo (ej. inventory)

### 1. Empaquetar el repo (el asistente puede dejarlo listo en /tmp)
El repo = la carpeta `hub-next/modules/<id>/` tal cual: `module.json` en la raíz +
`migrations/`, `queries/`, `commands/`, `schemas/`, `dist/` (WC `.esm.js` + `handler.wasm`).
El `handler/` (fuente Rust del WASM) se incluye para reproducibilidad pero no es necesario en runtime.

```bash
# Construir artefactos antes de empaquetar:
cd hub-next
node packages/module-stencil/build-all.mjs <id>     # → dist/<id>.esm.js
(cd modules/<id>/handler && cargo build --target wasm32-unknown-unknown --release --features guest \
   && cp target/wasm32-unknown-unknown/release/*_handler.wasm ../dist/handler.wasm)
```

### 2. **(TÚ)** Crear el repo en el org y empujar
```bash
gh repo create ERPlora/module-<id> --private
cd /tmp/erplora-repos/module-<id>   # (carpeta que deja el asistente)
git init && git add -A && git commit -m "feat: <id> module (hub-next)"
git remote add origin git@github.com:ERPlora/module-<id>.git
git branch -M main && git push -u origin main
```
> Convención: repo `module-<id>`; el `module_id` interno queda limpio (`<id>`).

### 3. **(TÚ)** Importar al marketplace (Developer API del Cloud)
```bash
curl -X POST https://erplora.com/api/v1/developer/repos/import/ \
  -H "Authorization: Bearer <tu-jwt>" -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/ERPlora/module-<id>", "branch": "main"}'
```
El sync detecta `module.json` → `manifest_kind=declarative`, descarga el zip, lo sube a
S3 (`modules/<id>/v<version>.zip`, inmutable) con su SHA256, crea `Module` + `ModuleVersion`.
La clasificación (sectores/pricing) se edita en el vendor portal, no en `module.json`.

### 4. Instalar en un Hub (runtime)
El hub descarga el zip de S3, verifica SHA256, valida manifest, ordena `depends_on`,
aplica migraciones, registra capacidades y lo activa (`hub_module`). Hoy el runtime Rust
expone `POST /api/modules/install {dir}` (carpeta ya extraída); el puente download+verify
desde el marketplace lo hace `erplora-source` + `erplora-installer`.

> **Orden de deps**: instalar primero las dependencias. Para sales: inventory + customers.

## Borrado de los `m_*` legacy (cuando todo esté migrado) — **(TÚ), irreversible**
Hacer backup del `Module` table + `aws s3 sync modules/ backups/` antes. Borrar la entrada
del marketplace + los zips S3 rompe el SHA256 de cualquier hub que aún los referencie.
