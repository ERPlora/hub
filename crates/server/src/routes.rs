//! Router assembly: app(), serving wrappers and the hub-context endpoint — split out of `lib.rs` verbatim (hub#1404).

use crate::*;

/// Construye el router con todas las rutas montadas sobre `state`.
pub fn app(state: AppState) -> Router {
    let registration_state = state.clone();
    let activity_state = state.activity.clone();
    // hub#1401: liveness/readiness viven en SU router, FUERA del presupuesto de peticiones en vuelo
    // que lleva la superficie de negocio (más abajo). Un chequeo de salud que reciba un `503` bajo
    // sobrecarga lo lee Swarm como «contenedor no sano» y reprograma el contenedor en plena punta
    // transitoria, convirtiendo la contrapresión en una caída real. Liveness ≠ readiness (hub#538):
    // `/healthz` dice si el proceso responde; `/readyz` dice si puede ATENDER, y es la que mira el
    // `HEALTHCHECK` del contenedor para decidir si revierte.
    let health = Router::new()
        .route("/healthz", get(healthz))
        .route("/readyz", get(readiness::readyz));
    let business = Router::new()
        // Un hub no se indexa (ver `with_noindex`). Va en el router de API, ANTES del
        // fallback SPA: sin esta ruta, `/robots.txt` devolvía `index.html` con un 200, que
        // un rastreador lee como «este sitio no tiene reglas».
        .route("/robots.txt", get(robots_txt))
        // El otro extremo del `report-uri` de la política (hub#1447). Sin sesión a propósito: lo
        // postea el NAVEGADOR cuando la CSP acaba de rechazar algo, y eso ocurre muy especialmente
        // en la pantalla de login, antes de que exista sesión alguna. Va dentro del shed de
        // negocio: si el hub está saturado, la caja cobra y el informe se cae, no al revés. El
        // límite de cuerpo es de dos órdenes de magnitud menos que el general: un informe de CSP
        // son cientos de bytes, y cuánto ocupa `script-sample` lo decide una página hostil.
        .route(
            "/csp-report/",
            post(csp_report::receive).layer(axum::extract::DefaultBodyLimit::max(16 * 1024)),
        )
        .route("/api/hub/context", get(hub_context))
        .route("/api/system", get(system::system_info))
        // Telemetría de recursos vs límites del plan (ADR-0154, hub#203). Sesión admin.
        .route("/api/system/metrics", get(system_metrics::system_metrics))
        // Series de uso (CPU/RAM/conexiones) para /system: proxy con caché al endpoint device
        // del SaaS (saas#1511) — el machine token vive en el runtime, nunca en el navegador.
        .route("/api/system/usage-series", get(usage_series::usage_series))
        // Qué le hemos cambiado a este hub y desde qué versión (hub#564). Solo lectura: la
        // contrapartida de actualizar sin preguntar (ADR-0269) es que se pueda SABER, no decidir.
        .route("/api/system/update-history", get(system::update_history))
        // The responsible declaration of THIS version, inside the product (art. 13.2 RRSIF —
        // hub#528). Projects the same `SistemaInformatico` block that travels in every record:
        // the producer facts the control plane serves + this binary's `Version` + the `hub_id`
        // as `NumeroInstalacion`. Never constants.
        .route(
            "/api/system/declaration",
            get(settings::get_responsible_declaration),
        )
        // Settings del hub (store key/value de sistema, tabla `hub_settings`). GET = cualquier
        // sesión de usuario; PUT = sesión admin (owner/admin). Contrato del frontend.
        .route(
            "/api/settings",
            get(settings::get_settings).put(settings::put_settings),
        )
        // Personal (core): los usuarios REALES del hub (`hub_user`) — incluido el owner, que entra
        // por Cloud y no tiene PIN. GET = cualquier sesión; alta/edición/baja = sesión admin. La
        // pantalla de Personal NO depende del módulo `staff` (que es otra cosa: profesional
        // reservable, comisiones, horarios). Ver `crate::hub_users`.
        .route(
            "/api/hub/users",
            get(hub_users::list_users).post(hub_users::create_user),
        )
        .route(
            "/api/hub/users/:id",
            axum::routing::put(hub_users::update_user).delete(hub_users::deactivate_user),
        )
        .route("/api/hub/roles", get(hub_users::list_roles))
        .route(
            "/api/hub/roles/:key",
            axum::routing::put(hub_users::set_role_activation),
        )
        // Modo del DISPOSITIVO (paso 2b, hub#357): `shared` (mostrador) vs `personal` (equipo
        // propio). GET = **sin sesión** (lo lee la pantalla de login, que es anterior a cualquier
        // sesión) y un dispositivo desconocido recibe `shared`; PUT = sesión **admin**, como
        // ajustes o el catálogo de roles. Ver `crate::device_mode`.
        .route(
            "/api/device/mode",
            get(device_mode::get_device_mode).put(device_mode::put_device_mode),
        )
        // Los dispositivos del negocio y el gesto «se me ha perdido la tablet» (hub#455). Las DOS
        // puertas exigen sesión **admin**, a diferencia de la de arriba: esta ENUMERA el negocio
        // entero (cuándo se usó cada dispositivo, cuánto le queda a su sesión), que es una lista de
        // la compra para quien tenga uno robado. Ver `crate::devices`.
        .route("/api/devices", get(devices::list_devices))
        // El `PUT` **nombra** el dispositivo (hub#494) y el `DELETE` lo corta: dos gestos con
        // consecuencias distintas, por eso son dos métodos y no un campo del mismo cuerpo.
        .route(
            "/api/devices/:device_id",
            axum::routing::delete(devices::revoke_device).put(devices::rename_device),
        )
        // Perfil del usuario autenticado. Sin `/:id`: solo permite leer/editar el propio.
        .route(
            "/api/profile",
            get(profile::get_profile).put(profile::put_profile),
        )
        .route(
            "/api/profile/avatar",
            get(profile::get_avatar)
                .post(profile::upload_avatar)
                .delete(profile::delete_avatar)
                .layer(axum::extract::DefaultBodyLimit::max(3 * 1024 * 1024)),
        )
        // Certificado fiscal del negocio (ADR-0079): recurso del hub, subido en Ajustes → Negocio.
        // Identidad fiscal hacia el SaaS (ADR-0201 7/11): la casilla «usar estos datos también
        // para mi factura de ERPlora». La llamada la hace el RUNTIME — el cloud_api_token nunca
        // cruza al navegador.
        .route(
            "/api/fiscal/representation-grant",
            get(representation_grant::get_representation_grant)
                .post(representation_grant::post_representation_grant)
                // 🔴 El límite por defecto de axum son 2 MB y aquí viajan hasta CUATRO documentos
                // escaneados (hub#1293): sin esto, el rechazo lo da el framework antes de llegar a
                // `validate` y la pantalla no tiene ningún código que enseñar.
                .layer(axum::extract::DefaultBodyLimit::max(
                    representation_grant::MAX_UPLOAD_BYTES,
                )),
        )
        // El modelo oficial pre-relleno, para imprimir y firmar a mano o firmar con AutoFirma
        // (hub#1293). Proxy puro hacia el SaaS, que es donde vive el texto: admin, como la subida.
        .route(
            "/api/fiscal/representation-grant/model",
            post(representation_grant::post_representation_grant_model),
        )
        // La salida a producción (hub#2079): la ÚNICA puerta a `production`, la del core, con todas
        // sus comprobaciones. La pantalla de VeriFactu la usa en vez de escribir su propia columna.
        .route(
            "/api/fiscal/go-live",
            get(settings::get_go_live)
                .post(settings::post_go_live)
                .delete(settings::delete_go_live),
        )
        .route(
            "/api/business/fiscal-identity",
            post(settings::publish_fiscal_identity),
        )
        .route(
            "/api/business/certificate",
            get(settings::get_business_certificate)
                .put(settings::put_business_certificate)
                .patch(settings::patch_business_certificate)
                .delete(settings::delete_business_certificate),
        )
        // Identidad de MÁQUINA para la pasarela fiscal (hub#1432): la clave nace en el hub y no
        // sale; el CSR viaja al operador y vuelve firmado con la CA interna (ADR-0419).
        .route(
            "/api/business/gateway-identity",
            get(settings::get_gateway_identity).delete(settings::delete_gateway_identity),
        )
        .route(
            "/api/business/gateway-identity/csr",
            post(settings::post_gateway_identity_csr),
        )
        .route(
            "/api/business/gateway-identity/certificate",
            axum::routing::put(settings::put_gateway_identity_certificate),
        )
        // hub#1457: el alta ENTERA sin operador delante — el runtime presenta el CSR en el
        // expediente legal del hub (saas#1833) con su credencial de máquina y recoge el
        // certificado cuando una persona lo firma. La PANTALLA es del módulo `verifactu`; el
        // módulo no puede hacer esta llamada, que es justo por lo que la puerta vive aquí.
        .route(
            "/api/business/gateway-identity/enrol",
            post(settings::post_gateway_identity_enrol),
        )
        // Export/import del hub a blueprint (ADR-0113): capa server sobre el motor del runtime
        // (`export_hub`/`import_sections`). Auth = sesión admin (owner/admin), como /api/settings.
        // El inspect recibe el zip crudo → body limit propio (el default de axum son 2 MiB).
        .route("/api/hub/export", post(export_import::export_blueprint))
        // Lo que alimenta las casillas por tabla del formulario (hub#534): sin el recuento,
        // la lista es una fila de nombres que nadie sabe interpretar.
        .route("/api/hub/export/tables", get(export_import::export_tables))
        .route(
            "/api/hub/import/inspect",
            post(export_import::import_inspect).layer(axum::extract::DefaultBodyLimit::max(
                export_import::MAX_BLUEPRINT_BYTES,
            )),
        )
        .route("/api/hub/import", post(export_import::import_blueprint))
        // Reintento SOLO de lo que no entró (hub#845): deriva la selección del informe persistido,
        // vuelve a bajar la MISMA versión del catálogo y re-ejecuta. Lo ya aplicado no se duplica
        // (propiedad del motor: guardas por clave técnica hub#260 + clave natural ADR-0304).
        .route("/api/hub/import/retry", post(export_import::retry_import))
        // Reset del hub — volver a cero (ADR-0170): el espejo destructivo del export. Mismo gate
        // admin. El `plan` es dry-run (lo que la UI pinta antes de confirmar); el límite fiscal
        // (facturas remitidas a la AEAT) lo aplica el MOTOR, no esta capa.
        .route("/api/hub/reset/plan", post(reset::reset_plan))
        .route("/api/hub/reset", post(reset::reset_hub))
        // Lotes de importación (ADR-0170): listar qué trajo cada blueprint y deshacer uno sin
        // tocar lo que el usuario creó después.
        .route("/api/hub/import/batches", get(reset::import_batches))
        .route("/api/hub/import/undo", post(reset::undo_import_batch))
        // Último informe de importación persistido (hub#763): lo que el Dashboard anuncia y la
        // pestaña Datos recupera al montarse, para que la navegación no pierda el informe accionable.
        .route("/api/hub/import/report", get(reset::import_report))
        // Gestor de la carpeta `media/` (pantalla /files). Browse + raw + upload + delete + mkdir.
        .route(
            "/api/media",
            get(media::media_list).delete(media::media_delete),
        )
        .route("/api/media/raw", get(media::media_raw))
        // Where the app asks for the credential the BROWSER can attach on its own (hub#791): an
        // `<img src>` carries no header, so the read door above also takes a cookie. Read-only and
        // scoped by `Path` to that door — the writing routes below stay header-only.
        .route("/api/media/session", post(media::mint_media_session))
        .route("/api/media/upload", post(media::media_upload))
        .route("/api/media/folder", post(media::media_create_folder))
        .route("/api/media/rename", post(media::media_rename))
        .route("/api/media/move", post(media::media_move))
        .route("/api/navigation", get(navigation))
        .route("/api/modules", get(list_modules))
        .route("/api/modules/install", post(install_module))
        .route("/api/modules/request-install", post(request_install))
        // Qué versión ofrece hoy el marketplace para cada módulo instalado (hub#516). Bajo demanda:
        // lo pide la pantalla de Apps al abrirse, no un sondeo en bucle.
        .route("/api/modules/updates", get(list_module_updates))
        // Assets web de un módulo instalado (module.json + `dist/*.esm.js` + wasm/icons) servidos
        // desde la CACHÉ de descargas, resueltos por la VERSIÓN instalada. En Hub Cloud los módulos
        // se descargan en runtime al `module_cache` (NO se hornean en el `web_dir`), así que sin esta
        // ruta `/modules/**` caía al fallback SPA (`index.html`) y NINGÚN Web Component cargaba: toda
        // la UI de módulos quedaba muerta ("No se pudo cargar el módulo").
        // hub#935 — la MISMA ruta para todas las versiones era el defecto: el bundle de un módulo
        // actualizado llegaba a una url que las cachés (borde y navegador) ya tenían resuelta con
        // los bytes de la versión anterior, así que la pantalla seguía ejecutando el código viejo
        // sin ningún aviso. Con la versión en la RUTA (la query no vale: el borde la ignora para la
        // clave de caché) cada versión tiene una dirección que ninguna caché ha visto antes.
        .route("/modules/:id/v/:version/*path", get(serve_module_asset_at))
        .route("/modules/:id/*path", get(serve_module_asset))
        // Proxies hub-scoped al Cloud (el token de máquina se queda en el runtime, no en el navegador)
        .route("/api/entitlement", get(proxy_entitlement))
        // hub#2105: the SaaS hands the running hub its new entitlement after a plan change, so
        // the change lands now instead of on the daily tick or a restart. The RS256 signature is
        // the authentication (no session, no key); see `entitlement::push_refresh`.
        .route("/api/entitlement/refresh", post(entitlement::push_refresh))
        .route("/api/marketplace/catalog", get(proxy_marketplace_catalog))
        // «Connect WhatsApp» from the hub (hub#1600, ADR-0452): owner/admin session here, the
        // hub's machine credential towards the SaaS, which keeps the Meta token.
        .route(
            "/api/hub/whatsapp/config",
            get(whatsapp_connect::whatsapp_config),
        )
        .route(
            "/api/hub/whatsapp/numbers",
            get(whatsapp_connect::whatsapp_numbers),
        )
        .route(
            "/api/hub/whatsapp/connect",
            post(whatsapp_connect::whatsapp_connect),
        )
        .route(
            "/api/hub/whatsapp/disconnect/:phone_number_id",
            post(whatsapp_connect::whatsapp_disconnect),
        )
        // The templates the business promises Meta (hub#1610, saas#1899): same gate and same
        // machine credential as the four above. The module cannot call the SaaS itself — that
        // credential is a secret of the runtime (ADR-0003) — so this is its only way to Meta.
        .route(
            "/api/hub/whatsapp/templates",
            get(whatsapp_templates::whatsapp_templates)
                .post(whatsapp_templates::whatsapp_template_register),
        )
        .route(
            "/api/hub/whatsapp/templates/:name",
            axum::routing::delete(whatsapp_templates::whatsapp_template_delete),
        )
        // Qué dice el marketplace de UN módulo (hub#1134). El catálogo de arriba sólo trae lo que
        // se sigue OFRECIENDO, así que no puede contestar por un módulo que este hub corre y el
        // marketplace ha retirado — que es justo el que «Mis apps» tiene que poder marcar.
        .route(
            "/api/marketplace/modules/:id",
            get(proxy_marketplace_module),
        )
        // Which build of the installable app the Cloud publishes (hub#400). The page cannot ask
        // erplora.com itself: `connect-src 'self' ipc:` kills it, and silently.
        .route("/api/app/release", get(proxy_app_release))
        // Blueprints: «fuente nube» del import (Ajustes → Datos). ADR-0121.
        .route("/api/blueprints/catalog", get(proxy_blueprints_catalog))
        .route("/api/blueprints/:slug/download", get(download_blueprint))
        .route("/api/modules/:id/activate", post(activate_module))
        .route("/api/modules/:id/deactivate", post(deactivate_module))
        .route("/api/modules/:id/uninstall", post(uninstall_module))
        // Actualizar un módulo SIN reiniciar el contenedor (hub#675/hub#516). Es la pieza que
        // faltaba: hasta ahora un fix de módulo esperaba a que saliera una imagen nueva del hub,
        // porque los módulos solo se recogen al arrancar y el rollout excluye a quien ya está en la
        // imagen. Es también el botón «Actualizar» del dueño, y con `{"version": "…"}` la palanca de
        // soporte.
        .route("/api/modules/:id/update", post(update_module))
        .route("/api/modules/:id/versions", get(list_module_versions))
        .route(
            "/api/modules/:id/capabilities",
            get(settings::get_module_capabilities).put(settings::put_module_capabilities),
        )
        .route("/api/query", post(query))
        .route("/api/command", post(command))
        // Qué NOMBRES aceptan las dos rutas de arriba (hub#1757). Los nombres son de cada módulo
        // instalado, así que ningún fichero del repo puede listarlos: el hub los sabe y no los
        // decía, y quien no tenía el `module.json` delante solo podía adivinar y cosechar 404.
        // Nunca anuncia lo que el dispatcher rechazaría (interno, módulo apagado). Misma doble
        // puerta que `…/events`: sesión admin + `manage_flows` si quien llama nombra un módulo —
        // el mapa de todas las puertas del hub no lo lee un módulo por estar un admin logueado.
        .route(
            "/api/hub/operations",
            get(operations_catalog::list_operations),
        )
        // hub#361: the manager approves ONE action. The PIN is verified in the runtime, and the
        // token that comes back is presented on the retry in `X-Elevation-Token` — never in the
        // command payload, so a command body stays pure data.
        .route("/api/elevation/approve", post(elevation::approve))
        // ── Print queue of the hub (ADR-0196 §6, hub#341) ───────────────────────────────────
        // Enqueue `{jobId, role, html}` (idempotent by `jobId`) and observe the queue. Drenarla
        // por el WS del runtime es hub#343. Auth = sesión de usuario.
        .route(
            "/api/print/jobs",
            get(print::list_jobs).post(print::enqueue_job),
        )
        // Sacar del atasco UN trabajo (hub#1108): devolverlo a la cola o retirarlo. Sesión
        // **admin** (+ capability `printer` si quien llama es un módulo): leer la cola es
        // cualquier sesión —quien está al lado de la impresora—, pero tirar un tique a la basura o
        // volver a lanzarlo es el gesto del dueño, con el precedente del CRUD de estaciones.
        // Descartar NUNCA borra: la fila queda sellada con quién, cuándo y por qué.
        .route("/api/print/jobs/:job_id/retry", post(print::retry_job))
        .route("/api/print/jobs/:job_id/discard", post(print::discard_job))
        // ── Registro de HOSTS de impresión (ADR-0196 §6, hub#342) ────────────────────────────
        // Quién drena cada rol. Un dispositivo se registra/late/se retira A SÍ MISMO (el sujeto es
        // su `X-Device-Id`, no hay parámetro para nombrar otro) → basta sesión de usuario: la app
        // tiene que poder hacerlo al arrancar. La excepción es retirar el dispositivo de OTRO
        // (la caja robada o sustituida), que pide sesión **admin**, como `/api/device/mode`.
        // El `live` NO se almacena: se deriva del último latido — un equipo apagado no escribe.
        .route(
            "/api/print/hosts",
            get(print::list_hosts)
                .post(print::register_host)
                .delete(print::retire_host),
        )
        .route("/api/print/hosts/heartbeat", post(print::host_heartbeat))
        // ── Estaciones de impresión, como FILAS (hub#457) ────────────────────────────────────
        // «Qué impresora imprime esto» deja de ser una cadena comparada literalmente y pasa a ser
        // una FILA con id: el mercado entero (Toast, Square, Lightspeed, Odoo, Simphony…) enlaza
        // ítem→estación←impresora por referencia, nunca por un texto tecleado al imprimir. Leer
        // basta sesión (el TPV ofrece los destinos); crear/renombrar/borrar es sesión **admin**,
        // como `/api/keys`: define qué colas TIENE el negocio, no qué hace la caja de hoy.
        .route(
            "/api/print/stations",
            get(print::list_stations).post(print::create_station),
        )
        .route(
            "/api/print/stations/:id",
            axum::routing::patch(print::rename_station).delete(print::delete_station),
        )
        // El mapa `documentType → estación` (hub#987): el módulo dice QUÉ imprime, el hub DÓNDE sale.
        .route(
            "/api/print/routes",
            get(print::list_routes).put(print::set_route),
        )
        // Lo que NO se está drenando, para la campana. Sesión de usuario, no admin: quien está en
        // el mostrador es quien puede encender la caja y quien se va a quedar sin darle el tique.
        .route("/api/print/undrained", get(print::undrained_stations))
        // ── API pública por módulo (ADR-0057, public-api.md) ────────────────────────────────
        // Gestión de keys (auth = sesión admin owner/admin; NO una api key).
        .route(
            "/api/keys",
            get(api_keys::list_keys).post(api_keys::create_key),
        )
        .route("/api/keys/:id/rotate", post(api_keys::rotate_key))
        .route("/api/keys/:id", axum::routing::delete(api_keys::revoke_key))
        // ── Dead-letter del outbox, operable (hub#660 — ADR-0127 fase 2) ────────────────────
        // Misma puerta que la gestión de keys: sesión local de un humano owner/admin. Reintentar
        // re-ejecuta el command de otro módulo con la autoridad de ESE módulo (hub#686) y descartar
        // cierra un registro para siempre, así que NO se abren a una API key ni al token de máquina.
        .route("/api/hub/events/dead", get(outbox_admin::list_dead))
        .route("/api/hub/events/dead/count", get(outbox_admin::count_dead))
        .route(
            "/api/hub/events/discarded",
            get(outbox_admin::list_discarded),
        )
        .route(
            "/api/hub/events/retry-all",
            post(outbox_admin::retry_all_dead),
        )
        .route("/api/hub/events/:id/retry", post(outbox_admin::retry_dead))
        .route(
            "/api/hub/events/:id/discard",
            post(outbox_admin::discard_dead),
        )
        // Correlación (hub#666): qué disparó ESTE evento — los runs que arrancó y los eventos que
        // provocó su entrega. Misma puerta admin: el trace dibuja lo que hace el negocio entero.
        .route("/api/hub/events/:id/trace", get(outbox_admin::trace_event))
        // Catálogo de campos de un evento (hub#715): lo que el picker del editor de flujos ofrece.
        // Segmento estático de un solo tramo, así que no compite con `/:id/…`. Puerta admin **y**
        // capability `manage_flows` si quien llama es un módulo — lo que traen los eventos de un
        // negocio es la forma de ese negocio, y no la lee cualquier módulo instalado.
        .route("/api/hub/events/shape", get(outbox_admin::event_shape))
        // Catálogo de NOMBRES de evento (hub#823): la unión de lo que los módulos instalados
        // declaran y lo que el outbox vio de verdad — el desplegable «Cuando pase…» del editor de
        // flujos deja de sembrarse a mano. Solo nombres, nunca payloads; misma doble puerta que
        // `…/shape` (ADR-0312): sesión admin + `manage_flows` si quien llama nombra un módulo.
        .route("/api/hub/events", get(outbox_admin::list_events))
        // ── Kernel de automatización (ADR-0283 K7, hub#661) ────────────────────────────────
        // REST del core, NO commands `hub.*`: el core se congela y el dispatcher no es donde se
        // añade superficie nueva (§9). Misma puerta que las keys y la dead-letter: sesión local de
        // un humano owner/admin — `PUT …/grants` es la pantalla donde una persona decide qué puede
        // hacer el hub cuando no hay nadie mirando, y una credencial de integración copiable no
        // decide eso (podría concederse a sí misma todo el hub a través de un flujo).
        //
        // ⚠️ `/flows/runs/:run_id` va ANTES de `/flows/:id/...` en este `Router` solo por
        // legibilidad: matchit resuelve el segmento estático `runs` con prioridad sobre el
        // parámetro `:id`, y `tests/flows_api_test.rs` lo comprueba contra el router de verdad.
        .route(
            "/api/hub/flows",
            get(flows_api::list_flows).post(flows_api::create_flow),
        )
        .route("/api/hub/flows/runs/:run_id", get(flows_api::get_run))
        // `schema` is a static segment too (hub#716): the contract the editor builds its UI from,
        // served by the hub instead of copied into every module's bundle. It goes here for the
        // same reason as `runs` — matchit resolves the static segment ahead of `:id`, and
        // `tests/flows_schema_route.rs` checks it against the real router.
        .route("/api/hub/flows/schema", get(flows_api::get_schema))
        // `templates` — las automatizaciones de fábrica de los módulos instalados (hub#1611).
        // Mismo caso que `schema` y `secrets`: segmento estático, gana al `:id` de abajo, y
        // `tests/flow_templates_route.rs` lo comprueba contra el router real — si algún día se
        // colara por `:id`, la respuesta sería «no existe ese flujo» en vez de la lista.
        .route("/api/hub/flows/templates", get(flows_api::list_templates))
        // Y encenderlas en un toque (hub#1677, ADR-0470). Van aquí, con el resto de `templates`,
        // por el mismo motivo: `templates` es estático y matchit lo resuelve antes que el `:id` de
        // abajo. Puerta: sesión local de owner/admin, y NINGUNA capability nueva — si la petición
        // nombra un módulo, tiene que ser el de la ruta (`403 flow.template_not_yours`).
        .route(
            "/api/hub/flows/templates/:module/:family/activate",
            post(flows_api::activate_template),
        )
        .route(
            "/api/hub/flows/templates/:module/:family/deactivate",
            post(flows_api::deactivate_template),
        )
        // `secrets` es igual: segmento estático, gana al `:id` (hub#662). El GET devuelve NOMBRES —
        // no hay endpoint que devuelva un secreto, y esa ausencia es el diseño (ADR-0283 §4).
        .route("/api/hub/flows/secrets", get(flows_api::list_secrets))
        .route(
            "/api/hub/flows/secrets/:name",
            axum::routing::put(flows_api::put_secret).delete(flows_api::delete_secret),
        )
        .route(
            "/api/hub/flows/:id",
            get(flows_api::get_flow)
                .put(flows_api::update_flow)
                .delete(flows_api::delete_flow),
        )
        .route(
            "/api/hub/flows/:id/grants",
            get(flows_api::list_grants).put(flows_api::replace_grants),
        )
        .route("/api/hub/flows/:id/run", post(flows_api::start_run))
        .route("/api/hub/flows/:id/runs", get(flows_api::list_runs))
        // ── Bandeja de aprobación (ADR-0283 D3, hub#665) ───────────────────────────────────
        // `approvals` es un segmento ESTÁTICO y matchit lo resuelve con prioridad sobre `:id`, así
        // que no se lo come `/flows/:id` aunque vaya después (igual que `/flows/runs/:run_id`);
        // `tests/agent_runner_test.rs` lo comprueba contra el router de verdad.
        // Misma puerta que el resto: sesión local de un humano owner/admin. Aquí es lo esencial —
        // esta fila ES el registro de una persona autorizando al hub a escribir sin nadie
        // delante, así que `decided_by` sale de la sesión resuelta y JAMÁS del body.
        .route("/api/hub/flows/approvals", get(flows_api::list_approvals))
        .route(
            "/api/hub/flows/approvals/:id/approve",
            post(flows_api::approve),
        )
        .route(
            "/api/hub/flows/approvals/:id/reject",
            post(flows_api::reject),
        )
        // ── The owner's rules (hub#1701, ADR-0476) ─────────────────────────────────────────
        // Core REST and not `hub.*` commands, for the same reason as the flows (ADR-0283 §9): a rule
        // is not a module's data, it is the hub's own configuration.
        //
        // Door = the local session of a human owner/admin, NEVER an API key nor the machine token: a
        // rule decides whether a sale can be charged, and a copyable integration credential does not
        // decide that. And with no module capability — there is no SDK surface to open here.
        //
        // 🔴 `checkpoints` goes BEFORE `/policies/:id`: it is a STATIC segment and matchit resolves
        // it with priority over the parameter, so served by `:id` it would answer «there is no such
        // rule» and the owner's screen would be left with no places to offer.
        // `tests/policies_api_test.rs` checks this against the real router.
        .route(
            "/api/hub/policies",
            get(policies_api::list_policies).post(policies_api::create_policy),
        )
        .route(
            "/api/hub/policies/checkpoints",
            get(policies_api::list_checkpoints),
        )
        .route(
            "/api/hub/policies/:id",
            get(policies_api::get_policy)
                .put(policies_api::update_policy)
                .delete(policies_api::delete_policy),
        )
        // Superficie de datos (auth = Auth::ApiKey, capa A genérica). Doble puerta `expose_api`.
        .route("/api/v1/:module/q/:query", post(api_keys::data_query))
        .route("/api/v1/:module/c/:command", post(api_keys::data_command))
        // OpenAPI 3.1 dinámico per-hub, **gateado por sesión de usuario** (interno, no público —
        // ADR-0057 §4 refinado 2026-06-24). El Swagger UI YA NO lo sirve el server: lo renderiza una
        // vista Vue interna del Hub (`apps/web/ApiDocsPage.vue`, `swagger-ui-dist` de npm) que pide
        // este spec con el fetch autenticado del web app (`X-Hub-Session`).
        .route("/api/v1/openapi.json", get(openapi::openapi_json))
        // Reporte de errores del FRONTEND (same-origin, sin auth cloud): el web app postea sus
        // errores JS aquí y el runtime los funnelea al registro global → Cloud (el secreto de
        // máquina nunca toca el navegador). Ver `frontend_error_report`.
        // hub#963 — the public door. `/p/:locator` is the only path in this router that answers
        // somebody with NO session: the diner holding a ticket. Its authorisation is the locator
        // itself (`public_door`), and the mint below is the session-gated side of the same pair.
        .route(
            "/p/:locator",
            get(public_door::show).post(public_door::redeem),
        )
        // sales#335 — the one script `/p/:locator` may load; must equal `NAMES_SCRIPT_PATH`.
        .route("/p/-/country-names.js", get(public_door::names_script))
        .route("/api/hub/public-claims", post(public_door::mint_claim))
        .route("/api/error-report", post(frontend_error_report))
        .route("/api/auth/pin", post(auth_pin))
        .route("/api/auth/badge", post(auth_badge))
        .route("/api/auth/set-pin", post(auth_set_pin))
        .route("/api/auth/cloud", post(auth_cloud))
        .route("/api/auth/courier", post(auth_courier))
        .route("/api/auth/logout", post(auth_logout))
        // The door to erplora.com from the till (pm#196, hub#1400): trades the hub session for a
        // one-time address that opens the SaaS session in the system browser. Only for whoever
        // typed their password, not for a shift PIN — see `auth_handoff`.
        .route("/api/auth/handoff", post(auth_handoff))
        // ── Gestión de usuarios-login del Hub (identidad, ADR-0157 §7 / checklist core #2) ──────
        // Alta/baja/listado de quién puede ENTRAR en el hub. Gate owner/admin (sesión, NO api key).
        // Cada alta/baja crea/desactiva el `hub_user` local Y notifica al SaaS (`members`). NO es
        // `staff.*` (negocio): es identidad.
        .route(
            "/api/members",
            get(members::list_members).post(members::add_member),
        )
        .route(
            "/api/members/:email",
            axum::routing::delete(members::remove_member),
        )
        .route("/api/assistant/chat/stream", post(assistant_chat_stream))
        // Report of inappropriate AI-generated content (Microsoft Store policy 11.16, hub#946):
        // any signed-in hub user; funneled into the global error registry (ADR-0052) → Cloud.
        .route("/api/assistant/report", post(assistant_report::report))
        // El plan del asistente y su checkout, por el runtime (saas#1540). Van AQUÍ y no desde el
        // navegador porque la credencial hub-scoped es secreto del runtime (ADR-0003): el web app
        // no tiene —ni debe tener— con qué firmar estas llamadas.
        .route("/api/assistant/config", get(assistant_config))
        .route("/api/assistant/checkout", post(assistant_checkout))
        // The EVENT channel (hub#504): needs an API key of this hub that may read. See
        // `event_stream` — the credential travels in the header, in the first frame (`/ws`) or as
        // a single-use ticket (`/api/events`), never as a long-lived secret in the URL.
        .route("/ws", get(event_stream::upgrade))
        // El canal del HOST DE IMPRESIÓN (ADR-0196 §6, hub#343): el primer WS cliente→servidor del
        // hub. Ruta propia y no un frame más de `/ws` porque su contrato es otro — por `/ws/print`
        // viaja el DOCUMENTO del tique y exige sesión + registro de host, mientras que `/ws` es un
        // fan-out de eventos de dominio a cualquier key con lectura.
        .route("/ws/print", get(print_ws::upgrade))
        // SSE: alternativa a /ws para el MISMO canal de eventos (hub#19). Se suscribe al mismo
        // `AppState.events` (broadcast, N suscriptores), así que no duplica el fan-out. Da gratis
        // reconexión del navegador (EventSource) + keep-alive (idle timeout del ALB). Nombre de
        // ruta = decisión del humano (`/api/events` por defecto).
        .route("/api/events", get(event_stream::sse))
        // Where the app asks for its credential for the channel (session → single-use ticket).
        .route("/api/events/ticket", post(event_stream::mint_ticket));
    // hub#1401: acota el trabajo de negocio en vuelo y suelta el exceso como un `503` inmediato con
    // `Retry-After` (ver [`with_load_shedding`]), en lugar de encolarlo hasta que el origen se
    // satura y Cloudflare responde `502`. `/healthz` y `/readyz` quedan fuera a propósito (arriba).
    // El shed va POR DENTRO del `TraceLayer` de abajo, así que un `503` soltado también se registra
    // (queda VISIBLE, no es un fallo mudo).
    let business = with_load_shedding(business, max_inflight_from_env());

    health
        .merge(business)
        // Log de cada request (verbo/ruta/estado/latencia) a INFO → consola + `media/_logs/`
        // (ADR-0047): la primera población real de la carpeta media. La respuesta se loguea a INFO;
        // los fallos del propio servidor a ERROR.
        .layer(
            tower_http::trace::TraceLayer::new_for_http()
                .on_response(
                    tower_http::trace::DefaultOnResponse::new().level(tracing::Level::INFO),
                )
                .on_failure(
                    tower_http::trace::DefaultOnFailure::new().level(tracing::Level::ERROR),
                ),
        )
        // Marca de actividad de usuario (`crate::activity`): una petición autenticada y aceptada
        // significa que alguien está usando este hub. Viaja al Cloud en el heartbeat de
        // `daily_usage`, que apaga (60d) y acaba borrando (120d) los hubs free que nadie usa.
        .layer(axum::middleware::from_fn_with_state(
            activity_state,
            track_user_activity,
        ))
        // Primera barrera del runtime: una máquina real sin UUID+credencial Cloud solo puede
        // consultar salud/contexto para pintar el login. Demo es la única excepción.
        .layer(axum::middleware::from_fn_with_state(
            registration_state,
            require_machine_registration,
        ))
        .with_state(state)
}

