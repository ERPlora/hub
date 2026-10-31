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
| `PUT /internal/hubs/{id}` | `base.hub.register` | 202 `requested` si lo crea, con su BD propia por hacer (el worker la hace, «Alta» abajo, y el SaaS recibe `POST /internal/hubs/{id}/ready` cuando está lista); 202 también si lo actualiza mientras se prepara (uno `failed` se reintenta al momento), 200 si lo actualiza ya listo; 422 `base.slug_invalid`, 409 `base.slug_taken`, `base.hub_cancelled`, `hub_purged` |
| `GET /internal/hubs/{id}` | `base.hub.get` | la fila: `status` `requested`, `creating`, `migrating`, `seeding` o `failed` mientras se prepara, `ready` (lo que espera el SaaS), `cancelled`…; nunca dónde está su BD; 404 |
| `DELETE /internal/hubs/{id}` | `base.hub.cancel` | 202 `cancelled` (con su BD propia terminada, el worker la copia: `offboarding`, «Copias de los datos» abajo); 404; 409 `hub_purged` |
| `POST /internal/hubs/{id}/restore` | `base.hub.restore` | 200 `ready` (`requested` otra vez si su BD no llegó a terminarse); 404; 409 `hub_purged` |
| `GET /internal/hubs/{id}/dumps` | `base.hub.dump_list` | 200 `{available, dumps: [{id, kind, created_at, bytes, url}]}`: las copias de sus datos de la más nueva a la más vieja (`id` = su clave en el bucket, `url` prefirmada de 15 min, descarga como fichero); `available: false` si nunca tendrá copia (sin BD propia, o dado de baja antes de terminarla); 200 también dado de baja; 404 desconocido o purgado; 503 `base.dumps_unavailable` sin bucket |
| `GET /internal/usage?day=AAAA-MM-DD[&cursor=]` | `base.usage.list` | 200 `{day, hubs: [{id, s3_bytes, db_bytes, active_users_1d, active_users_30d}], next_cursor}`: lo que usó ese día (UTC) cada negocio con BD propia, medido esa noche (`base/usage.py`), por páginas de 500; 409 `usage_not_ready` antes de medirlo; 422 `internal.payload_invalid` sin `day`, mal escrito o con un cursor ajeno |
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
la app apagada en él, 404 `app_inactive` (erplora.com guarda el mensaje y reintenta), leída en la BD del propio negocio
(ya dentro de su hub: el host por el que entra el SaaS no abre ninguno); si esa BD falla ahora, 503
`base.hub_unavailable`, con su línea en el log (`base.hub_unreachable`, o `base.hub_unavailable` si la BD dice ser de
otro hub), y erplora.com también reintenta; un cuerpo fuera de contrato, 422 con `fields`; y el sobre de cualquier otra
negativa de la operación, tal cual.

## Tenencia: una BD por hub (fase 1, tajadas S1–S3)

Plan `docs/plans/2026-10-22-fase-2-tenencia.md` de erplora-next; reglas en PLAN-DB y CLAUDE.md «Tenencia del Hub».

- **Dos clases de BD.** La de control (`default`) guarda el registro (`control/`: `Hub`, `DemoCode`, `Cluster`,
  `HubDue`; `Hub` y `DemoCode` conservan sus tablas `base_hub` y `base_democode`), Django (admin, auth, contenttypes,
  sesiones) y, en esta fase, `base.Membership`. La de cada hub, todo lo demás (`base`, `live` y cada app de `apps/`).
  La lista explícita está en `base/tenancy/inventory.py`; un modelo sin clase falla. El outbox (`live.OutboxEvent`
  y sus entregas) sigue al contexto: las operaciones del registro (`base.hub.*`, `base.demo.*`) lo escriben en control.
- **Modo compartido transitorio (hasta S5).** `Hub.db_name` vacío = el hub sigue con sus datos en la BD de control,
  como en la fase 1: los hubs de prod de antes de S2a, las demos de antes y `a`/`b` (`seed_local_hubs`). Desde S2a
  (ronda 2026-10-30 de PLAN-DB, decisión 1) todo negocio y toda demo nuevos nacen con `db_name` (`<control>_<hex>`,
  `<control>_demo_<hex>`; `base/tenancy/names.py`) y trabajan en su BD; un test
  (`base/tenancy/tests/test_provision.py`) impide crear un hub en `base/services.py` sin ella, salvo `a`/`b`:
  `seed_local_hubs` les da BD propia (clonada de `<control>_template`, con las tablas de todas las apps y todas
  encendidas) solo cuando todas las apps pueden vivir en una (`provision.portable_apps`); mientras alguna no pueda
  (`staff`, `attendance`, `task`, `whatsapp_inbox` y las que dependen de ellas apuntan a los usuarios de control),
  comparten la de control y el log dice qué apps lo impiden. Un `a`/`b` que ya existe conserva su BD. S5 hace el corte
  y retira el modo.
