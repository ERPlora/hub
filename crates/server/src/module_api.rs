//! Module install/update/version/asset HTTP handlers — split out of `lib.rs` verbatim (hub#1404).

use crate::*;

#[derive(Deserialize)]
pub(crate) struct RequestInstallReq {
    module_id: String,
    #[serde(default)]
    version: String,
}

/// POST /api/modules/request-install — flujo real Cloud→descarga→runtime (ARQUITECTURA.md §2.2).
/// Auth = JWT del usuario + `X-Hub-Id` de las cabeceras. Tras instalar, emite el evento
/// `module.installed` por `/ws` y prepara la ingestión de embeddings (vía Cloud, pendiente §9.3).
pub(crate) async fn request_install(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<RequestInstallReq>,
) -> Response {
    // La credencial de máquina sirve para que ESTE Hub hable con Cloud, no para autorizar al
    // navegador. Exigimos primero la sesión local de un owner/admin: de lo contrario cualquier
    // módulo web same-origin podría disparar instalaciones usando indirectamente el token del Hub.
    {
        let rt = st.runtime.read().await;
        if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }
    // Hub-scoped: token de máquina si el hub está enrolado; si no, JWT del usuario.
    let Some(auth) = auth::hub_scoped_auth(&headers, &st) else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": "hub sin credencial (ni token de máquina ni Authorization: Bearer)" })),
        )
            .into_response();
    };

    // Progreso por fases → WS `module.install.progress` (feedback visual del marketplace).
    // `module_id` = módulo en curso (puede ser una dep anidada); `root_id` = el pedido por el
    // usuario, para que el frontend actualice la card correcta aunque esté migrando una dep.
    let progress_state = st.clone();
    let root_id = req.module_id.clone();
    let on_progress = move |module_id: &str, phase: &str| {
        progress_state.broadcast(json!({
            "type": "module.install.progress",
            "module_id": module_id,
            "root_id": root_id,
            "phase": phase,
        }));
    };

    // hub#2508: no runtime lock while erplora.com answers and the zip downloads — only to register
    // it — so the till keeps charging on every device; `module_ops` serializes app changes.
    let _module_ops = st.module_ops.lock().await;
    let result = install::install_from_cloud(
        &st.marketplace_http,
        &st.config.cloud_base_url,
        &st.config.module_cache,
        &auth,
        &*st.runtime,
        &req.module_id,
        &req.version,
        &on_progress,
        &st.config.signature_policy(),
    )
    .await;

    match result {
        Ok(installed) => {
            let chunks =
                ingest::collect_chunks(st.runtime.read().await.registry(), &installed.module_id);
            drop(_module_ops);
            index_module_embeddings(&st, &auth, &installed.module_id, &installed.version, chunks)
                .await;

            // Evento WS con la forma exacta del contrato del frontend.
            st.broadcast(json!({ "type": "module.installed", "module_id": installed.module_id }));

            Json(json!({
                "ok": true,
                "module_id": installed.module_id,
                "version": installed.version,
                "status": "installed",
                // hub#1130: dependencies the install-plan/manifest resolution dragged in that
                // were NOT installed before this call. Always present — empty when nothing was
                // dragged in — so the caller never has to special-case the shape.
                "also_installed": installed.also_installed,
            }))
            .into_response()
        }
        Err(e) => {
            // Observabilidad (antes: 502 ciego sin log → invisible en Dokploy). Logueamos el error
            // real y mapeamos a un código honesto: un fallo instalando en el runtime (deps sin
            // satisfacer tras la resolución anidada = ciclo, migración, schema) NO es un 502 de
            // gateway. Así el operador distingue "fallo del Cloud/red" de "fallo instalando el módulo".
            tracing::error!(
                module_id = %req.module_id,
                requested_version = %req.version,
                error = %e,
                "request-install falló"
            );
            install_error_response(&e)
        }
    }
}

/// Ingestión de embeddings (§9.6): recoge el texto agéntico del módulo (`agent.description` +
/// `ai.description` de queries/commands), lo embebe **vía el proxy del Cloud** (§9.3 — el Hub nunca
/// llama a un proveedor de embeddings directamente) y lo registra en el índice vectorial para el
/// routing de tools (§9.2b).
///
/// Best-effort: un fallo aquí NO aborta nada (el módulo ya está instalado y operativo; el router
/// degrada a "todos"). Corre también tras un **update** (hub#516): la versión nueva puede describir
/// tools distintas, y un índice que se queda con el texto de la versión anterior enruta a ciegas.
pub(crate) async fn index_module_embeddings(
    st: &AppState,
    auth: &cloud_client::Auth,
    module_id: &str,
    version: &str,
    chunks: Vec<ingest::PendingChunk>,
) {
    if chunks.is_empty() {
        return;
    }
    let Some(store) = &st.vector else {
        tracing::info!(module_id = %module_id, chunks = chunks.len(), "sin índice vectorial; ingestión de embeddings omitida (§9.5)");
        return;
    };
    let embedder =
        embed::CloudEmbedder::new(st.http.clone(), &st.config.cloud_base_url, auth.clone());
    match embed::index_chunks(&embedder, store.as_ref(), &st.hub_id(), version, &chunks).await {
        Ok(n) => tracing::info!(module_id = %module_id, chunks = n, "embeddings indexados (§9.6)"),
        Err(e) => {
            tracing::warn!(module_id = %module_id, error = %e, "ingestión de embeddings falló (no crítico; router degrada)")
        }
    }
}

/// Optional body of `POST /api/modules/:id/update`. No `version` = **the latest**, the default
/// offer; with `version` = the one picked from the list, and only one the list would offer
/// (forwards, or the pin when support set one — hub#2546).
///
/// Elegir una versión concreta **no la clava**: el arranque siguiente vuelve a resolver la última
/// (ADR-0269 — nadie se queda atrás). Clavar es el **pin de soporte**, herramienta nuestra, y no se
/// toca desde aquí.
#[derive(Deserialize, Default)]
pub(crate) struct UpdateModuleReq {
    #[serde(default)]
    version: Option<String>,
}