/// La versión que debe correr un módulo en este arranque (hub#516).
///
/// Delega en [`install::resolve_target`] — **el mismo resolutor que usa el botón «Actualizar»** y
/// que `/api/modules/updates`. Una segunda copia de esta decisión sería una segunda política: la
/// automática y la manual acabarían ofreciendo cosas distintas.
pub(crate) async fn resolve_module_target(
    state: &AppState,
    machine: &cloud_client::Auth,
    module_id: &str,
    installed: &str,
    pinned: Option<&str>,
) -> erplora_runtime::module_update::Target {
    install::resolve_target(
        &state.http,
        &state.config.cloud_base_url,
        machine,
        module_id,
        installed,
        pinned,
    )
    .await
}

pub(crate) async fn healthz() -> &'static str {
    "ok"
}

/// Anota que **alguien está usando** este hub (ver `crate::activity`).
///
/// Punto ÚNICO a propósito: cada handler resuelve la auth a su manera (sesión, API key, token de
/// máquina), y colgar la marca de cada uno se desincronizaría al añadir el siguiente. Aquí se ve
/// lo que importa — llevaba credencial y no se rechazó — sin tocar ninguna firma.
///
/// Coste por petición: leer una cabecera y un `fetch_max` atómico. Ninguna escritura a disco.
pub(crate) async fn track_user_activity(
    State(activity): State<std::sync::Arc<crate::activity::ActivityState>>,
    request: axum::extract::Request,
    next: Next,
) -> Response {
    let has_credential = auth::session_token(request.headers()).is_some()
        || auth::api_key_token(request.headers()).is_some();
    let response = next.run(request).await;
    if crate::activity::is_user_activity(has_credential, response.status().as_u16()) {
        activity.touch(entitlement::now_unix());
    }
    response
}