- **Alta** (`base/tenancy/provision.py`, S2a). `PUT /internal/hubs/{id}` y `POST /internal/demos` dejan el hub
  `requested` y debido en `control.HubDue`; el worker (o `provision(hub)`) toma su arriendo (`SELECT … FOR UPDATE SKIP
  LOCKED`, 60 s, renovado en cada paso y entre app y app al migrar: dos altas a la vez hacen una sola BD) y lo lleva por `creating` (lo coloca en
  el `Cluster` abierto con menos hubs bajo su `max_hubs`, o en el servidor de los settings si no hay ninguna fila; sin
  sitio, `no_cluster_available`; y clona `<control>_template[_<vertical>]` de ese cluster con `CREATE DATABASE …
  TEMPLATE`, privada: nada a `PUBLIC`, `CONNECT, TEMPORARY` a `hub_app` y `hub_admin`), `migrating` (lleva a la hoja
  las apps que la plantilla ya tiene (todas las portables, que las plantillas traen) y `base`: el alta es el clon y no
  migra nada; las tablas de cualquier otra app se crean la primera vez que el negocio la enciende (S3); cada paso deja en
  el log `base.tenancy.provision.step` con sus segundos), y anota `schema_apps = {app: su última migración}`), `seeding`
  (la foto del SaaS guardada en la fila: sus personas y los bloques de las apps
  encendidas; si llega otra mientras, se aplica también antes de `ready`) y `ready` (el SaaS lo oye tras el COMMIT).
  Una foto que llega a un negocio sin BD hecha (preparándose, o cancelado o fallido antes de estar listo) se guarda en
  la fila sin entrar en ella (`registry.database_is_made`). Cada paso escribe
  control en una transacción corta (`base/services.py`, «The provisioning's writes in control») y se puede repetir. Un
  fallo deja `failed` con `attempts`, `last_error` (`<código>: <motivo>`: `no_cluster_available`, `template_missing`,
  `clone_failed`, `schema_failed`, `photo_moving`, `unexpected`) y `next_attempt_at` (1 min, 5 min, 15 min y luego cada hora). La
  puerta del host responde 503 en todos esos estados. `CREATE`/`DROP DATABASE` van por `base/tenancy/ops.py`: conexión
  directa del migrador a `postgres`, en autocommit, cerrada al salir.
- **Roles y clusters** (`base/tenancy/credentials.py`). El rol del migrador (`DB_MIGRATOR_USER/PASSWORD`; vacío, el de
  la conexión por defecto) solo lo tienen `worker` y `hub-migrate`; el web nunca. Un hub en un `Cluster` se alcanza por
  el PgBouncer de ese cluster (su escritor directo si la fila no nombra ninguno) y su `__ddl` y `ops` por su escritor;
  la fila manda en host y puertos. Con `secret_name`, las credenciales salen de dos secretos de Secrets Manager bajo
  ese prefijo, `…/app` (el único que puede leer el web) y `…/migrator`, leídos una vez cada 10 min; uno ilegible es un
  error con su nombre, nunca las credenciales del entorno. Sin `secret_name`, las del entorno.
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
  cambia solo el migrador (`base/tenancy/migrator.py`, abajo).
- **El migrador.** `ensure_schema(hub, add=())` es la única función que cambia el esquema de un hub: abre su alias
  directo `<db_name>__ddl` (sin PgBouncer, como el migrador del servidor del hub: el del settings o el de su
  `Cluster`), con `lock_timeout` 5 s y `statement_timeout`/`idle_in_transaction_session_timeout` 5 min, toma en esa BD
  el lock de esquema `pg_try_advisory_lock(hashtext('erplora.schema'))` (otra pasada espera hasta 120 s y si no,
  `schema_locked`), lleva a la hoja del código la plataforma (`base`, `live`), las apps que esa BD ya tiene y las de
  `add` con sus `requires`, y escribe en control lo que tiene (`Hub.schema_apps`: manda el `django_migrations` de la BD
  del hub) y `schema_state = current`. Un hub sin BD propia (`db_name=""`) da `HubWithoutDatabase`; nunca toca
  control. Nunca da un paso atrás ni borra una tabla. Toda app del hub cabe en la BD de un hub (tenencia W10: las
  personas del negocio son suyas, `base.HubUser`); si una volviera a enlazar un modelo de control, `add=` la rechazaría
  (`AppNotPortable`) y las plantillas la dejarían fuera, y el lint «(h)» de `tests/test_guardrails.py` lo impide antes.
- **Las plantillas**, en cada servidor donde viven hubs (`CREATE DATABASE … TEMPLATE` solo clona dentro de uno):
  `<control>_template`, solo la plataforma, y una `<control>_template_<vertical>` por vertical de `base/catalog.py`,
  clonada de la anterior, con las tablas de las apps de su vertical (`template_apps`) y todo apagado (ninguna
  `AppActivation`). La de la plataforma la crea **solo** `bootstrap_databases` (roles, `vector`, privilegios por
  defecto, sin acceso para PUBLIC); si falta en un servidor, `migrate_hubs` para con `TemplateMissing` («run
  db-bootstrap there»). La de una vertical que falta se clona (reintenta mientras otro tenga abierta la de la
  plataforma, 55006) y recibe los mismos permisos de BD que su origen, porque el clon no copia los `GRANT`; en cada
  pasada se igualan otra vez. Una cuya lista cambió se pone al día, nunca se rehace ni pierde tablas. En local,
  `node tests/e2e/database.ts` crea la `<BD>_template` de cada BD de e2e (y `--drop` borra sus plantillas); para la
  `hub` de desarrollo, `createdb hub_template` en el Postgres de compose (o `bootstrap_databases`).
- **`manage.py migrate_hubs`** (la tarea `hub-migrate` de cada despliegue): 1) control, bajo su lock; 2) las
  plantillas de cada servidor (con todas las apps portables, también en S3, `migrator.templates`; nunca se reconstruyen:
  el primer despliegue que les añade las portables migra cada una en caliente, cerca de un minuto, y un alta en ese rato
  cae en `clone_failed` y se reintenta a los 60 s; `clusters_to_migrate`: sin
  filas de `Cluster`, el del settings; con ellas, los abiertos
  y los cerrados que aún tienen hubs, y el del settings mientras viva en él un hub sin cluster), como canarios: si una
  falla, no se toca ningún hub; 3) los hubs atrasados según `schema_apps` (un despliegue sin migraciones no abre
  ninguna BD de hub) con BD propia ya hecha (`registry.own_database_made`: lista o con `ready_at`; uno cancelado o
  caducado antes de estar listo no tiene BD y no para el despliegue) y estado `ready`, `cancelled` o `expired`, solo
  con las apps que ya tienen (nunca crea una app que el hub no encendió: eso es de la activación, S3): primero el de
  ERPlora y después 4 a la
  vez, cada uno en su servidor; un fallo de `lock_timeout` se reintenta hasta 3 veces, y el hub que falla queda
  `behind`, no para a los demás y hace salir al comando con código ≠ 0. Una BD por delante del código (tras un
  rollback) no cuenta como atrasada. `--check` no aplica nada: lista lo pendiente de control, de las plantillas (abre
  cada una) y los hubs atrasados (sin abrirlos), y sale 1 si hay algo. Cada alias `__ddl` se olvida tras usarlo. Las
  credenciales del migrador son `DB_MIGRATOR_USER`/`DB_MIGRATOR_PASSWORD`; sin ellas falla
  (`MigratorCredentialsMissing`), nunca usa las de `default` (`hub_app` en el web y el worker), salvo en local con
  `DEBUG` (un solo rol); los tests las fijan en `config/settings_pytest.py`. Las de cada cluster se enchufan en
  `migrator.migrator_credentials`.