/// **Actualiza un módulo sin reiniciar el contenedor** (hub#675 + hub#516).
///
/// Es lo que hace que un fix de módulo **no espere a una imagen nueva del hub**: los módulos solo se
/// recogían al arrancar, y `rollout_hub_fleet` excluye a los hubs que ya están en la imagen
/// objetivo, así que no había campaña que provocase el reinicio.
///
/// Va por [`install::update_from_cloud`] y **no** por `install_from_cloud`, y la diferencia no es
/// cosmética: con el plan del Cloud (ADR-0060) el módulo que ya está instalado viaja en el set
/// instalado, vuelve como `already_satisfied` y `execute_plan` lo **salta** — el update habría dicho
/// que sí sin descargar nada. La puerta de update lo excluye del set y no lo salta.
///
/// **Si la versión nueva falla, la anterior sigue puesta**, y por dos caminos que se componen: el
/// runtime repone en memoria lo que el módulo aportaba (hub#516, `Registry::snapshot_module`), y
/// encima `update_with_fallback` confirma reinstalando la que había. `Outcome::Lost` queda para lo
/// que de verdad lo es: que ni siquiera eso valga y el hub se quede sin el módulo.
///
/// Auth = **sesión local de admin** *más* credencial hub-scoped, igual que `request-install`. La
/// sesión no es un detalle: sin ella, cualquier módulo web same-origin podría disparar
/// actualizaciones usando indirectamente el token de máquina del hub.
pub(crate) async fn update_module(
    State(st): State<AppState>,
    Path(module_id): Path<String>,
    headers: HeaderMap,
    body: Option<Json<UpdateModuleReq>>,
) -> Response {
    use erplora_runtime::module_update::{update_with_fallback, Outcome};

    {
        let rt = st.runtime.read().await;
        if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }
    // Mismo motivo que en `proxy_marketplace_module` (hub#1134): este id acaba dentro de las URLs
    // del Cloud (`versions/`, `download/`) que se firman con el token de máquina.
    if !module_id_is_safe(&module_id) {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({
                "ok": false,
                "error": { "code": "module.invalid_id", "message": "invalid module id" },
            })),
        )
            .into_response();
    }
    let Some(auth) = auth::hub_scoped_auth(&headers, &st) else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": "hub sin credencial (ni token de máquina ni Authorization: Bearer)" })),
        )
            .into_response();
    };

    // hub#2508: one app change at a time, and no runtime lock while erplora.com answers.
    let _module_ops = st.module_ops.lock().await;
    // La versión que tiene ahora: es a la que hay que volver si la nueva falla.
    let installed = {
        let rt = st.runtime.read().await;
        rt.registry().module_version(&module_id)
    };
    if !st.runtime.read().await.registry().is_installed(&module_id) {
        return install_error_response(&install::InstallError::NotInstalled(module_id));
    }

    // Vacío / `latest` = lo que el resolutor decida (el MISMO del arranque: cuarentena y pin
    // mandan, nunca hacia atrás). Se resuelve AQUÍ, antes de tocar nada, porque el destino tiene que
    // ser una versión concreta: es la que se compara con la instalada para saber si hay algo que
    // hacer, y la que se reporta como `from → to`.
    let requested = body
        .map(|Json(b)| b)
        .unwrap_or_default()
        .version
        .unwrap_or_default();
    // hub#2546: an explicit version is held to the version list's rule (`module_update::offer`),
    // or typing it into the request walks around the support pin and goes backwards. Checked here,
    // at the administrator's door, and not in `resolve_update_target`: the rollback below and the
    // reconcile between copies (HUB-F26) pass explicit versions that are not anyone's choice.
    // hub#2596: the rule includes what erplora.com publishes — it leaves a quarantined version out
    // of `versions/`. It is asked only when the hub's own rule lets the version through and the
    // answer can change it (no pin, a real move), with the runtime released, like the version list
    // (hub#2508): a pin or a step back is still refused without a call. A list that cannot be read
    // is «I don't know», and then the plan and the download decide.
    let explicit = requested.trim();
    if !matches!(explicit, "" | "latest") {
        use erplora_runtime::module_update::may_request;
        let pinned = install::support_pin(&*st.runtime.read().await, &module_id).await;
        let mut allowed = may_request(&installed, pinned.as_deref(), explicit, None);
        if allowed && pinned.is_none() && explicit != installed {
            let published = install::listed_versions(
                &st.marketplace_http,
                &st.config.cloud_base_url,
                &auth,
                &module_id,
            )
            .await;
            allowed = may_request(&installed, None, explicit, published.as_deref());
        }
        if !allowed {
            return install_error_response(&install::InstallError::VersionNotOffered {
                module_id,
                version: explicit.to_string(),
            });
        }
    }
    let target = install::resolve_update_target(
        &st.marketplace_http,
        &st.config.cloud_base_url,
        &auth,
        &install::RuntimeAccess::from(&*st.runtime),
        &module_id,
        &requested,
    )
    .await;

    // Mismas fases que instalar (`resolving → downloading → verifying → installing`): la card del
    // catálogo ya sabe pintarlas, así que actualizar se ve igual de vivo que instalar.
    let progress_state = st.clone();
    let root_id = module_id.clone();
    let on_progress = move |current: &str, phase: &str| {
        progress_state.broadcast(json!({
            "type": "module.install.progress",
            "module_id": current,
            "root_id": root_id,
            "phase": phase,
        }));
    };

    // El fallo del PRIMER intento se guarda entero, no como texto: un plan `blocked` (dependencia
    // premium sin comprar) o un `NotInstalled` son decisiones que le tocan al usuario, con su código
    // y su puntero de compra — convertirlos en «no se pudo, sigues en la anterior» perdería la única
    // información accionable que llevan.
    let first_error: std::sync::Arc<std::sync::Mutex<Option<install::InstallError>>> =
        std::sync::Arc::new(std::sync::Mutex::new(None));

    // `update_with_fallback` compara `from`/`to` y decide la secuencia; la instalación real la pone
    // este closure. Pedir la versión de partida es barato: `update_from_cloud` ve `to == from` y no
    // descarga nada, así que la vuelta atrás confirma sin repetir trabajo.
    let outcome = update_with_fallback(&installed, &target, |version| {
        let st = st.clone();
        let auth = auth.clone();
        let module_id = module_id.clone();
        let on_progress = &on_progress;
        let first_error = first_error.clone();
        async move {
            let result = install::update_from_cloud(
                &st.marketplace_http,
                &st.config.cloud_base_url,
                &st.config.module_cache,
                &auth,
                &*st.runtime,
                &module_id,
                &version,
                on_progress,
                &st.config.signature_policy(),
            )
            .await;
            match result {
                Ok(_) => Ok(()),
                Err(e) => {
                    let message = e.to_string();
                    first_error.lock().unwrap().get_or_insert(e);
                    Err(message)
                }
            }
        }
    })
    .await;

    // Lo que el dueño verá mañana en Sistema → Actualizaciones (hub#564). Se anota AQUÍ, con el
    // resultado en la mano: el estado actual del hub no se puede restar de sí mismo para deducir
    // una transición, así que si no se escribe cuando ocurre, no existe. Misma decisión que el
    // arranque (`from_module_outcome`), y `AlreadyThere` no escribe nada porque no cambió nada.
    // Best-effort: no poder anotar el historial no convierte una actualización buena en un error.
    //
    // hub#2663: what is read from the registry is read here, still holding the turn, and then the
    // turn goes back — like installing does — because the version is in place (or the previous one
    // is back): the history line and the assistant's indexing (an erplora.com call of up to 60 s)
    // must not keep the next app change waiting.
    let (module_name, chunks) = {
        let rt = st.runtime.read().await;
        let module_name = rt
            .registry()
            .installed
            .iter()
            .find(|m| m.id == module_id)
            .map(|m| m.name.clone())
            .unwrap_or_else(|| module_id.clone());
        // The new version may describe different tools: an index left with the previous one's
        // texts routes blindly.
        let chunks = match outcome {
            Outcome::Updated { .. } => ingest::collect_chunks(rt.registry(), &module_id),
            _ => Vec::new(),
        };
        (module_name, chunks)
    };
    drop(_module_ops);
    {
        let rt = st.runtime.read().await;
        if let Some(change) = erplora_runtime::update_history::from_module_outcome(
            &module_id,
            &module_name,
            &target,
            &outcome,
        ) {
            if let Err(e) =
                erplora_runtime::update_history::record(rt.db(), &st.hub_id(), change).await
            {
                tracing::warn!(module_id = %module_id, error = %e, "no se pudo anotar el historial de actualización (hub#564)");
            }
        }
    }

    // Un fallo con decisión del usuario detrás (409 `install_blocked`, 404 `update_not_installed`)
    // se cuenta como lo que es, no como «no se pudo».
    if !matches!(outcome, Outcome::Updated { .. } | Outcome::AlreadyThere(_)) {
        if let Some(e) = first_error.lock().unwrap().as_ref() {
            if matches!(
                e,
                install::InstallError::Blocked { .. } | install::InstallError::NotInstalled(_)
            ) {
                return install_error_response(e);
            }
        }
    }

    match outcome {
        Outcome::AlreadyThere(version) => {
            Json(json!({ "ok": true, "data": { "module_id": module_id, "version": version, "updated": false } })).into_response()
        }
        Outcome::Updated { from, to } => {
            index_module_embeddings(&st, &auth, &module_id, &to, chunks).await;
            // Lo único que el dueño ve de toda la maquinaria (ADR-0269 §3.5): qué cambió y de qué
            // versión a cuál. `module.installed` va detrás porque es el evento que el shell YA
            // escucha (App.vue) para refrescar entitlement + nav.
            st.broadcast(json!({
                "type": "module.updated",
                "module_id": module_id,
                "from": from,
                "to": to,
            }));
            st.broadcast(json!({ "type": "module.installed", "module_id": module_id }));
            Json(json!({ "ok": true, "data": { "module_id": module_id, "from": from, "version": to, "updated": true } })).into_response()
        }
        // 200, not 5xx: the update did not go in, but **the module keeps working**. Answering with
        // an error would suggest the hub was left broken, and it was not.
        // `cause` is the stable code of why the new version did not go in (hub#2556): the screen
        // says «erplora.com did not answer in time, try again» for a download that ran out of time
        // instead of a bare «could not update». The English `message` stays for the log.
        Outcome::RolledBack { stayed_on, error } => {
            let cause = first_error
                .lock()
                .ok()
                .and_then(|first| first.as_ref().map(|e| e.code()));
            Json(json!({
                "ok": true,
                "data": { "module_id": module_id, "version": stayed_on, "updated": false },
                "warning": {
                    "code": "module.update_failed_kept_previous",
                    "cause": cause,
                    "message": error,
                },
            }))
            .into_response()
        }
        Outcome::Lost { ref module, ref error } => update_lost_response(module, error),
    }
}