/// Bloquea toda la superficie de negocio hasta completar el registro de la máquina. El login
/// email/password inicial va directamente al SaaS; después Tauri adopta `hub_id + token` y vuelve
/// a consultar `/api/hub/context`, que ya pasa esta barrera.
pub(crate) async fn require_machine_registration(
    State(st): State<AppState>,
    request: axum::extract::Request,
    next: Next,
) -> Response {
    let path = request.uri().path();
    // `/p/...` (hub#963) is in the allow-list for the same reason the three above are: the person
    // on the other side is a CUSTOMER holding a printed ticket. They cannot enrol a device, and a
    // hub that already put a locator on paper has to honour it whatever state its enrolment is in.
    // `/csp-report/` (hub#1447) está en la lista por lo mismo que `/healthz`: quien postea no es
    // un usuario del negocio sino el NAVEGADOR, que no puede enrolar nada. Y un hub a medio
    // enrolar es justo el estado donde una política rota es más probable: dejar que la barrera se
    // coma esos informes sería un fallo mudo dentro del arreglo contra los fallos mudos.
    if matches!(
        path,
        "/healthz" | "/readyz" | "/api/hub/context" | "/csp-report/"
    ) || public_door::is_public_path(path)
        || st.is_dev_hub()
        || st.machine_registered()
    {
        return next.run(request).await;
    }
    (
        StatusCode::PRECONDITION_REQUIRED,
        Json(json!({
            "ok": false,
            "error": {
                "code": "machine_registration_required",
                "message": "este dispositivo debe registrarse con el Cloud antes de usar el Hub"
            }
        })),
    )
        .into_response()
}