- **Quién abre el contexto**: `HubDatabaseMiddleware` (cada petición: el hub del host; en `hubs.localhost`, el hub
  elegido en el admin o la BD compartida), `HubContextBuilder.enter` (cada re-ejecución viva, en el hilo del ejecutor),
  `/ws/print`, las puertas de `/internal`, el worker y los comandos. Una sesión vale solo en el host donde se abrió
  (`SessionHostMiddleware`): la de B en el host de A es anónima (401).
- **Tests**: la suite construye por sesión `<BD de test>_template_test` con el migrador y clona dos hubs con BD
  propia (`base/tenancy/tests/hubs.py`; fixtures `hub_a`, `hub_b`; marca `django_db(databases=hubs.HUB_DATABASES)`).
  La plantilla de test lleva todas las apps del hub (`migrator.portable_apps()`, `base/tests/test_hub_user_links.py`).
  Los tests escritos antes de la tenencia caen en la BD compartida (fixture de sesión `shared_database_fallback`); los
  de la tenencia y los de cada puerta de entrada la apagan (`no_test_fallback`), como en producción.


### Activar una app crea sus tablas (tajada S3)

Un negocio y una demo nacen con las tablas de su plantilla (`<control>_template[_<vertical>]`: la plataforma y las apps de
su vertical) y todas las apps apagadas (PLAN §33); el alta es el clon. Las tablas de cualquier otra app se crean **la
primera vez que el negocio la enciende** (PLAN-DB §7, spec 2026-10-11 «tablas al activar»), nunca en el alta ni en
`migrate_hubs`, y nunca se borran:

- **Encender** (`base.app.enable`, Apps o un blueprint) en un hub con BD propia: si su BD ya tiene las tablas de la app
  y de lo que necesita (`Hub.schema_apps`, lo que confirmó el migrador), queda `on` al momento (200); si no, todo lo que
  enciende queda `creating` en un solo plan, la ruta responde **202** con `state: "creating"`, se anota
  `base.app.activation_requested` y, tras el COMMIT, se llama al worker (`HubDue.mark_due`). Cada fila guarda la última
  migración de la app en el código que la pidió (`AppActivation.target`).
- **El worker** (`_activations`, también con `--databases-only`) toma cada tick los hubs llamados (`hub_due` vencido y
  libre); en cada uno, lo debido (`creating`, o `failed` cuyo próximo intento llegó) se crea con
  `migrator.ensure_schema(hub, add=…)` bajo el lock de esquema del hub y `base.app.activation_settle` lo enciende
  (`base.app.enabled`, aviso vivo: Apps y el menú de todos los dispositivos cambian sin recargar) o lo deja `failed` con
  `attempts`, `last_error` y `next_attempt_at` (1, 5, 15 min y después cada hora; `base.app.activation_failed`), y mueve
  la llamada del hub a lo siguiente que espera (o la quita). Esquema ocupado por otra ejecución: +30 s. Una petición de un
  código más nuevo que el del worker (o la app o lo que necesita ya en una migración que su código no conoce): se deja a
  un worker de ese código, +60 s, y a los 10 minutos queda `failed` con `code_behind` (tras un rollback no llega
  ninguno). El pase de `hub_due` no toca la llamada de un hub listo. Una llamada perdida la encuentra el pase por los
  hubs servidos: cada 10 minutos los que tuvieron una visita en 7 días y una vez al día el resto.
- **Apps** pinta «Activándose…» (y la pantalla de la app dice que se abre en un momento) y, si falló, «No se ha podido
  activar» con **«Reintentar»** (`base.app.retry`, 202); «Desactivar» en las tres. La sesión (`base.session.me`) da `activating`.
  Mientras no está `on` sus operaciones responden 404 `app_inactive`, el relevo no le entrega nada y sus tareas no
  corren. **Apagar** nunca borra tablas; apagada mientras se crean, queda `off` con ellas hechas. Un blueprint que
  enciende una app que aún se prepara no carga sus datos y su informe dice que se vuelva a cargar en un minuto
  («Reintentar» del informe trae lo que faltó).
- Un hub que aún comparte la BD de la fase 1 (`db_name=""`) enciende al momento, como hasta ahora (propuesta (i) de
  la ronda 2026-10-30, hasta el corte de S5). `seed_local_hubs` da a `a` y `b` las tablas de todas las apps y todas
  encendidas (`provision(apps=…)`).


### Copias de los datos y uso nocturno (tajada S2b)

PLAN-DB, ronda 2026-10-30: decisión 2 y propuestas (a), (f), (j), (k), (l), (m).

