# hub-next

## Desarrollo local

```bash
git submodule update --init          # packages/live y packages/ui (ERPlora/live, ERPlora/ui)
printf 'DEBUG=True\n' > .env         # sin DEBUG, el hub arranca como producción
uv sync && pnpm install
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