/// Envuelve el router de API para servir el frontend estático (el `dist/` de Vite) con **fallback
/// SPA** a `index.html`: las rutas de API (`/api/*`, `/ws`, `/healthz`) las resuelve el router; el
/// resto cae al `ServeDir`, y las rutas del router SPA cliente (sin fichero en disco) sirven el
/// `index.html`. Para el combo cloud + web-PWA (§3).
pub fn with_static_frontend(router: Router, web_dir: &str) -> Router {
    use tower_http::services::{ServeDir, ServeFile};
    let index = format!("{}/index.html", web_dir.trim_end_matches('/'));
    router.fallback_service(ServeDir::new(web_dir).fallback(ServeFile::new(index)))
}

/// `X-Robots-Tag: noindex` en TODAS las respuestas del hub + `/robots.txt`.
///
/// Un hub es la caja de un cliente: **nunca** se indexa. No es una preferencia de SEO —
/// `{slug}.erplora.com` dice quién es el cliente, la portada dice qué módulos tiene instalados, y
/// detrás hay un login de un TPV real. Y no hay nada que ganar en el otro platillo: ninguna página
/// de un hub es un resultado de búsqueda que queramos.
///
/// Dos capas porque tapan agujeros distintos: el `robots.txt` es para el rastreador que pregunta,
/// y la cabecera para el que no —y para la URL que un `robots.txt` no sabe describir, como un
/// enlace profundo que alguien pegó en una issue pública—. `noarchive` va porque una copia
/// cacheada de una pantalla de caja no debe sobrevivir a la pantalla.
///
/// La tercera capa vive en `apps/web/index.html` (meta `robots`), que es la copia del documento
/// que esta capa NO cubre: la que va empaquetada dentro de la app instalada. Contrato completo en
/// `crates/server/tests/never_indexed.rs`.
pub(crate) const ROBOTS_TAG: &str = "noindex, nofollow, noarchive";