- **Restablecer el negocio** (`base.hub.reset`, Ajustes › Datos): sin `dry_run` ya no vacía en la petición; anota lo
  pedido en el registro (`Hub.reset_requested_at`, `Hub.reset_sections`), lo deja debido en `hub_due` y responde
  `status: "copying"`. El worker (`base/worker.py`, pase `_data`, bajo el arriendo del hub) copia la BD del negocio
  (`base/tenancy/dumps.py`) y, solo si la copia quedó guardada, vacía las secciones en su BD con
  `base.hub.reset_apply` (una transacción: todo o nada) y anota `base.hub.data_reset`; si la copia falla no vacía
  nada y deja `failed` con su motivo (`dumps_unavailable`, `dump_failed`, `emptying_failed`, `hub_not_ready`), y la
  pantalla ofrece «Volver a intentarlo». Cada paso llega en vivo (`base.hub.reset_progressed`, aviso tras el COMMIT en
  control) a `base.hub.dumps`. Sin bucket, 503 `base.dumps_unavailable`; con otro en marcha, 409
  `base.reset_in_progress`; sin BD propia, 409 `base.reset_shared_database` como antes.
- **La baja**: `base.hub.cancel` de un negocio con su BD propia terminada lo deja debido y el worker lo copia una vez
  (`offboarding`); si falla, reintenta a 1 min, 5 min, 15 min y luego cada hora (`attempts`, `last_error`,
  `next_attempt_at`). La BD se conserva: el `DROP` del día 90, con su segunda copia, no está en esta tajada.
- **La copia** (`dump_hub`): `pg_dump -Fc --no-owner --no-acl` de esa BD como el migrador, por conexión directa al
  escritor de su cluster (`migrator_conninfo`, nunca PgBouncer), con la contraseña en `PGPASSWORD` y nunca en la orden
  ni en un error, acotado a 15 min (el arriendo se renueva mientras corre) y a un fichero temporal; solo si termina
  bien se sube a `HUB_DUMPS_BUCKET` en `<hex>/<AAAAMMDDTHHMMSSZ>-<tipo>.dump` y se guarda su `control.HubDump`. Cada
  copia caduca a los 90 días por la regla del bucket (aws `s3_dumps.tf`). Los enlaces (`presigned_url`) duran 15 min y
  descargan el fichero como `erplora-<slug>-<fecha>-<tipo>.dump`. En local y en los tests, `HUB_DUMPS_ENDPOINT_URL`
  apunta boto3 a otro S3 (los tests: el servidor de moto, `base/tenancy/tests/s3.py`); sin `HUB_DUMPS_BUCKET` no hay
  copias y el restablecimiento responde 503.
- **Ajustes › Datos › Restablecer › «Copias»** (`base.hub.dumps`, vivo; `base.hub.dump_link` en cada «Descargar»):
  las copias del negocio y su último restablecimiento; nada en un negocio que aún comparte BD.
- **Uso nocturno** (`base/usage.py`, pase `_usage` del worker): a las 00:15 UTC mide el día que acabó (antes de que
  el SaaS lo pida a las 01:15 y fuera de la copia de Aurora de 02:00–03:00) para cada negocio con BD propia:
  `pg_database_size` desde el catálogo de su cluster (conexión de mantenimiento del migrador, sin abrir la BD del
  hub), sus ficheros (`files.used_bytes`) y las personas que entraron ese día y en los 30 que lo acaban
  (`control.HubVisit`, una por persona, hub y día en cada login). Los que comparten BD no se miden
  (`base.usage_shared_database`). La noche es un `control.UsageRun`: la mide el primer worker que la reclama, y otro la
  retoma si quedó a medias una hora. Sistema › Recursos enseña el tamaño (`base.plan.usage`, `database`).

## Demo

Una demo es un hub **vacío** del propio Hub (`demo-<8 hex>`, fila `is_demo` de `base.Hub`) que pide el `/demo/` del
SaaS, sin cuenta ni tarjeta, durante `DEMO_TTL_MINUTES` (60). Desde S2a (ronda 2026-10-30 de PLAN-DB) nace con su BD
propia, `<control>_demo_<hex>`, clonada de la plantilla de su vertical por el worker como un negocio («Tenencia»,
«Alta»); las demos de antes compartían las tablas de las apps con las demás y con `a`/`b`, y caducan solas.

