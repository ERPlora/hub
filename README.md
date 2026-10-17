# hub-next

## Desarrollo local

```bash
git submodule update --init          # packages/live y packages/ui (ERPlora/live, ERPlora/ui)
printf 'DEBUG=True\n' > .env         # sin DEBUG, el hub arranca como producción
uv sync && pnpm install
uv run python manage.py migrate && uv run python manage.py seed_local_hubs   # deja `a` y `b` en el registro
uv run python manage.py runserver    # Django en a.localhost:8000 y Vite (`pnpm run dev`)
uv run pytest -q                     # Postgres de compose.yaml (`docker compose up -d`)
```

`DEBUG` está apagado si no se define: sin `DEBUG=True` en `.env` (o en el entorno), los ajustes
exigen `SECRET_KEY`, `SAAS_URL` e `INTERNAL_SHARED_SECRET`, como en producción. Con `DEBUG=True`
el resto de variables toma los valores locales por defecto (lista completa en el `.env.example` de
erplora-next). `.env` nunca se sube al repo.

`runserver` arranca Vite en el `VITE_DEV_PORT` que lee Django, del entorno o del `.env` (por defecto `5173`):
a un segundo checkout le basta `VITE_DEV_PORT=5203` en su `.env`. `pnpm run dev` o la e2e sueltos solo la leen
del entorno, y `uv run pytest` sigue en el `5173` aunque la defina (`config/settings_pytest.py`).

## Registro de hubs y `/internal`

El Hub sirve solo los hubs de su registro (`base.Hub`, plan `docs/plans/2026-10-17-demo-hubs-fase-1.md` de
erplora-next): `HubHostRequiredMiddleware` busca la fila del slug del `Host` y responde **404** si no hay fila,
**410** si el hub terminó (cancelado, purgado o una demo pasada su `expires_at`; página con la vuelta a ERPlora) y
**503** con `Retry-After` si aún se prepara. La API, y toda llamada que no pide una página, recibe el sobre
(`base.hub_gone`, `base.hub_preparing`). En local, `seed_local_hubs` (solo con `DEBUG`, idempotente) deja `a` y `b`;
en los tests, la fixture autouse `local_hubs` de `conftest.py` hace lo mismo en todo test con BD (un test sin BD que
pide la página de un hub necesita `django_db`).

Lo escribe el SaaS por `/internal` (`base/internal.py`), firmado con HMAC v1 + v2 y dos secretos
(`base/signing.py`, el mismo esquema que `accounts/signing.py` del SaaS); cada ruta es una operación de `base`:

| Ruta | Operación | Respuesta |
|---|---|---|
| `PUT /internal/hubs/{id}` | `base.hub.register` | 202 si lo crea (listo al momento en la fase 1; el SaaS recibe `POST /internal/hubs/{id}/ready` tras el COMMIT), 200 si lo actualiza; 422 `base.slug_invalid`, 409 `base.slug_taken`, `base.hub_cancelled`, `hub_purged` |
| `GET /internal/hubs/{id}` | `base.hub.get` | la fila (`status: "ready"` es lo que espera el SaaS); 404 |
| `DELETE /internal/hubs/{id}` | `base.hub.cancel` | 202 `cancelled`; 404; 409 `hub_purged` |
| `POST /internal/hubs/{id}/restore` | `base.hub.restore` | 200 `ready`; 404; 409 `hub_purged` |
| `PUT /internal/hubs/{id}/state` | `base.hub.state_apply` | 200 `{applied, version}`: guarda la foto si su versión es mayor y aplica el bloque VeriFactu y el estado del negocio; 404 |

Sin firma válida, 401 `internal.unsigned`; un cuerpo que nombra otro hub que el de la ruta, 422
`internal.hub_mismatch`. `/internal` responde en cualquier host (el SaaS entra por `hub.erplora.internal`; el ALB
no lo publica).

## Demo

Una demo es un hub **vacío** del propio Hub (`demo-<8 hex>`, fila `is_demo` de `base.Hub`) que pide el `/demo/` del
SaaS, sin cuenta ni tarjeta, durante `DEMO_TTL_MINUTES` (60). En la fase 1 no tiene BD propia: sus datos comparten
las tablas de las apps con las demás demos y con `a`/`b` (limitación aceptada; plan
`docs/plans/2026-10-17-demo-hubs-fase-1.md`, §1.6 y §1.7).

| Ruta | Operación | Respuesta |
|---|---|---|
| `POST /internal/demos` `{session_key, vertical, language}` | `base.demo.create` | 201 `{id, slug, expires_at, created: true}`; 200 con la demo viva de ese navegador (`created: false`); 503 `base.demo_full` + `Retry-After: 60` con `MAX_CONCURRENT_DEMOS` (50) vivas; 422 `internal.payload_invalid` |
| `POST /internal/demos/{slug}/codes` `{session_key, language}` | `base.demo.code_create` | 201 `{code, expires_at}` (un uso, 60 s, solo se guarda su sha256); 404; 410 `base.hub_gone`; 403 `base.demo_not_owner` |