/// Cuerpo del `robots.txt` de un hub: sin `Allow`, sin `Sitemap`, sin excepciones.
pub(crate) const HUB_ROBOTS_TXT: &str = "User-agent: *\nDisallow: /\n";

pub(crate) async fn robots_txt() -> impl axum::response::IntoResponse {
    (
        [(
            axum::http::header::CONTENT_TYPE,
            "text/plain; charset=utf-8",
        )],
        HUB_ROBOTS_TXT,
    )
}

/// Añade la cabecera a lo que salga del router — incluidos los 404 y el fallback SPA, que son
/// justo las respuestas que una capa montada «por ruta» se dejaría fuera.
pub fn with_noindex(router: Router) -> Router {
    router.layer(tower_http::set_header::SetResponseHeaderLayer::overriding(
        axum::http::HeaderName::from_static("x-robots-tag"),
        HeaderValue::from_static(ROBOTS_TAG),
    ))
}

/// Añade el header `Content-Security-Policy` a TODAS las respuestas (ADR-0050). La CSP de
/// `tauri.conf` **no** aplica a este documento —solo la inyecta el protocolo de assets de Tauri, y
/// la ventana de la app instalada navega a ESTE servidor (ADR-0159)—, así que el runtime es el
/// único que puede emitirla. En las respuestas de API el header es inocuo.
///
/// El valor sale siempre de [`resolve_csp`]: [`default_csp`] salvo que `HUB_CSP` lo sustituya. La
/// mención a un `embedded_serve_config` y a un `None` que había aquí quedó obsoleta: el runtime
/// embebido del shell ya no existe, y desde hub#708 tampoco existe el caso «sin política».
pub fn with_csp(router: Router, csp: &str) -> Router {
    use axum::http::header::CONTENT_SECURITY_POLICY;
    // No abortar el arranque por una CSP mal formada (un salto de línea, un byte no-ASCII), pero
    // TAMPOCO servir sin política: se cae a la de por defecto y se avisa. `resolve_csp` ya filtra
    // el camino de `HUB_CSP`; esto cubre a cualquier otro llamador. Servir sin header era la rama
    // que dejó a la flota entera sin CSP (hub#708), así que aquí ya no existe.
    let value = HeaderValue::from_str(csp).unwrap_or_else(|e| {
        eprintln!("CSP inválida ({e}): se sirve la política por defecto en su lugar");
        HeaderValue::from_str(&default_csp("")).expect("la CSP por defecto siempre es un header")
    });
    router.layer(tower_http::set_header::SetResponseHeaderLayer::overriding(
        CONTENT_SECURITY_POLICY,
        value,
    ))
}