| Ruta | Operación | Respuesta |
|---|---|---|
| `POST /internal/demos` `{session_key, vertical, language}` | `base.demo.create` | 202 `{id, slug, status: "requested", expires_at, created: true}` (el SaaS sondea `GET /internal/hubs/{id}` hasta `ready` antes de pedir el código); 200 con la demo viva de ese navegador, preparándose o lista (`created: false`); 503 `base.demo_full` + `Retry-After: 60` con `MAX_CONCURRENT_DEMOS` (50) vivas, contando las que se preparan (el recuento y el alta van bajo `pg_advisory_xact_lock`: dos altas a la vez nunca pasan el tope ni dan dos demos a un navegador); 422 `internal.payload_invalid` |
| `POST /internal/demos/{slug}/codes` `{session_key, language}` | `base.demo.code_create` | 201 `{code, expires_at}` (un uso, 60 s, solo se guarda su sha256); 404; 410 `base.hub_gone`; 403 `base.demo_not_owner`; 503 `base.hub_preparing` mientras se hace su BD |

`session_key` es el sha256 (hex) de un token aleatorio de la sesión del navegador en el SaaS: una demo viva por
navegador. Entrada: el SaaS salta a `/auth/login?next=/` de la demo, que (como un negocio, con la cookie
`hub_login_state`) vuelve a `{SAAS_URL}/demo/enter/?hub=<slug>&next=<next>&state=<state>`; el SaaS pide el código y
lo envía en un formulario a `/auth/callback`, que lo canjea **en local** (sin llamar al SaaS) y abre la sesión de
`demo:<slug>` («Demo», `hub_owner`, nunca staff). Un código gastado, caducado o de otra demo vuelve a
`{SAAS_URL}/demo/?state=failed`; salir de la demo, a `{SAAS_URL}/demo/`. `GET /api/me` lleva `demo: {expires_at}`
(`null` en un negocio).

Caducidad: desde `expires_at` el host responde **410** («This demo has ended», con enlace a `/demo/?state=expired` del
SaaS, que olvida la demo que su sesión aún daba por viva: una demo puede acabar antes de su hora). El
worker la purga en ≤ 60 s (`reap_demos`: la marca `expired` y debida, y bajo su arriendo la pasa a `dropping`, borra su
BD entera con `DROP DATABASE … WITH (FORCE)`, solo esa, y `base.demo.purge` borra sus códigos, su `Membership` y el
usuario `demo:<slug>`; una demo de antes de S2a no tiene BD que borrar) y la fila queda `purged` como lápida
`DEMO_TOMBSTONE_DAYS` (7) días; después, 404. Una demo que caduca mientras se prepara se borra sin terminarla. Para terminar una demo a mano: la acción «Expire
now» del admin (`hubs.localhost:8000/admin/control/hub/`, solo superusuarios) o, en cualquier entorno:

```bash
uv run python manage.py demo_expire demo-1a2b3c4d   # base.demo.expire + una pasada del reaper → «demo-1a2b3c4d: purged»
```

Probarla en local, con el SaaS en `:8001` (su `HUB_INTERNAL_URL` por defecto apunta a `http://localhost:8000` y el
secreto local `local-internal-shared-secret` es el mismo en los dos):

```bash
uv run python manage.py runserver                 # Hub en :8000 (con `migrate`, `migrate_hubs` y `seed_local_hubs` hechos)
uv run python manage.py run_worker                # hace la BD de la demo (sin worker se queda en «preparando»)
(cd ../saas && uv run python manage.py runserver 127.0.0.1:8001)
# http://localhost:8001/demo/ → «Try the demo» → http://demo-<hex>.localhost:8000/ con la sesión «Demo»
uv run python manage.py demo_expire demo-<hex>    # el host pasa a 410 y su enlace lleva a /demo/ del SaaS en «expired»
```

La e2e de punta a punta es `tests/e2e/demo.spec.ts` (cómo correrla: `tests/e2e/README.md`, «La demo»).

## Worker: tareas programadas y avisos entre apps