`session_key` es el sha256 (hex) de un token aleatorio de la sesión del navegador en el SaaS: una demo viva por
navegador. Entrada: el SaaS salta a `/auth/login?next=/` de la demo, que (como un negocio, con la cookie
`hub_login_state`) vuelve a `{SAAS_URL}/demo/enter/?hub=<slug>&next=<next>&state=<state>`; el SaaS pide el código y
lo envía en un formulario a `/auth/callback`, que lo canjea **en local** (sin llamar al SaaS) y abre la sesión de
`demo:<slug>` («Demo», `hub_owner`, nunca staff). Un código gastado, caducado o de otra demo vuelve a
`{SAAS_URL}/demo/?state=failed`; salir de la demo, a `{SAAS_URL}/demo/`. `GET /api/me` lleva `demo: {expires_at}`
(`null` en un negocio).

Caducidad: desde `expires_at` el host responde **410** («This demo has ended», con enlace a `/demo/` del SaaS). El
worker la purga en ≤ 60 s (`reap_demos`, `base.demo.purge`: borra sus códigos, su `Membership` y el usuario
`demo:<slug>`; `purge_demo_data` no borra nada en la fase 1 y en la fase 2 hará el `DROP DATABASE`) y la fila queda
`purged` como lápida `DEMO_TOMBSTONE_DAYS` (7) días; después, 404. Para terminar una demo a mano: la acción «Expire
now» del admin (`hubs.localhost:8000/admin/base/hub/`, solo superusuarios) o, en cualquier entorno:

```bash
uv run python manage.py demo_expire demo-1a2b3c4d   # base.demo.expire + una pasada del reaper → «demo-1a2b3c4d: purged»
```

Probarla en local, con el SaaS en `:8001` (su `HUB_INTERNAL_URL` por defecto apunta a `http://localhost:8000` y el
secreto local `local-internal-shared-secret` es el mismo en los dos):

```bash
uv run python manage.py runserver                 # Hub en :8000 (con `migrate` y `seed_local_hubs` hechos)
(cd ../saas && uv run python manage.py runserver 127.0.0.1:8001)
# http://localhost:8001/demo/ → «Try the demo» → http://demo-<hex>.localhost:8000/ con la sesión «Demo»
uv run python manage.py demo_expire demo-<hex>    # el host pasa a 410 y /demo/ del SaaS a «expired»
```

## Despliegue: `main` → prod, `pre` → pre

`pre` es la preproducción del equipo (`hubs.pre.erplora.com`, `<slug>.pre.erplora.com`): misma Aurora
que prod, con su propio clúster de ECS (`erplora-pre`; prod corre en `erplora-prod`), sus propios
servicios (`hub-pre`, `worker-pre`), BD `pre_*` y repositorio de ECR (`erplora/hub-pre`). Se apaga
sola cada tarde (plan `docs/plans/2026-10-14-entorno-pre.md` de erplora-next).

1. Cada push a una rama de trabajo corre `test / test` (`ci.yml`).
2. Si `pre` avanzó, se integra `origin/pre` en la rama y se vuelve a empujar.
3. Con el check en verde, `git push origin <rama>:pre` (fast-forward): `deploy.yml` prueba, construye
   la imagen y la despliega en pre; si estaba apagada, la enciende. Sin release: las releases son de
   prod.
4. Probado en pre, PR `pre` → `main` con «Create a merge commit»: despliega prod como siempre
   (release `hub-v…`).
5. Después, `git push origin main:pre` (fast-forward) para que `pre` no se separe de `main`.

La rama decide el entorno (`.github/scripts/deploy-env.sh`): `main` → prod, `pre` → pre; cualquier
otra no despliega. Relanzar o volver atrás, siempre desde la rama del entorno:

```bash
gh workflow run deploy.yml --repo ERPlora/hub --ref pre -f environment=pre
gh workflow run rollback.yml --repo ERPlora/hub --ref pre -f environment=pre -f confirm=ROLLBACK
gh workflow run deploy.yml --repo ERPlora/hub --ref main -f environment=prod -f release=hub-v2026.10.14.1
```

Variables del repo: `AWS_REGION`, `ALB_DNS_NAME`, `AWS_DEPLOY_ROLE_ARN` (prod, confía en `main`),
`AWS_DEPLOY_ROLE_ARN_PRE` (pre, confía en `pre`) y, opcional, `BUILD_RUNNER`. En las tareas,
`ERPLORA_ENVIRONMENT` (`prod` o `pre`: prefijo `hub`/`pre-hub` de la caché en Valkey) y
`HUB_BASE_DOMAIN` (`erplora.com` o `pre.erplora.com`; en local, `localhost`): un Hub solo sirve
`<slug>.<HUB_BASE_DOMAIN>` y `hubs.<HUB_BASE_DOMAIN>`.