/// El router que monta [`serve`] de verdad: API + (opcional) front estático + la CSP, que **no** es
/// opcional. Extraído por el mismo motivo que [`build_router`] en su día: para poder afirmar sobre
/// la composición REAL sin bindear un puerto. Que la cabecera no dependa de una rama `if let` es el
/// contrato que fija `crates/server/tests/cloud_csp.rs`.
pub fn build_serving_router(state: AppState, web_dir: Option<&str>, csp: &str) -> Router {
    with_noindex(with_csp(build_router(state, web_dir), csp))
}

/// Compone el router de API (`app`) con, opcionalmente, el frontend estático servido en el **MISMO
/// origen** (ADR-0050). Es el camino REAL que monta tanto [`serve`] (ECS/binario, desde `HUB_WEB_DIR`)
/// como el runtime embebido del shell Tauri (Hub Local, desde `resource_dir()`), extraído aquí para
/// poder testearlo sin bindear puerto (`tower::ServiceExt::oneshot`). `web_dir = Some` ⇒ front + API
/// en un solo router; `None` ⇒ solo API (dev con Vite, que proxya).
pub fn build_router(state: AppState, web_dir: Option<&str>) -> Router {
    match web_dir.filter(|s| !s.is_empty()) {
        Some(dir) => with_static_frontend(app(state), dir),
        None => app(state),
    }
}