`uv run python manage.py run_worker` es la tarea `worker` (`base/worker.py`): registra los módulos en el SaaS y, cada
5 s, corre las tareas programadas que tocan (`base/scheduler.py`) y reparte el outbox (`base/relay.py`, ronda
2026-10-20 de `PLAN-HUB.md`) de la BD compartida; después, en cada hub listo con BD propia (uno a uno, dentro de
`use_hub`, 3 s por tick como mucho y el siguiente tick sigue por el próximo hub), reparte su outbox, escribe una vez por
proceso el calendario de sus apps en su BD y corre las tareas que tocan de sus apps encendidas en su propio ámbito (su
aviso vivo sale por su canal); y al final hace las BD de los hubs debidos en `HubDue` y borra las de las demos que
acabaron (`base/tenancy/provision.py`, «Tenencia», «Alta»). Antes de eso crea las tablas de las apps que un hub con BD propia encendió (tajada S3, «Activar una app
crea sus tablas»). Con `--databases-only` solo hace estas dos cosas (las BD, las tablas de las apps encendidas y las
demos que acaban): es el worker del e2e, cuyas specs juegan ellas mismas el reparto y las tareas. El reparto lleva cada evento nuevo a las reacciones de las apps que lo escuchan (el
`REACTIONS` de su `events.py`; `"*"` = todo evento de las demás): la venta cobrada baja el stock y cuenta en la ficha
del cliente, la ronda enviada abre su comanda en cocina, etc. Un evento que no es de un hub (los del registro y las
demos, en el outbox de control) no lo oye ninguna app: no hay hub en el que correr su reacción. Cada app lo recibe **una vez** (`base.EventDelivery`, en
la misma transacción que su reacción), como el sistema y en el ámbito del hub que lo anotó (su aviso vivo sale por el
canal de ese hub). Una reacción que falla se deshace y reintenta a los 2, 4, 8… s (una hora como mucho); al octavo
intento queda `dead` con su error, en el log y en la fila. Los eventos que una reacción anota se reparten un nivel
más abajo, y pasado el 16 no se entregan. Lo que una reacción o una tarea deja para después del COMMIT y espera a la
red (la llamada a otro sistema o el paso del asistente de Automatizaciones, y lo que la Bandeja de WhatsApp entrega a
erplora.com: mensajes, borrados y plantillas) va por `base/outbound.py`: 4 hilos del
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

### Las personas del negocio en su BD (`base.HubUser`)

Control guarda el usuario de la sesión (`auth.User`, la copia `saas:<id>` de la cuenta de erplora.com) y el rol
(`Membership`); la BD del hub guarda a la persona del negocio, `base.HubUser`: `username` (`saas:<id>`, `demo:<slug>`),
`account_id` (la cuenta de erplora.com; ninguna para el dueño de una demo), nombre, correo, `is_active` y su alta. Nunca
se borra: quien se va conserva su nombre en lo que firmó y deja de estar activo. Se crea o se pone al día en cada
entrada (código de erplora.com, demo, PIN o tarjeta: `base.services.ensure_hub_user`), en la primera escritura de quien
aún no la tiene (`acting_hub_user`) y desde la foto del SaaS (`base.hub_user.sync`, dentro de `hub.state_apply`; la de un negocio cuya BD aún se prepara, en
su siembra). Las
apps enlazan a ella, nunca a `settings.AUTH_USER_MODEL` (lint «(h)»): `staff` (registro y aprobación de ausencias),
`attendance`, `task` y `whatsapp_inbox`; leen la de quien llama con `base.queries.hub_user_of`, y la tarjeta del
asistente nombra a la persona por su id con `base.hub_user.get`. `base.session.me` da como `user.id` el de esa persona,
el mismo que guardan los registros, para que una pantalla sepa qué es «suyo».

El paso (expand) dejó las columnas viejas, a `auth_user`, fuera del estado, vacías y sin su clave (`*/migrations/*_hub_users`),
y escribió el contract en `base/tests/test_migration_safety.py` (`ACCEPTED`) para un despliegue posterior. Para que la
historia se pueda reproducir en una BD de hub, que no tiene `auth_user`, se editaron por excepción las `0001_initial` de esas
cuatro apps (`db_constraint=False`) y el `RunPython` de `attendance/0002`: donde ya corrieron, nada cambia.

### Migraciones que conviven con el código anterior

`ecs-deploy.sh` corre `hub-migrate` (`migrate_hubs`: control, plantillas y hubs atrasados; espera hasta
`MIGRATE_TIMEOUT_SECONDS`, 3600 s por defecto) **antes** de cambiar los servicios, y un rollback devuelve el código anterior
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