/// `GET /api/modules/updates` — qué versión ofrece hoy el marketplace para cada módulo instalado
/// (hub#516). **On demand, never a fast poll**: each call costs one Cloud call per module (24). The
/// Apps screen asks when it opens, and the shell's bell notice (hub#1172) asks when an admin session
/// starts and then hours apart; the unattended path is still the boot, which resolves the latest.
///
/// Usa **el mismo resolutor** que el arranque, así que lo que el botón ofrece es exactamente lo que
/// la actualización automática haría sola: nunca una versión en cuarentena, nunca hacia atrás, y el
/// pin de soporte gana. Si el Cloud no contesta, `latest == installed` y no se ofrece nada —
/// inventar una versión sería peor que no decir nada.
pub(crate) async fn list_module_updates(
    State(st): State<AppState>,
    headers: HeaderMap,
) -> Response {
    let installed: Vec<(String, String, Option<String>)> = {
        let rt = st.runtime.read().await;
        if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
        match erplora_runtime::installer::installed_with_pin(rt.db(), &st.hub_id()).await {
            Ok(rows) => rows,
            Err(e) => {
                return (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    Json(json!({ "ok": false, "error": e.to_string() })),
                )
                    .into_response()
            }
        }
    };

    let Some(auth) = auth::hub_scoped_auth(&headers, &st) else {
        // Without a credential the marketplace cannot be asked: every app is «I don't know»
        // (hub#2336), never an empty list the screen would read as «nothing to update». A pinned
        // app is the exception: it never moves, so its answer is known without asking.
        let out: Vec<Value> = installed
            .into_iter()
            .map(|(module_id, version, pinned)| {
                let checked = pinned.is_some();
                update_row(&module_id, &version, pinned, &version, false, None, checked)
            })
            .collect();
        return Json(json!({ "ok": true, "data": out })).into_response();
    };

    let mut out = Vec::with_capacity(installed.len());
    for (module_id, version, pinned) in installed {
        let offer = install::resolve_offer(
            &st.marketplace_http,
            &st.config.cloud_base_url,
            &auth,
            &module_id,
            &version,
            pinned.as_deref(),
        )
        .await;
        out.push(update_row(
            &module_id,
            &version,
            pinned,
            offer.target.version(),
            offer.target.is_update(),
            offer.floor,
            offer.checked,
        ));
    }
    Json(json!({ "ok": true, "data": out })).into_response()
}

/// One row of `GET /api/modules/updates`.
fn update_row(
    module_id: &str,
    installed: &str,
    pinned: Option<String>,
    latest: &str,
    update_available: bool,
    floor: Option<String>,
    checked: bool,
) -> Value {
    json!({
        "module_id": module_id,
        "installed": installed,
        "latest": latest,
        "update_available": update_available,
        "pinned": pinned,
        // hub#2082: the ERPlora the offered version needs (`null` = none declared), so the
        // Apps page says «needs ERPlora X» instead of an «Update» the runtime would refuse.
        "latest_min_erplora_version": floor,
        // hub#2336: `false` = the marketplace could not be asked about this app. «I don't know»
        // is neither an update nor «up to date»: the screen and the bell say so.
        "checked": checked,
    })
}

/// `GET /api/modules/:id/versions` — entre qué versiones puede elegir este hub (hub#675).
///
/// Es la lista del **desplegable de versión**, y sirve a las dos puertas: instalar (el módulo aún no
/// está: valen todas las publicadas) y actualizar (solo hacia delante desde la instalada). Por eso
/// **no es un 404** pedir las versiones de algo que no está instalado —esa regla es de `update`, no
/// de esta— y por eso `installed` puede venir `null`.
///
/// La política la pone `module_update::offer`, la misma pieza que decide la actualización
/// automática: fuera la cuarentena, fuera el retroceso, y un módulo clavado por soporte no ofrece
/// nada. Sin eso, el desplegable sería una segunda puerta con una segunda política.
///
/// Auth = **sesión de admin**, igual que instalar y actualizar. Sin ella no se pregunta al Cloud:
/// la respuesta viaja con la credencial de máquina del hub, y cualquier módulo web same-origin
/// podría usarla de rebote para leer el catálogo.
pub(crate) async fn list_module_versions(
    State(st): State<AppState>,
    Path(module_id): Path<String>,
    headers: HeaderMap,
) -> Response {
    {
        let rt = st.runtime.read().await;
        if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }
    // Mismo motivo que en `proxy_marketplace_module` (hub#1134): este id acaba dentro de la URL del
    // Cloud que se firma con el token de máquina.
    if !module_id_is_safe(&module_id) {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({
                "ok": false,
                "error": { "code": "module.invalid_id", "message": "invalid module id" },
            })),
        )
            .into_response();
    }

    // Todo lo que hace falta del hub, y **se suelta el candado**: la llamada al Cloud viene después.
    // Sostener el guard del runtime durante un round-trip de red retendría a cualquier escritor en
    // cola (una instalación) y, tras él, a `/api/query` y `/api/command` —el TPV— mientras el
    // marketplace tarda en contestar (hub#978: el `RwLock` es justo con los escritores).
    let (installed, pinned) = {
        let rt = st.runtime.read().await;
        (
            install::installed_version(&rt, &module_id),
            install::support_pin(&rt, &module_id).await,
        )
    };

    // Sin credencial no se puede preguntar al marketplace. No es un error: es «no lo sé», y «no lo
    // sé» se pinta como «no hay nada que elegir», nunca como una lista inventada.
    let Some(auth) = auth::hub_scoped_auth(&headers, &st) else {
        return Json(json!({
            "ok": true,
            "data": { "module_id": module_id, "installed": installed, "latest": null, "versions": [] },
        }))
        .into_response();
    };

    let versions = install::offered_versions(
        &st.marketplace_http,
        &st.config.cloud_base_url,
        &auth,
        &module_id,
        installed.as_deref(),
        pinned.as_deref(),
    )
    .await;

    Json(json!({
        "ok": true,
        "data": {
            "module_id": module_id,
            "installed": installed,
            // La que se ofrece por defecto: la primera de la lista. `null` = no hay nada que elegir.
            "latest": versions.first(),
            "versions": versions,
        },
    }))
    .into_response()
}

