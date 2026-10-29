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
el resto de variables toma los valores locales por defecto (lista completa en `.env.example`). `.env` nunca se
sube al repo.

`runserver` arranca Vite en el `VITE_DEV_PORT` que lee Django, del entorno o del `.env` (por defecto `5173`):
a un segundo checkout le basta `VITE_DEV_PORT=5203` en su `.env`. `pnpm run dev` o la e2e sueltos solo la leen
del entorno, y `uv run pytest` sigue en el `5173` aunque la defina (`config/settings_pytest.py`).

## Registro de hubs y `/internal`

El Hub sirve solo los hubs de su registro (`control.Hub`, antes `base.Hub`; plan `docs/plans/2026-10-17-demo-hubs-fase-1.md` de
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
| `PUT /internal/hubs/{id}/state` | `base.hub.state_apply` | 200 `{applied, version}`: guarda la foto si su versión es mayor y aplica el bloque VeriFactu y el estado del negocio y, con la app de WhatsApp activa en ese negocio, su clave `whatsapp` (el estado del número, con la versión de la foto, por `whatsapp_inbox.channel.sync`; apagada, la foto se aplica y la clave espera a la siguiente); 404; 422 si un bloque no cumple el contrato (no se guarda nada) |

Sin firma válida, 401 `internal.unsigned`; un cuerpo que nombra otro hub que el de la ruta, 422
`internal.hub_mismatch`. `/internal` responde en cualquier host (el SaaS entra por `hub.erplora.internal`; el ALB
no lo publica).

Las puertas de WhatsApp (contrato en `apps/whatsapp_inbox/WORKBOOK.md`, «Contrato con el SaaS», puertas 1–4) llevan
en el cuerpo el negocio, `hub` (su slug en la fase 1), y ejecutan la operación de la bandeja como el sistema en ese
negocio:

| Ruta | Operación | Respuesta |
|---|---|---|
| `POST /internal/whatsapp/inbound` | `whatsapp_inbox.message.receive` | 200 `{id, conversation_id, created}`; el mismo `wa_message_id` otra vez, 200 con `created: false` |
| `POST /internal/whatsapp/status` | `whatsapp_inbox.message.update_status` | 200 `{updated, status}`; un mensaje desconocido, `updated: false` |
| `PUT /internal/whatsapp/channel` | `whatsapp_inbox.channel.sync` | 200 `{applied, version}`; una versión igual o menor no se aplica |

En las tres, en este orden: sin `hub`, 422 `internal.payload_invalid`; el negocio responde como su host (404
`not_found` si el registro no lo conoce, 410 `base.hub_gone`, 503 `base.hub_preparing`, 402 `base.hub_suspended`);
la app apagada en él, 404 `app_inactive` (erplora.com guarda el mensaje y reintenta); un cuerpo fuera de contrato, 422
con `fields`; y el sobre de cualquier otra negativa de la operación, tal cual.

## Tenencia: una BD por hub (fase 2, tajada S1)

Plan `docs/plans/2026-10-22-fase-2-tenencia.md` de erplora-next; reglas en PLAN-DB y CLAUDE.md «Tenencia del Hub».

- **Dos clases de BD.** La de control (`default`) guarda el registro (`control/`: `Hub`, `DemoCode`, `Cluster`,
  `HubDue`; `Hub` y `DemoCode` conservan sus tablas `base_hub` y `base_democode`), Django (admin, auth, contenttypes,
  sesiones) y, en esta fase, `base.Membership`. La de cada hub, todo lo demás (`base`, `live` y cada app de `apps/`).
  La lista explícita está en `base/tenancy/inventory.py`; un modelo sin clase falla. El outbox (`live.OutboxEvent`
  y sus entregas) sigue al contexto: las operaciones del registro (`base.hub.*`, `base.demo.*`) lo escriben en control.
- **Modo compartido transitorio (S1–S4).** `Hub.db_name` vacío = el hub sigue con sus datos en la BD de control,
  como en la fase 1: todos los hubs de prod, las demos y `a`/`b` (`seed_local_hubs`). Un hub con `db_name`
  (`<control>_<hex>`, `demo_<hex>`; `base/tenancy/names.py`) trabaja en su BD. S5 hace el corte y retira el modo.
- **Contexto** (`base/tenancy/context.py`): `use_hub(hub)`, `use_control()` y, transitorio, `use_shared_database()`
  (la BD única de la fase 1 para lo que aún no tiene un hub: el relevo y las tareas del worker, el admin sin hub
  elegido, `manage.py shell`, el hub de plataforma sin fila). Sin contexto, un modelo o una operación de hub lanza
  `HubContextMissing`: nunca cae a `default`. Una operación de un hub dentro del contexto de otro,
  `HubContextMismatch`.
- **Enrutado** (`base/tenancy/router.py`, detrás de `SharedRouter`): control → `default`; hub → el alias del contexto.
  El alias de un hub con BD propia es `hub_<hex>`, registrado en caliente copiando `hub_template` (PgBouncer en modo
  transacción: sin pool, `CONN_MAX_AGE` 0, sin cursores de servidor ni sentencias preparadas) sin mutar
  `connections.settings`; su `base_hub_identity` se comprueba una vez por proceso (otra identidad → 503
  `base.hub_unavailable`, no se sirve nada). `migrate` solo acepta `default` (y `shared`); el esquema de un hub lo
  cambia el migrador por su alias `<db_name>__ddl` (`migrate_apps`; `ensure_schema` llega en S3).
- **Quién abre el contexto**: `HubDatabaseMiddleware` (cada petición: el hub del host; en `hubs.localhost`, el hub
  elegido en el admin o la BD compartida), `HubContextBuilder.enter` (cada re-ejecución viva, en el hilo del ejecutor),
  `/ws/print`, las puertas de `/internal`, el worker y los comandos. Una sesión vale solo en el host donde se abrió
  (`SessionHostMiddleware`): la de B en el host de A es anónima (401).
- **Tests**: la suite construye por sesión `<BD de test>_template_test` con el migrador y clona dos hubs con BD
  propia (`base/tenancy/tests/hubs.py`; fixtures `hub_a`, `hub_b`; marca `django_db(databases=hubs.HUB_DATABASES)`).
  La plantilla de test lleva las apps cuyas tablas solo apuntan a las del hub: las enlazadas al usuario de control
  (`staff`, `attendance`, `task`, `whatsapp_inbox` y las que dependen de ellas) esperan al personal propio del hub.
  Los tests escritos antes de la tenencia caen en la BD compartida (fixture de sesión `shared_database_fallback`); los
  de la tenencia y los de cada puerta de entrada la apagan (`no_test_fallback`), como en producción.

## Demo

Una demo es un hub **vacío** del propio Hub (`demo-<8 hex>`, fila `is_demo` de `base.Hub`) que pide el `/demo/` del
SaaS, sin cuenta ni tarjeta, durante `DEMO_TTL_MINUTES` (60). En la fase 1 no tiene BD propia: sus datos comparten
las tablas de las apps con las demás demos y con `a`/`b` (limitación aceptada; plan
`docs/plans/2026-10-17-demo-hubs-fase-1.md`, §1.6 y §1.7).

| Ruta | Operación | Respuesta |
|---|---|---|
| `POST /internal/demos` `{session_key, vertical, language}` | `base.demo.create` | 201 `{id, slug, expires_at, created: true}`; 200 con la demo viva de ese navegador (`created: false`); 503 `base.demo_full` + `Retry-After: 60` con `MAX_CONCURRENT_DEMOS` (50) vivas (el recuento y el alta van bajo `pg_advisory_xact_lock`: dos altas a la vez nunca pasan el tope); 422 `internal.payload_invalid` |
| `POST /internal/demos/{slug}/codes` `{session_key, language}` | `base.demo.code_create` | 201 `{code, expires_at}` (un uso, 60 s, solo se guarda su sha256); 404; 410 `base.hub_gone`; 403 `base.demo_not_owner` |

`session_key` es el sha256 (hex) de un token aleatorio de la sesión del navegador en el SaaS: una demo viva por
navegador. Entrada: el SaaS salta a `/auth/login?next=/` de la demo, que (como un negocio, con la cookie
`hub_login_state`) vuelve a `{SAAS_URL}/demo/enter/?hub=<slug>&next=<next>&state=<state>`; el SaaS pide el código y
lo envía en un formulario a `/auth/callback`, que lo canjea **en local** (sin llamar al SaaS) y abre la sesión de
`demo:<slug>` («Demo», `hub_owner`, nunca staff). Un código gastado, caducado o de otra demo vuelve a
`{SAAS_URL}/demo/?state=failed`; salir de la demo, a `{SAAS_URL}/demo/`. `GET /api/me` lleva `demo: {expires_at}`
(`null` en un negocio).

Caducidad: desde `expires_at` el host responde **410** («This demo has ended», con enlace a `/demo/?state=expired` del
SaaS, que olvida la demo que su sesión aún daba por viva: una demo puede acabar antes de su hora). El
worker la purga en ≤ 60 s (`reap_demos`, `base.demo.purge`: borra sus códigos, su `Membership` y el usuario
`demo:<slug>`; `purge_demo_data` no borra nada en la fase 1 y en la fase 2 hará el `DROP DATABASE`) y la fila queda
`purged` como lápida `DEMO_TOMBSTONE_DAYS` (7) días; después, 404. Para terminar una demo a mano: la acción «Expire
now» del admin (`hubs.localhost:8000/admin/control/hub/`, solo superusuarios) o, en cualquier entorno:

```bash
uv run python manage.py demo_expire demo-1a2b3c4d   # base.demo.expire + una pasada del reaper → «demo-1a2b3c4d: purged»
```

Probarla en local, con el SaaS en `:8001` (su `HUB_INTERNAL_URL` por defecto apunta a `http://localhost:8000` y el
secreto local `local-internal-shared-secret` es el mismo en los dos):

```bash
uv run python manage.py runserver                 # Hub en :8000 (con `migrate` y `seed_local_hubs` hechos)
(cd ../saas && uv run python manage.py runserver 127.0.0.1:8001)
# http://localhost:8001/demo/ → «Try the demo» → http://demo-<hex>.localhost:8000/ con la sesión «Demo»
uv run python manage.py demo_expire demo-<hex>    # el host pasa a 410 y su enlace lleva a /demo/ del SaaS en «expired»
```

La e2e de punta a punta es `tests/e2e/demo.spec.ts` (cómo correrla: `tests/e2e/README.md`, «La demo»).

## Worker: tareas programadas y avisos entre apps

`uv run python manage.py run_worker` es la tarea `worker` (`base/worker.py`): registra los módulos en el SaaS y, cada
5 s, corre las tareas programadas que tocan (`base/scheduler.py`) y reparte el outbox (`base/relay.py`, ronda
2026-10-20 de `PLAN-HUB.md`). El reparto lleva cada evento nuevo a las reacciones de las apps que lo escuchan (el
`REACTIONS` de su `events.py`; `"*"` = todo evento de las demás): la venta cobrada baja el stock y cuenta en la ficha
del cliente, la ronda enviada abre su comanda en cocina, etc. Cada app lo recibe **una vez** (`base.EventDelivery`, en
la misma transacción que su reacción), como el sistema y en el ámbito del hub que lo anotó (su aviso vivo sale por el
canal de ese hub). Una reacción que falla se deshace y reintenta a los 2, 4, 8… s (una hora como mucho); al octavo
intento queda `dead` con su error, en el log y en la fila. Los eventos que una reacción anota se reparten un nivel
más abajo, y pasado el 16 no se entregan. Lo que una reacción o una tarea deja para después del COMMIT y espera a la
red (la llamada a otro sistema o el paso del asistente de Automatizaciones) va por `base/outbound.py`: 4 hilos del
worker, fuera del bucle, así que una respuesta lenta nunca retiene el reparto de los demás ni las tareas; lo que se
pierde (cola llena, parada del worker) lo vuelve a lanzar el plazo de su app. Un negocio nace con todas las apps apagadas (ronda 2026-10-27; los
hubs de antes las conservan encendidas, migración `base/0017`); una app que se enciende después no recibe lo anterior. Lo anotado antes de la migración `base/0006_event_delivery` (el atraso desde
el primer despliegue) se da por repartido sin aplicarse.

## `/ws/print`: el canal del dispositivo que imprime

El único WebSocket del Hub (PLAN-HUB §5). `config/asgi.py` manda el HTTP a Django, como siempre, y el WebSocket de
`/ws/print` a `base/ws_print.py`, una aplicación ASGI propia, **sin Channels** (ronda 11: sin capa de canales); otra
ruta WebSocket se rechaza en el saludo (Daphne contesta 403). Lo sirve el mismo `daphne` del servicio `hub`, y el ALB
ya hace el *upgrade* por HTTP/1.1 (el latido de 30 s del dispositivo cabe en su `idle_timeout` de 120 s).

- **Quién entra**: el `Host` pasa por la misma puerta que el HTTP (`base.middleware`: sin hub 4404, terminado 4410,
  preparándose 4503); el `Origin` tiene que ser el del propio hub; la credencial es la cookie de sesión del Hub del
  saludo, comprobada en `hello` y en cada mensaje (un cierre de sesión corta el socket en el siguiente latido).
- **Protocolo**: el del Hub viejo (`print_ws.rs`), mismos mensajes y campos: `hello` (con `deviceId` y las
  `printers` a las que llega el dispositivo) → `ready`; `claim` → `job` o `idle`; `done`/`failed` → `ack`; `beat`;
  y del Hub, `wake` y `error` con su código. La tabla de códigos está en el docstring de `base/ws_print.py`.
- **Quién imprime lo decide Impresión** (PRINTING-F18): en `hello` el canal lee el alta del dispositivo por su
  `deviceId` (`printing.device.get`) y sus impresoras son las activas de esa alta, como en el Hub viejo. Un
  dispositivo sin alta (o retirado) se rechaza ya en `hello` con `print.host_not_registered` (4403). Con la sesión de
  quien gestiona las impresoras, las `printers` que nombra se suman y su primer `claim` lo da de alta (o le añade la
  impresora); con cualquier otra sesión no cambian nada. Cada `beat` vuelve a leer el alta: retirado, `refreshed: 0`.
- **La cola es de Impresión**: el canal llama por nombre a `printing.device.get`, `printing.printer.get`,
  `printing.job.claim`, `printing.job.complete`, `printing.job.fail` y `printing.job.list`, con la sesión del
  dispositivo (mismos permisos, ámbito y comprobación de app que la API HTTP); no toca modelos.
- **El `wake`** no abre otro `LISTEN`: el socket tiene un stream del broker de `live` (el `LISTEN` único del proceso
  en la BD de control, el de `/api/live`) suscrito a los trabajos en cola más nuevos de cada función del dispositivo;
  tras el COMMIT de un trabajo nuevo, solo en el canal de su hub, llega el empujón, sin el documento. Empuja solo lo
  que entra en la cola (un trabajo nuevo, uno reintentado o uno que otro dispositivo devolvió), como el `wake` del Hub
  viejo: el `claim`, el `done` y el `failed` del propio dispositivo no lo despiertan.

Para verlo en local: `curl -i -H 'Host: a.localhost:8000' -H 'Origin: http://a.localhost:8000' -H 'Connection: Upgrade'
-H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ=='
http://127.0.0.1:8000/ws/print` contesta `101 Switching Protocols`. La e2e es `tests/e2e/ws-print.spec.ts`.

## Límites de intentos

Las puertas que comprueban una credencial cuentan los intentos que **rechazan** por quien llama
(`base.throttle.client_key`: la IP que vio el ALB según `TRUSTED_PROXY_HOPS`, o su /64 si es IPv6, porque un cliente
tiene la /64 entera) con `base.throttle.AttemptLimit`, en la caché de Django (Valkey en AWS; la memoria del proceso en
local). La puerta comprueba **primero** la credencial: lo que acepta nunca cuenta ni se rechaza, así que un dispositivo
con sesión válida no queda fuera porque otro de la misma red (la tablet con la sesión caducada) haya fallado. Pasado
el tope, el siguiente intento **rechazado** de quien llama recibe la respuesta del límite hasta que acaba la ventana
que abrió su primer rechazo. El rechazo que llega al tope queda en el log de `base.throttle` con su clave
(`limit:<puerta>:<IP>`), nunca con la credencial.

| Puerta | Tope | Qué cuenta | Intento rechazado pasado el tope |
|---|---|---|---|
| `/auth/callback` (hub, demo y admin del Hub) | 10 en 5 min | código rechazado por el SaaS o vacío, `state` que no es de este navegador, código de demo que no abre nada | 429 con `Retry-After` y una página del Hub (`en` + `es`) que dice cuántos minutos esperar |
| `/internal/*` | 30 en 5 min | firma rechazada | 429 `base.rate_limited` con `Retry-After` |
| `/ws/print` | 10 en 5 min | sesión que no vale en este hub o que terminó | cierre 4429 `base.rate_limited` |
| web pública (`/api/website/public/*`) | 60 lecturas por hub e IP por minuto | todas | 429 `base.rate_limited` (`allow`, otra cuenta, sin credencial) |

No cuentan, porque nadie ha adivinado nada y contarlos bloquearía a la gente por un fallo de la plataforma: el SaaS
caído o con error, la firma del propio Hub rechazada por el SaaS, un código bueno cuyo usuario o papel no puede entrar
aquí y un `hello` de `/ws/print` sin sesión. El SaaS nunca firma mal: el tope de `/internal` es para lo demás que
llegue a la puerta. Las credenciales (código de un solo uso, firma HMAC, clave de sesión) no se pueden adivinar por
fuerza: el tope frena el ruido y lo deja en el log. Con Valkey caído, el límite se aparta y deja un error en el log: la
puerta sigue comprobando su credencial, porque la entrada, la impresión y las llamadas del SaaS no pueden pararse con
la caché, igual que `/readyz` (la web pública, en cambio, falla con ella). Las pruebas usan siempre la caché en memoria
(`config/settings_pytest.py`, aunque haya `VALKEY_URL`) y la vacían en cada test (`conftest.py`), porque todas llaman
desde la misma IP.

El PIN para cambiar de empleado y las API keys (`erpk_live`) aún no existen en el Hub (fase 2); cuando lleguen,
cuentan con el mismo `AttemptLimit`.

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

### Migraciones que conviven con el código anterior

`ecs-deploy.sh` corre `hub-migrate` **antes** de cambiar los servicios, y un rollback devuelve el código anterior
sobre el esquema ya migrado: durante un rato, el código anterior lee y escribe las tablas del nuevo (expand/contract,
PLAN-DB §7). Por eso, en una migración:

- **Una columna nueva `NOT NULL`** lleva su valor por defecto **en la BD** (`db_default=…`, además del `default` de
  Python), o nace `null=True` y pasa a `NOT NULL` en un despliegue posterior. Con solo `default`, Django rellena las
  filas y luego quita el `DEFAULT` de la columna, y los `INSERT` del código anterior, que no la conoce, caen con
  `null value in column … violates not-null constraint` hasta que acaba el despliegue (pasó en `kitchen/0004`, hub#115).
- **Quitar o renombrar** una columna o una tabla (`RemoveField`, `DeleteModel`, `RenameField`, `RenameModel`,
  `AlterModelTable`) va en dos despliegues: primero sale solo del estado (`SeparateDatabaseAndState` con
  `state_operations`; si es una columna, antes `null=True` o `db_default`) y en uno posterior se borra de la BD con
  `RunSQL`. Un renombrado puede conservar el nombre en la BD (`db_column=…`, `db_table=…`) y no rompe nada.
- **Estrechar** una columna con `AlterField` (pasar a `NOT NULL`, acortar `max_length`, cambiar a otro tipo o añadirle
  un `CHECK`, como el de un entero positivo) va en un despliegue posterior al que deja de escribir esos valores. Un
  `db_default` no salva el paso a `NOT NULL`: el código anterior conoce la columna y manda el `NULL` en su `INSERT`.
  Ampliar (más `max_length`, `text`, `smallint` → `integer` → `bigint`, `null=True`) no rompe nada.
- **Una restricción nueva** sobre una tabla que ya se usa (`AddConstraint` con `UniqueConstraint` o `CheckConstraint`,
  `AlterUniqueTogether` con un conjunto nuevo, `AlterField` a `unique=True`) va en un despliegue posterior al que deja de
  escribir las filas que la incumplen: el `INSERT` o el `UPDATE` del código anterior que la incumple falla. `NOT VALID`
  (`AddConstraintNotValid` + `ValidateConstraint`) y el índice único `CONCURRENTLY` solo evitan el bloqueo de la tabla,
  no ese fallo, así que también cuentan. Quitar una restricción no rompe nada.

Lo comprueba `base/tests/test_migration_safety.py` sobre todas las migraciones que carga el proyecto (`base`, `live`,
las apps y las de Django: `hub-migrate` las aplica todas), cada una contra el estado anterior del `MigrationLoader`.
El paso del despliegue posterior (el contract), las migraciones ya desplegadas antes de la regla y las de Django van en
su lista `ACCEPTED`: una entrada nueva se justifica en su PR (la del contract, con la PR de su primer paso), y una que ya
no rompe nada hace caer el test.
