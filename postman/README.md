# Postman — la API del runtime del hub, generada (hub#1613)

> **No se edita a mano.** `erplora-hub.postman_collection.json` la genera un test desde
> `contracts/kernel/routes.snapshot` (la superficie congelada del kernel) más `overlay.json`, y sin la
> variable de actualización ese mismo test exige que la commiteada sea **byte-idéntica**. Si cambia una
> ruta y nadie regenera, el build se pone rojo.

```bash
UPDATE_POSTMAN_COLLECTION=1 cargo test -p erplora-server --test postman_collection_hub1613   # regenera
cargo test -p erplora-server --test postman_collection_hub1613                               # el gate
```

| Fichero | Qué es |
|---|---|
| `erplora-hub.postman_collection.json` | Las rutas del core (`{slug}.a.erplora.com`, **169** el 2026-09-16 — cuenta con `contracts/kernel/routes.snapshot`, que drifta con cada PR), con la credencial que pide cada clase de auth del snapshot: `X-Hub-Session` (session/admin/any-credential), `Authorization: Bearer erpl_live_…` (api-key), nada (none) |
| `overlay.json` | Lo que el snapshot no lleva, por `MÉTODO ruta`: nombre, descripción, cuerpo de ejemplo, cabeceras extra y el script `test` que guarda variables. Solo puede nombrar rutas que existen — una entrada huérfana rompe el test. Ampliar la colección es editar este JSON, no Rust |

**Empieza aquí** (primera carpeta): `GET /api/hub/context` → `POST /api/auth/cloud` con el JWT del
SaaS (`{{access_token}}`, el que guarda la colección del SaaS al hacer Login) → guarda `hub_session`
sola → `POST /api/auth/set-pin` (6 dígitos) → `POST /api/auth/pin` (con `device_id`: el gate de
device-trust rechaza un login que no identifica su dispositivo) → `POST /api/keys` → guarda
`hub_api_key` sola → `GET /api/v1/openapi.json`.

**Los módulos no están aquí.** Su API (`/api/v1/{module}/q|c/…`) es por hub y dinámica (ADR-0057):
instalar un módulo la amplía. Importa en Postman la respuesta de `GET /api/v1/openapi.json` de ESE
hub (con el ajuste `api_docs_enabled` encendido) y usa `Authorization: Bearer {{hub_api_key}}`.

`hub_url` apunta al **banco permanente de PRE** (`banco-pre`). El entorno, la receta de recreación
y las tres credenciales del SaaS: `saas/postman/README.md`. Esta colección **no** es superficie de
contrato: vive fuera de `contracts/kernel/` y regenerarla no es un cambio de contrato.