/// Status HTTP de un fallo del pipeline de instalación/actualización. Compartido por
/// `request-install` y `update` (hub#516): el mismo fallo tiene que contarse igual por las dos
/// puertas, o la UI acaba programando contra dos contratos.
///
/// 🔴 **Ninguna rama devuelve un 5xx** (hub#1720). El hub es el ORIGEN, no una pasarela: un `502`
/// emitido aquí es indistinguible del `502` que acuña el proxy que tiene delante, así que el borde
/// contesta con su propia página `error code: 502` y **sustituye el cuerpo** — llevándose el `code`
/// estable de hub#139 que la shell traduce. Medido en PRE el 2026-09-09: el motivo quedaba en el
/// log del contenedor y quien estaba en el marketplace leía una página del borde, sin poder
/// distinguir «me falta credencial» de «ese módulo no existe» de «el Cloud está caído». Un `4xx`
/// cruza cualquier proxy con su cuerpo intacto y sigue leyéndose como fallo (`res.ok === false`).
/// Lo sostiene `no_install_failure_is_reported_as_a_server_error`, que recorre TODAS las variantes.
pub(crate) fn install_error_status(e: &install::InstallError) -> StatusCode {
    match e {
        install::InstallError::VersionNotFound(_) => StatusCode::NOT_FOUND,
        // Actualizar algo que no está instalado: no hay recurso al que aplicar la operación.
        install::InstallError::NotInstalled(_) => StatusCode::NOT_FOUND,
        install::InstallError::Runtime(_) => StatusCode::UNPROCESSABLE_ENTITY,
        // hub#1620: the hub refuses a module it cannot run whole. Same status as any other runtime
        // refusal — what differs is the code and the two numbers in the body.
        install::InstallError::CoreVersionTooOld { .. } => StatusCode::UNPROCESSABLE_ENTITY,
        // Fallo de FIRMA (hub#239): el módulo no verifica — sin firma, firma inválida o
        // clave ajena. Es un rechazo de seguridad, NO un fallo de gateway: 403.
        install::InstallError::Source(source::SourceError::BadSignature(_)) => {
            StatusCode::FORBIDDEN
        }
        // ADR-0060: el plan exige comprar dependencias. NO es un fallo del hub ni del
        // Cloud: es una decisión que le toca al usuario → 409 con los datos de compra.
        install::InstallError::Blocked { .. } => StatusCode::CONFLICT,
        // hub#2546: the module's state (a support pin, or a newer version installed) is what
        // refuses the version asked for — nothing failed, nothing was touched.
        install::InstallError::VersionNotOffered { .. } => StatusCode::CONFLICT,
        // hub#1720: el Cloud CONTESTÓ que ese módulo no está en el catálogo de este hub. Es la
        // misma frase que `VersionNotFound` un escalón más arriba —«eso no existe para ti»—, así
        // que se cuenta igual y no como una avería.
        install::InstallError::NotInCatalog { .. } => StatusCode::NOT_FOUND,
        // El pipeline dependía del Cloud (catálogo, plan, zip, `sha256`) y esa parte falló: el
        // hub hizo su trabajo y no pudo terminar. `424 Failed Dependency` lo dice tal cual y —al
        // contrario que el `502` que había aquí— llega al navegador con su `code` dentro.
        install::InstallError::Cloud(_)
        | install::InstallError::Source(_)
        | install::InstallError::MissingSha256 { .. }
        | install::InstallError::CloudDenied
        | install::InstallError::CloudRejected { .. }
        | install::InstallError::CloudTimeout => StatusCode::FAILED_DEPENDENCY,
    }
}

/// Status HTTP con el que se cuenta cómo acabó un intento de actualización
/// ([`erplora_runtime::module_update::Outcome`]).
///
/// El match es **exhaustivo a propósito**: un desenlace nuevo del pipeline no compila hasta que
/// alguien decide con qué status se cuenta, en vez de heredar en silencio el de al lado.
pub(crate) fn update_outcome_status(
    outcome: &erplora_runtime::module_update::Outcome,
) -> StatusCode {
    use erplora_runtime::module_update::Outcome;
    match outcome {
        // La actualización salió, o no hacía falta.
        Outcome::AlreadyThere(_) | Outcome::Updated { .. } => StatusCode::OK,
        // 200, no un error: la actualización no salió, pero **el módulo sigue funcionando**.
        Outcome::RolledBack { .. } => StatusCode::OK,
        // hub#1763: la nueva falló Y la vuelta atrás también, así que el hub se quedó sin el
        // módulo — pero eso se cuenta con el mismo `424` que el resto del pipeline (hub#1720), no
        // con un `5xx`: el borde sustituye el cuerpo de un `5xx` por su propia página y se lleva
        // el `module.update_lost` que la shell traduce, dejando a quien pulsó «Actualizar» sin
        // saber siquiera qué módulo se ha ido.
        Outcome::Lost { .. } => cloud_proxy::CLOUD_FAILED,
    }
}

/// Respuesta de `POST /api/modules/:id/update` cuando la nueva versión falló **y la vuelta atrás
/// también** ([`erplora_runtime::module_update::Outcome::Lost`]): el hub se quedó sin el módulo.
///
/// Mismo sobre **plano** que [`install_error_response`] —`{ok, error, code}`—, porque es el único
/// que lee la shell (`updateModule` en `apps/web/src/lib/runtime.ts`): `error` es la frase y `code`
/// el hecho estable. Con el `code` anidado en `error.code` nadie lo leía, y quien pulsó «Actualizar»
/// leía «sigue funcionando con la versión que tenía» sobre un módulo que acababa de desaparecer
/// (hub#1763). La frase que ve la persona sale de `runtimeErrors.module.update_lost`, `en`+`es`.
pub(crate) fn update_lost_response(module: &str, error: &str) -> Response {
    let outcome = erplora_runtime::module_update::Outcome::Lost {
        module: module.into(),
        error: error.into(),
    };
    (
        update_outcome_status(&outcome),
        Json(json!({
            "ok": false,
            "error": format!("`{module}`: {error}"),
            "code": "module.update_lost",
        })),
    )
        .into_response()
}