/// GET /api/hub/context — el `hub_id` inyectado por el despliegue (env `HUB_ID`) + el usuario
/// activo (hoy `null`; el frontend resuelve la sesión por separado) + `pin_users`: usuarios activos
/// con PIN del hub, para que el shell muestre el grid de login local directamente (sin depender de
/// un flag en localStorage) + `business_type`/`sector`: el sector del hub (env `HUB_SECTOR`) para
/// que el dashboard derive el preset "Recomendado" de widgets (ADR-0054) + `currency`/`language`:
/// settings del hub (tabla `hub_settings` ∪ defaults), lectura barata en el arranque del SPA para no
/// pegar a `/api/settings` por separado. Contrato del frontend.
pub(crate) async fn hub_context(State(st): State<AppState>) -> Response {
    let hub_id = st.hub_id();
    // El primer login Tauri puede haber adoptado el UUID real después de arrancar Axum. Antes de
    // abrir la sesión local reconciliamos el Runtime y aplicamos las migraciones scoped del nuevo
    // Hub. Es idempotente y convierte este endpoint de boot en la barrera de consistencia.
    let runtime = match st.runtime_for(&hub_id).await {
        Ok(runtime) => runtime,
        Err(error) => return tenant_rejected(error),
    };
    // Lee pin_users + settings en un único lock del runtime (lectura de arranque, sin gate).
    let (pin_users, currency, currency_decimals, language, timezone, pin_length) = {
        let rt = runtime.read().await;
        if let Err(error) = rt.ensure_system_tables().await {
            return err_response(error);
        }
        let pin_users: Vec<Value> = rt
            .list_pin_users()
            .await
            .unwrap_or_default()
            .into_iter()
            .map(|(id, name, role)| json!({ "id": id, "name": name, "role": role }))
            .collect();
        // Settings del hub: si la lectura falla (no debería), cae a los defaults del contrato para
        // no romper el arranque del SPA.
        let settings = rt.get_settings().await.unwrap_or_else(|_| json!({}));
        let currency = settings
            .get("currency")
            .cloned()
            .unwrap_or_else(|| json!("EUR"));
        // Los DECIMALES de la moneda (ADR-0123 §7). El front los necesita para las dos fronteras
        // (teclear y pintar): el dinero viaja en UNIDADES MÍNIMAS, y cuántas hay en una unidad mayor
        // depende de la moneda — EUR 2, **JPY 0**, KWD 3. Un `/100` clavado en el front cobra 100
        // veces mal en un hub en yenes.
        //
        // Precedencia: lo que el hub declare a mano (`currency_decimals`, para monedas que el
        // registro no conoce) → el registro ISO-4217 → el default explícito.
        let currency_decimals = settings
            .get("currency_decimals")
            .and_then(|v| v.as_i64())
            .map(|n| n as u32)
            .unwrap_or_else(|| {
                erplora_runtime::settings::decimals_of(currency.as_str().unwrap_or("EUR"))
            });
        let language = settings
            .get("language")
            .cloned()
            .unwrap_or_else(|| json!("es"));
        // La zona horaria del negocio ya RESUELTA (hub#731). En `settings` la clave viaja cruda
        // (`null` = «dedúcela del país») porque tiene que poder volver por un `PUT`; aquí se
        // expone el nombre IANA real, que es lo que la UI necesita para enseñar a qué hora local
        // se va a disparar un flujo. Si la lectura falla, UTC — que es lo que el reloj hará.
        let timezone = rt
            .timezone_name()
            .await
            .unwrap_or_else(|_| "UTC".to_string());
        // How many DIGITS this hub's PIN has (hub#974): 4 or 6. It travels here because the screen
        // that needs it —the login pinpad— is the only one with NO session, and `/api/settings`
        // demands one: without this key the shell fell back to its own default and painted four
        // circles on a six-digit hub, firing the login with a truncated PIN on the fourth digit
        // (hub#1765).
        //
        // No re-check against `PIN_LENGTHS` here on purpose: `get_settings` is `settings::get_all`,
        // which already degrades a row that no longer validates to that key's default, so a length
        // nobody can type cannot get this far. The fallback below is for the other case — settings
        // unreadable, `json!({})` above — where there is no value at all.
        let pin_length = settings
            .get(erplora_runtime::pin_policy::PIN_LENGTH_SETTING)
            .and_then(|v| v.as_i64())
            .unwrap_or(erplora_runtime::pin_policy::DEFAULT_PIN_LENGTH);
        (
            pin_users,
            currency,
            currency_decimals,
            language,
            timezone,
            pin_length,
        )
    };
    // Sector del hub: el frontend lee `sector ?? business_type` (alias), así que emitimos ambas
    // claves con el mismo valor. `None` → `null` (degradación elegante: el board no aplica preset).
    let sector = st.config.sector.clone();
    // Demo/Dev es la única excepción al registro obligatorio. En cualquier runtime real se exige
    // tanto UUID Cloud como credencial de máquina; nunca se expone el secreto al navegador.
    let demo = st.is_dev_hub();
    let machine_registered = st.machine_registered();
    Json(json!({
        "hub_id": hub_id,
        "user": Value::Null,
        "pin_users": pin_users,
        "demo": demo,
        // ⚠️ NO es `demo`. Esa clave lleva años significando **modo `dev`** y el SPA la usa para
        // el fallback de login por PIN (`runtime.ts` → `config.demo`): cambiarle el sentido sería
        // abrir ese fallback en cada demo pública. Esta es la DEMO EFÍMERA de ADR-0197: el hub
        // real de una hora que el visitante prueba sin registrarse. La UI la lee para EXPLICAR
        // los cierres de hub#376 (entorno fiscal clavado, certificado e identidad congelados)
        // en vez de dejar un 409 sin contexto.
        "ephemeral_demo": st.config.demo,
        "machine_registered": machine_registered,
        "registration_required": !demo && !machine_registered,
        "public_key_loaded": st.config.jwt_public_key.is_some(),
        // Which Cloud this hub belongs to (hub#1164): the same `HUB_CLOUD_API_URL` the CSP
        // `connect-src` is built from. The web app resolves its Cloud base URL from here at boot
        // instead of a build-time constant, so one image serves pre and prod alike. Empty when no
        // Cloud is configured (dev binary): the shell then keeps its build-time fallback.
        "cloud_base_url": st.config.cloud_base_url,
        "business_type": sector,
        "sector": sector,
        // Settings de arranque (tabla `hub_settings` ∪ defaults). El SPA los usa para formato de
        // moneda + locale sin un fetch extra a `/api/settings`.
        "currency": currency,
        // Cuántos decimales tiene esa moneda. El front NO puede asumir 2 (ADR-0123 §7).
        "currency_decimals": currency_decimals,
        "language": language,
        // Nombre IANA del reloj del NEGOCIO (hub#731) — resuelto, nunca `null`.
        "timezone": timezone,
        // Cuántos dígitos pide el PIN de este hub (hub#974). El pinpad del LOGIN lo lee de aquí:
        // es la única lectura que puede hacer sin sesión (hub#1765).
        "pin_length": pin_length,
    }))
    .into_response()
}