/// Respuesta de un fallo del pipeline, con el canal de errores de dominio (hub#139): además del
/// mensaje humano viaja un `code` estable contra el que la UI programa y traduce. Un install —o un
/// update— fallido no es mudo.
pub(crate) fn install_error_response(e: &install::InstallError) -> Response {
    let mut body = json!({
        "ok": false,
        "error": e.to_string(),
        "code": e.code(),
    });
    if let install::InstallError::Blocked {
        blocked_on,
        purchase,
        ..
    } = e
    {
        body["blocked_on"] = json!(blocked_on);
        body["purchase"] = json!(purchase
            .iter()
            .map(|p| json!({
                "module_id": p.module_id,
                "module_type": p.module_type,
                "price": p.price,
                "currency": p.currency,
                "purchase_url": p.purchase_url,
            }))
            .collect::<Vec<_>>());
    }
    // hub#1620: the translated sentence names both versions, so they travel as data.
    if let install::InstallError::CoreVersionTooOld {
        module,
        required,
        core,
    } = e
    {
        body["module_id"] = json!(module);
        body["required"] = json!(required);
        body["core"] = json!(core);
    }
    (install_error_status(e), Json(body)).into_response()
}

/// Lo que se le dice a las cachés sobre un asset servido por la ruta **con** versión: el contenido
/// de una versión publicada no cambia jamás (republicar exige subir la versión), así que se puede
/// guardar para siempre. Es lo que hace que la url versionada además sea *más rápida* que la de
/// antes, no solo más correcta.
pub(crate) const MODULE_ASSET_IMMUTABLE: &str = "public, max-age=31536000, immutable";

/// Y lo que se le dice sobre la ruta **sin** versión: ahí el contenido SÍ cambia bajo los pies (es
/// «la versión instalada», sea cual sea hoy), así que guardarla sin preguntar es exactamente el
/// defecto de hub#935. `no-cache` no prohíbe almacenarla: obliga a revalidarla antes de usarla.
pub(crate) const MODULE_ASSET_REVALIDATE: &str = "no-cache, must-revalidate";

/// Un segmento de ruta que no puede salir del `module_cache` (ni `..` ni vacío ni separadores).
pub(crate) fn is_safe_path_segment(seg: &str) -> bool {
    !seg.is_empty() && seg != ".." && seg != "." && !seg.contains('/') && !seg.contains('\\')
}

/// Lee `module_cache/<id>/<version>/<rel>` y lo devuelve con su content-type y su política de caché.
pub(crate) async fn read_module_asset(
    st: &AppState,
    id: &str,
    version: &str,
    rel: &str,
    cache_control: &'static str,
) -> Response {
    // Anti path-traversal: ningún segmento `..` (incluido tras decodificar %2e%2e) ni vacío.
    if rel.split('/').any(|seg| !is_safe_path_segment(seg)) {
        return StatusCode::NOT_FOUND.into_response();
    }
    let full = st.config.module_cache.join(id).join(version).join(rel);
    match tokio::fs::read(&full).await {
        Ok(bytes) => (
            [
                (header::CONTENT_TYPE, module_asset_content_type(rel)),
                (header::CACHE_CONTROL, cache_control),
            ],
            bytes,
        )
            .into_response(),
        Err(_) => StatusCode::NOT_FOUND.into_response(),
    }
}

/// GET /modules/:id/v/:version/*path — el MISMO asset, direccionado por versión (hub#935).
///
/// Existe porque un módulo actualizado no llegaba al navegador: todas las versiones se servían desde
/// la misma url y sin una sola cabecera de caché, así que el borde cacheaba el `.js` por extensión
/// (`cf-cache-status: HIT`) y el `import()` del shell seguía recibiendo el bundle anterior mientras
/// el `module.json` ya decía la versión nueva. El fallo era MUDO: manifest nuevo, servidor nuevo,
/// pantalla vieja. Un `?v=` no lo arregla —el borde ignora la query para la clave de caché—; una
/// ruta distinta sí, porque ninguna caché la ha visto antes.
///
/// Sirve **cualquier versión presente en la caché de descargas**, no solo la instalada: es lo que la
/// hace inmutable de verdad (una pestaña abierta desde antes de actualizar sigue resolviendo su
/// bundle) y lo que permite declararla cacheable un año. El módulo sí tiene que estar instalado.
pub(crate) async fn serve_module_asset_at(
    State(st): State<AppState>,
    Path((id, version, rel)): Path<(String, String, String)>,
) -> Response {
    // La versión es un segmento de ruta más y llega del cliente: hostil hasta que se demuestre.
    if !is_safe_path_segment(&version) {
        return StatusCode::NOT_FOUND.into_response();
    }
    let installed = {
        let rt = st.runtime.read().await;
        rt.modules().into_iter().any(|m| m.id == id)
    };
    if !installed {
        return StatusCode::NOT_FOUND.into_response();
    }
    read_module_asset(&st, &id, &version, &rel, MODULE_ASSET_IMMUTABLE).await
}

/// GET /modules/:id/*path — sirve los assets web (`module.json`, `dist/*.esm.js`, wasm, icons) de un
/// módulo instalado desde la CACHÉ de descargas, resueltos por la VERSIÓN instalada
/// (`module_cache/<id>/<version>/<path>`). La versión sale del registro (el módulo debe estar
/// instalado). Guard anti path-traversal. Un asset ausente o un módulo no instalado → **404** (lo
/// maneja el cargador del Web Component); al ser ruta explícita NO cae al fallback SPA, así que nunca
/// se sirve `index.html` haciéndose pasar por JS/JSON (que es exactamente lo que rompía la UI).
///
/// Sigue siendo la ruta del `module.json` —quien DICE en qué versión está el módulo— y el respaldo
/// para clientes anteriores a hub#935. Por eso va marcada «revalida siempre»: su contenido cambia
/// cada vez que se actualiza el módulo, y servirla de una caché es servir la versión de ayer.
pub(crate) async fn serve_module_asset(
    State(st): State<AppState>,
    Path((id, rel)): Path<(String, String)>,
) -> Response {
    // Versión instalada del módulo (del registro). Módulo no instalado → 404.
    let version = {
        let rt = st.runtime.read().await;
        rt.modules()
            .into_iter()
            .find(|m| m.id == id)
            .map(|m| m.version)
    };
    let Some(version) = version else {
        return StatusCode::NOT_FOUND.into_response();
    };
    read_module_asset(&st, &id, &version, &rel, MODULE_ASSET_REVALIDATE).await
}

/// Content-Type de un asset de módulo por extensión (los que sirve [`serve_module_asset`]).
pub(crate) fn module_asset_content_type(rel: &str) -> &'static str {
    if rel.ends_with(".js") || rel.ends_with(".mjs") {
        "text/javascript"
    } else if rel.ends_with(".json") || rel.ends_with(".map") {
        "application/json"
    } else if rel.ends_with(".wasm") {
        "application/wasm"
    } else if rel.ends_with(".css") {
        "text/css"
    } else if rel.ends_with(".svg") {
        "image/svg+xml"
    } else {
        "application/octet-stream"
    }
}

#[derive(Deserialize)]
pub(crate) struct InstallReq {
    /// Ruta a la carpeta del módulo ya extraída (la prepara erplora-source desde el S3 zip).
    dir: String,
}

/// Query param de idioma para los endpoints localizables (ADR-0055). `?locale=es`; default `en`.
#[derive(serde::Deserialize)]
pub(crate) struct LocaleQuery {
    pub(crate) locale: Option<String>,
}

pub(crate) async fn navigation(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<LocaleQuery>,
) -> Response {
    let locale = q.locale.as_deref().unwrap_or("en");
    let rt = st.runtime.read().await;
    let ctx = match auth::require_user_session(&headers, &st.config, &rt).await {
        Ok(ctx) => ctx,
        Err(e) => return unauthorized(e),
    };
    let reg = rt.registry();
    let items: Vec<Value> = rt
        .navigation()
        .iter()
        // hub#1052: una pestaña con `permission` solo se sirve a quien la tiene. Antes no había
        // dónde declararlo, así que el módulo la pintaba para todos y el usuario descubría el
        // límite estrellándose contra un 403 — `flows` lo dice en su propio código: mandar al
        // cajero a revisar sus permisos «lo mandaría a un sitio al que no puede ir».
        //
        // El predicado es el MISMO que el de la puerta real (`permissions::has`), así que el menú
        // y el command no pueden discrepar sobre qué significa un permiso. Sin `permission` la
        // entrada es visible, como en todos los manifests publicados hasta hoy.
        .filter(|n| {
            n.nav
                .permission
                .as_deref()
                .is_none_or(|p| erplora_runtime::permissions::has(&ctx, p))
        })
        .map(|n| {
            let entry = reg.installed.iter().find(|m| m.id == n.module_id);
            let mod_fallback = entry
                .map(|m| m.name.as_str())
                .unwrap_or(n.module_id.as_str());
            json!({
                "module_id": n.module_id,
                // Nombre del módulo traducido (ADR-0055): lo usa el shell para el sidebar y las
                // tarjetas del dashboard (un ítem por módulo).
                "module_name": reg.module_name_localized(&n.module_id, mod_fallback, locale),
                // Versión INSTALADA (hub#935). Con ella el shell construye la url versionada del
                // bundle (`/modules/<id>/v/<version>/…`) sin depender del `module.json`, que es un
                // asset y sí puede llegar de una caché: si llegara atrasado, el shell pediría la url
                // de la versión vieja —cacheada— y volveríamos al fallo mudo que motivó la issue.
                // Esta respuesta va autenticada y ninguna caché la toca.
                "module_version": entry.map(|m| m.version.clone()),
                "id": n.nav.id,
                // Label de la pestaña traducido (ADR-0055): locale → en → label del manifest.
                "label": reg.nav_label_localized(&n.module_id, &n.nav.id, &n.nav.label, locale),
                "icon": n.nav.icon, "component": n.nav.component,
            })
        })
        .collect();
    // `active_modules` = módulos instalados **y activos** (hub#894). **Aditivo**: `ok`/`data` intactos.
    //
    // `data` es el menú, y por sí solo no distingue las dos cosas que producen el mismo array vacío:
    // un hub recién nacido y un hub con 12 módulos cuyo menú salió vacío de todas formas. La primera
    // es un hecho que merece pintarse («añade tu primera app»); la segunda no, y se pintaba igual —
    // un hub real de producción (12/12 según `/readyz`) le dijo a su dueña que no tenía apps y le
    // ofreció instalar las que ya tenía. Este número le da al shell contra qué comprobar la lista
    // vacía en vez de creérsela.
    //
    // Cuenta los **activos**, no los instalados, y la diferencia importa: un módulo que el admin
    // apagó a propósito NO se espera que aporte menú, así que contarlo convertiría un hub apagado a
    // conciencia en un falso «no he podido cargar tus apps». El denominador es lo que el hub espera
    // que aporte, no lo que tiene guardado.
    let active_modules = reg
        .installed
        .iter()
        .filter(|m| reg.is_active(&m.id))
        .count();
    Json(json!({ "ok": true, "data": items, "active_modules": active_modules })).into_response()
}

pub(crate) async fn list_modules(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<LocaleQuery>,
) -> Response {
    let locale = q.locale.as_deref().unwrap_or("en");
    let rt = st.runtime.read().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let reg = rt.registry();
    // Ids de módulos (activos) que exponen al menos una op `expose_api` (ADR-0057). Se calcula UNA
    // vez y se consulta por pertenencia → campo aditivo `has_public_api` por módulo, que usa la
    // matriz de scope de las API keys para listar solo módulos que conceden algo.
    let public_api: std::collections::HashSet<String> =
        reg.modules_with_public_api().into_iter().collect();
    let items: Vec<Value> = rt
        .modules()
        .into_iter()
        .map(|m| {
            json!({
                "id": m.id,
                // Nombre traducido (ADR-0055): locale → en → name del manifest.
                "name": reg.module_name_localized(&m.id, &m.name, locale),
                "version": m.version,
                "status": m.status,
                // Dependencias declaradas: el toggle del shell las usa para AVISAR de la cascada
                // (ADR-0128) antes de desactivar («también desactivará: …»).
                "depends_on": m.depends_on,
                // ADITIVO (ADR-0057): true si el módulo expone alguna query/command `expose_api`.
                "has_public_api": public_api.contains(&m.id),
                // ADITIVO (hub#521): lo que el core NO entendió de su `module.json` y aun así
                // instaló. Vacío en un módulo que encaja con el contrato — que es lo normal. Es la
                // superficie CONSULTABLE del aviso: sin ella, «el hub lo ignora en silencio» se
                // arreglaría escribiendo el silencio en un log que nadie mira.
                "manifest_warnings": m.manifest_warnings,
            })
        })
        .collect();
    Json(json!({ "ok": true, "data": items })).into_response()
}

/// `POST /api/modules/install {dir}` — instala un módulo desde una carpeta YA extraída.
///
/// Vía de **desarrollo**: esquiva el pipeline del marketplace (grant + SHA256 obligatorio,
/// ADR-0015), así que va doblemente gateada (hub#239, ver [`install_guard`]): modo desarrollo
/// explícito + `dir` confinado en el staging del hub. La sesión admin sigue siendo necesaria,
/// pero **no basta**: el agujero no era de auth, era de superficie.
pub(crate) async fn install_module(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<InstallReq>,
) -> Response {
    let mut rt = st.runtime.write().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let dir = match install_guard::resolve_install_dir(
        st.config.dev_mode,
        &st.config.install_staging_roots(),
        &req.dir,
    ) {
        Ok(dir) => dir,
        Err(rejection) => return install_dir_rejected(&req.dir, rejection),
    };
    match rt.install_from_dir(&dir).await {
        Ok(id) => Json(json!({ "ok": true, "data": { "module_id": id } })).into_response(),
        Err(e) => err_response(e),
    }
}

/// Respuesta estable a un `dir` de instalación rechazado (hub#239). `403` cuando la vía está
/// cerrada por política (producción / fuera del staging), `422` cuando la ruta simplemente no
/// sirve. Se registra a WARN: un intento fuera del staging es señal de abuso, no ruido.
pub(crate) fn install_dir_rejected(
    requested: &str,
    rejection: install_guard::InstallDirRejection,
) -> Response {
    use install_guard::InstallDirRejection as R;
    let status = match rejection {
        R::DevModeRequired | R::OutsideStaging => StatusCode::FORBIDDEN,
        R::NotFound | R::NotADirectory => StatusCode::UNPROCESSABLE_ENTITY,
    };
    tracing::warn!(
        dir = %requested,
        code = rejection.code(),
        "instalación desde carpeta rechazada"
    );
    let body = json!({
        "ok": false,
        "error": { "code": rejection.code(), "message": rejection.message() },
    });
    (status, Json(body)).into_response()
}

pub(crate) async fn activate_module(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let mut rt = st.runtime.write().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.activate(&id).await {
        Ok(()) => {
            drop(rt);
            // hub#1317 (review of hub#1311): before this, activating a module emitted nothing
            // over `/ws` — the same hole hub#631 closed ONLY for `module.installed`. Another
            // tab/device of the same hub (and, since hub#1211, the module-sdk's active-modules
            // cache read by `queryOptional`) stayed on yesterday's state until it reloaded. Same
            // shape as `module.installed`: a raw frame with no `FRAME_MODULE` (it's the hub's
            // own, not a module's).
            st.broadcast(json!({ "type": "module.activated", "module_id": id }));
            Json(json!({ "ok": true })).into_response()
        }
        Err(e) => err_response(e),
    }
}

pub(crate) async fn deactivate_module(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let mut rt = st.runtime.write().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.deactivate(&id).await {
        Ok(()) => {
            drop(rt);
            // hub#1317: same reasoning as `activate_module` — without this, another tab kept
            // offering a module the owner had just switched off until someone reloaded it.
            st.broadcast(json!({ "type": "module.deactivated", "module_id": id }));
            Json(json!({ "ok": true })).into_response()
        }
        Err(e) => err_response(e),
    }
}

/// Body of `POST /api/modules/:id/uninstall` (hub#1101). Optional in full: the historical call
/// sends nothing at all, and «nothing» has to keep meaning the SAFE answer.
#[derive(serde::Deserialize, Default)]
pub(crate) struct UninstallReq {
    /// «Other apps need this one — remove it anyway». Only the caller that was shown the list
    /// (the confirmation dialog of hub#773, or support driving the API on purpose) sends it.
    /// It opens the dependants gate and NOTHING else: the fiscal locks are not the owner's
    /// question and stay shut (ADR-0202 R2, ADR-0273 D5).
    #[serde(default)]
    force: bool,
}

pub(crate) async fn uninstall_module(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
    body: Option<Json<UninstallReq>>,
) -> Response {
    let force = body.map(|Json(b)| b.force).unwrap_or_default();
    let _module_ops = st.module_ops.lock().await;
    let mut rt = st.runtime.write().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    // hub#2545: forcing takes the dependents with it (farthest first), so `also` names them.
    let outcome = if force {
        rt.uninstall_forced(&id).await
    } else {
        rt.uninstall(&id).await.map(|()| Vec::new())
    };
    match outcome {
        Ok(also) => {
            drop(rt);
            // hub#1317: emitted NOW, before the best-effort embeddings cleanup below — what
            // matters to another tab/device is that the runtime already uninstalled the module,
            // not whether the best-effort vector index cleanup finished. One frame per app that
            // left, in the order they left: a dependent removed by `force` is just as gone.
            let gone: Vec<&String> = also.iter().chain(std::iter::once(&id)).collect();
            for module_id in &gone {
                st.broadcast(json!({ "type": "module.uninstalled", "module_id": module_id }));
            }
            // Drops each departed module's chunks from the vector index (§9.6): uninstall →
            // delete chunks. Best-effort: a store error does not fail the uninstall.
            if let Some(store) = &st.vector {
                for module_id in &gone {
                    if let Err(e) =
                        embed::drop_module(store.as_ref(), &st.hub_id(), module_id).await
                    {
                        tracing::warn!(module_id = %module_id, error = %e, "could not drop the module's embeddings (non-critical)");
                    }
                }
            }
            if also.is_empty() {
                Json(json!({ "ok": true })).into_response()
            } else {
                Json(json!({ "ok": true, "also_uninstalled": also })).into_response()
            }
        }
        Err(e) => err_response(e),
    }
}

#[cfg(test)]
mod install_error_status_tests {
    use super::*;

    /// One label per variant of [`install::InstallError`]. Its only job is to make the guard below
    /// **mechanical**: `tag()` matches exhaustively over the error enum, so a variant added to the
    /// pipeline does not compile until it is named here, and `sample()` matches exhaustively over
    /// this enum, so it does not compile until an instance of it travels through the guard either.
    /// Adding a failure mode and quietly mapping it back to a 502 is not reachable from here.
    /// The labels and the list the guard walks are declared **once**: a hand-kept second copy is
    /// exactly how a guard goes green on a list that quietly lost the case that was failing.
    /// Dropping a name here deletes the variant too, and `tag()` stops being exhaustive over
    /// [`install::InstallError`] — it does not compile.
    macro_rules! every_install_failure {
        ($($v:ident),+ $(,)?) => {
            #[derive(Debug, Clone, Copy, PartialEq, Eq)]
            enum Tag { $($v),+ }

            const EVERY_TAG: &[Tag] = &[$(Tag::$v),+];
        };
    }

    every_install_failure!(
        Cloud,
        VersionNotFound,
        Source,
        MissingSha256,
        Blocked,
        Runtime,
        CoreVersionTooOld,
        NotInstalled,
        CloudDenied,
        NotInCatalog,
        CloudRejected,
        CloudTimeout,
        VersionNotOffered,
    );

    fn tag(e: &install::InstallError) -> Tag {
        match e {
            install::InstallError::Cloud(_) => Tag::Cloud,
            install::InstallError::VersionNotFound(_) => Tag::VersionNotFound,
            install::InstallError::Source(_) => Tag::Source,
            install::InstallError::MissingSha256 { .. } => Tag::MissingSha256,
            install::InstallError::Blocked { .. } => Tag::Blocked,
            install::InstallError::Runtime(_) => Tag::Runtime,
            install::InstallError::CoreVersionTooOld { .. } => Tag::CoreVersionTooOld,
            install::InstallError::NotInstalled(_) => Tag::NotInstalled,
            install::InstallError::CloudDenied => Tag::CloudDenied,
            install::InstallError::NotInCatalog { .. } => Tag::NotInCatalog,
            install::InstallError::CloudRejected { .. } => Tag::CloudRejected,
            install::InstallError::CloudTimeout => Tag::CloudTimeout,
            install::InstallError::VersionNotOffered { .. } => Tag::VersionNotOffered,
        }
    }

    fn sample(t: Tag) -> install::InstallError {
        match t {
            Tag::Cloud => install::InstallError::Cloud("cloud_unreachable".into()),
            Tag::VersionNotFound => install::InstallError::VersionNotFound("sales@9.9.9".into()),
            Tag::Source => {
                install::InstallError::Source(source::SourceError::Fetch("connection reset".into()))
            }
            Tag::MissingSha256 => install::InstallError::MissingSha256 {
                module_id: "sales".into(),
                version: "1.0.0".into(),
            },
            Tag::Blocked => install::InstallError::Blocked {
                requested: "sales".into(),
                blocked_on: vec!["taxes".into()],
                purchase: Vec::new(),
            },
            Tag::Runtime => install::InstallError::Runtime("migration failed".into()),
            Tag::CoreVersionTooOld => install::InstallError::CoreVersionTooOld {
                module: "whatsapp_inbox".into(),
                required: "1.1.16".into(),
                core: "1.1.15".into(),
            },
            Tag::NotInstalled => install::InstallError::NotInstalled("sales".into()),
            Tag::CloudDenied => install::InstallError::CloudDenied,
            Tag::NotInCatalog => install::InstallError::NotInCatalog {
                module_id: "sales".into(),
            },
            Tag::CloudRejected => install::InstallError::CloudRejected { status: 500 },
            Tag::CloudTimeout => install::InstallError::CloudTimeout,
            Tag::VersionNotOffered => install::InstallError::VersionNotOffered {
                module_id: "sales".into(),
                version: "0.5.0".into(),
            },
        }
    }

    /// **hub#1720 — no failure of the install pipeline is reported as a server error.**
    ///
    /// The hub is the ORIGIN, not a gateway. A `5xx` minted here is indistinguishable from a `5xx`
    /// minted by the proxy in front of it, so the edge answers with its own page and REPLACES the
    /// body — taking with it the stable `code` of hub#139 that the shell translates. Measured in
    /// PRE on 2026-09-09: `request-install` answered `502`, the motive was written to the
    /// container log, and the person on the marketplace read `error code: 502`.
    ///
    /// The rule is the whole class, not the three variants that were caught doing it: a `4xx`
    /// crosses any proxy with its body intact and still reads as a failure (`res.ok === false`)
    /// for the shell.
    #[test]
    fn no_install_failure_is_reported_as_a_server_error() {
        for &t in EVERY_TAG {
            let e = sample(t);
            let status = install_error_status(&e);
            assert!(
                !status.is_server_error(),
                "{:?} answers {status}: an edge is free to replace the body of a 5xx with its own \
                 page, so `{}` would never reach the browser",
                t,
                e.code()
            );
            assert!(
                status.is_client_error(),
                "{:?} answers {status}: a failed install still has to read as an error for the \
                 shell (`res.ok === false`)",
                t
            );
        }
    }

    /// The control of the control: each label really does carry **its own** variant into the
    /// guard. A `sample()` that answered someone else's variant would leave the case it was
    /// supposed to cover untested while the guard above stayed green.
    ///
    /// The other half of that risk — a label dropped from the walked list — is not testable from
    /// here on purpose: `every_install_failure!` declares the enum and the list from one source,
    /// so losing a name is a **compile** error, not a green run.
    #[test]
    fn every_label_carries_its_own_variant_into_the_guard() {
        for &t in EVERY_TAG {
            assert_eq!(
                tag(&sample(t)),
                t,
                "{t:?} builds a sample of another variant, so {t:?} never reaches the guard"
            );
        }
    }
}

#[cfg(test)]
mod update_outcome_status_tests {
    use super::*;
    use erplora_runtime::module_update::Outcome;

    /// One label per desenlace of [`Outcome`], declared **once** so the guard below is mechanical:
    /// `tag()` matches exhaustively over the runtime enum, so a new outcome does not compile until
    /// it is named here, and `sample()` matches exhaustively over these labels, so it does not
    /// compile until an instance of it travels through the guard either. Same mould as
    /// `every_install_failure!`: a hand-kept second list is exactly how a guard goes green over a
    /// case it quietly stopped walking.
    macro_rules! every_update_outcome {
        ($($v:ident),+ $(,)?) => {
            #[derive(Debug, Clone, Copy, PartialEq, Eq)]
            enum Tag { $($v),+ }

            const EVERY_TAG: &[Tag] = &[$(Tag::$v),+];
        };
    }

    every_update_outcome!(AlreadyThere, Updated, RolledBack, Lost);

    fn tag(o: &Outcome) -> Tag {
        match o {
            Outcome::AlreadyThere(_) => Tag::AlreadyThere,
            Outcome::Updated { .. } => Tag::Updated,
            Outcome::RolledBack { .. } => Tag::RolledBack,
            Outcome::Lost { .. } => Tag::Lost,
        }
    }

    fn sample(t: Tag) -> Outcome {
        match t {
            Tag::AlreadyThere => Outcome::AlreadyThere("1.0.0".into()),
            Tag::Updated => Outcome::Updated {
                from: "1.0.0".into(),
                to: "1.1.0".into(),
            },
            Tag::RolledBack => Outcome::RolledBack {
                stayed_on: "1.0.0".into(),
                error: "migration failed".into(),
            },
            Tag::Lost => Outcome::Lost {
                module: "sales".into(),
                error: "rollback failed".into(),
            },
        }
    }

    /// **hub#1763 — no outcome of an update is reported as a server error either.**
    ///
    /// Same reason as `no_install_failure_is_reported_as_a_server_error` (hub#1720), on the door
    /// that issue left out: `POST /api/modules/:id/update` answered `500` on [`Outcome::Lost`], and
    /// an edge is free to replace the body of a `5xx` with its own page — taking with it the
    /// `module.update_lost` code the shell translates. The person is then told nothing at all about
    /// the module that just disappeared from their hub.
    #[test]
    fn no_update_outcome_is_reported_as_a_server_error() {
        for &t in EVERY_TAG {
            let status = update_outcome_status(&sample(t));
            assert!(
                !status.is_server_error(),
                "{t:?} answers {status}: an edge is free to replace the body of a 5xx with its own \
                 page, so the `code` would never reach the browser"
            );
        }
    }

    /// The control of the control: each label really does carry **its own** outcome into the guard.
    /// A `sample()` that answered someone else's variant would leave the case it was supposed to
    /// cover untested while the guard above stayed green.
    #[test]
    fn every_update_label_carries_its_own_outcome_into_the_guard() {
        for &t in EVERY_TAG {
            assert_eq!(
                tag(&sample(t)),
                t,
                "{t:?} builds a sample of another outcome, so {t:?} never reaches the guard"
            );
        }
    }

    /// hub#1763 — the answer of `POST /api/modules/:id/update` when the module was LOST reaches the
    /// shell in the ONE envelope it reads: `{ok, error, code}`, flat, the same as
    /// [`install_error_response`]. With the code nested in `error.code`, `updateModule`
    /// (`apps/web/src/lib/runtime.ts`) read `body.code` — nothing — fell back to `update_failed`,
    /// and the toast said «it keeps running the version it had» about a module that had just
    /// disappeared from the hub.
    #[tokio::test]
    async fn the_update_that_lost_the_module_answers_the_flat_envelope_the_shell_reads() {
        let response = update_lost_response("sales", "rollback failed");
        assert_eq!(response.status(), StatusCode::FAILED_DEPENDENCY);
        let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let body: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(body["ok"], false, "{body}");
        assert_eq!(body["code"], "module.update_lost", "{body}");
        let sentence = body["error"].as_str().unwrap_or_else(|| {
            panic!("`error` is the sentence the shell shows, not an object: {body}")
        });
        assert!(
            sentence.contains("sales") && sentence.contains("rollback failed"),
            "{sentence}"
        );
    }
    /// hub#1620 — «this app needs a newer hub» reaches the shell with its OWN code and the two
    /// numbers the translated sentence names, instead of `install_runtime_failed` + the engine's
    /// English line. `from_runtime` is the one door every runtime refusal of the pipeline takes.
    #[tokio::test]
    async fn an_app_that_needs_a_newer_hub_answers_its_code_and_both_versions() {
        let e = install::InstallError::from_runtime(
            erplora_runtime::RuntimeError::CoreVersionTooOld {
                module: "whatsapp_inbox".into(),
                required: "1.1.16".into(),
                core: "1.1.15".into(),
            },
        );
        let response = install_error_response(&e);
        assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
        let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let body: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(body["ok"], false, "{body}");
        assert_eq!(body["code"], "core_version_too_old", "{body}");
        assert_eq!(body["required"], "1.1.16", "{body}");
        assert_eq!(body["core"], "1.1.15", "{body}");
        assert_eq!(body["module_id"], "whatsapp_inbox", "{body}");
    }

    /// Every OTHER runtime refusal keeps travelling as `install_runtime_failed`: `from_runtime`
    /// lifts out the one fact the shell can act on, it does not reinvent the rest.
    #[test]
    fn other_runtime_refusals_stay_install_runtime_failed() {
        let e = install::InstallError::from_runtime(erplora_runtime::RuntimeError::Wasm("boom".into()));
        assert_eq!(e.code(), "install_runtime_failed");
    }
}
