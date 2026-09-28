//! Proxies towards the SaaS: catalogue, entitlement, blueprints, releases — split out of `lib.rs` verbatim (hub#1404).

use crate::*;

/// Fallo de un GET hub-scoped al Cloud: sin credencial (401 local) o error de red (502).
/// Separado de la respuesta HTTP para que cada proxy construya su body (p. ej.
/// `proxy_entitlement` añade el bloque `revalidation` también en el fallo).
pub(crate) enum CloudGetError {
    NoCredential,
    Network(String),
}

// ── The status a Cloud failure is REPORTED with (hub#1763) ──────────────────────────────────
//
// The hub is the ORIGIN, not a gateway. A `5xx` minted here is indistinguishable from the `5xx`
// the proxy in front of it mints on its own, so the edge answers with its OWN page and replaces
// the body — taking with it the stable `code` of hub#139 that the shell translates. What the
// business reads is `error code: 502`, on the marketplace, on its photos, on the staff tab, on the
// plan usage, on a blueprint import, on the assistant and on the account screen; and «it is down»,
// «this hub's credential was refused» and «that does not exist» all read the same, so the answer
// is to retry forever on a sentence that says nothing.
//
// hub#1720 closed this for the install pipeline (`install_error_status`); this is the same rule
// for the doors that PROXY. It applies to a status the hub RELAYS just as much as to one it mints:
// handing back the Cloud's own `500` puts the same page on the same screen.

/// What the hub answers when the thing that failed was the call to erplora.com: the hub did its
/// job and could not finish, which is what `424 Failed Dependency` says. A `4xx` crosses any proxy
/// with its body intact and still reads as a failure (`res.ok === false`) for the shell, so the
/// `code` survives the trip. Same status the install pipeline answers since hub#1720.
pub(crate) const CLOUD_FAILED: StatusCode = StatusCode::FAILED_DEPENDENCY;

/// The status the hub answers for an answer of erplora.com it is RELAYING. A `4xx` travels
/// untouched — «you are not allowed», «that does not exist» are facts about the request and read
/// the same from either end. A `5xx` does not: it becomes [`CLOUD_FAILED`], because a relayed
/// server error is swallowed by the edge exactly like a minted one.
pub(crate) fn relayed_status(cloud: StatusCode) -> StatusCode {
    if cloud.is_server_error() {
        CLOUD_FAILED
    } else {
        cloud
    }
}

/// The status erplora.com answered, as an `http::StatusCode`. A code outside 100–999 cannot cross
/// the wire, so the fallback is unreachable in practice; it stands for «the Cloud failed» and
/// [`relayed_status`] turns it into [`CLOUD_FAILED`] like any other server error.
pub(crate) fn cloud_status(raw: u16) -> StatusCode {
    StatusCode::from_u16(raw).unwrap_or(StatusCode::BAD_GATEWAY)
}

/// GET hub-scoped al Cloud con la credencial de máquina (o JWT de usuario como fallback).
/// Devuelve status + body crudos del Cloud. El **secreto de máquina nunca sale al navegador**:
/// el web llama a estas rutas del runtime y es el runtime quien firma la petición al Cloud.
pub(crate) async fn cloud_get_raw(
    st: &AppState,
    headers: &HeaderMap,
    req: cloud_client::PreparedRequest,
) -> Result<(StatusCode, axum::body::Bytes), CloudGetError> {
    cloud_get_raw_full(st, headers, req)
        .await
        .map(|(status, _retry_after, body)| (status, body))
}

/// Como [`cloud_get_raw`] pero devolviendo además el `Retry-After` en segundos cuando el Cloud lo
/// manda (hub#1167). Sólo lo necesita quien tiene que **dejar de llamar**: DRF pone esa cabecera
/// en sus 429 y es el único que sabe cuánto le queda a la ventana de la hora — en producción se
/// han visto 2828 s. Estimarla es peor que leerla, y seguir llamando durante ese rato mantiene
/// vacío un cubo de tokens que comparte toda la flota (saas#1640).
pub(crate) async fn cloud_get_raw_full(
    st: &AppState,
    headers: &HeaderMap,
    req: cloud_client::PreparedRequest,
) -> Result<(StatusCode, Option<i64>, axum::body::Bytes), CloudGetError> {
    let Some(auth) = auth::hub_scoped_auth(headers, st) else {
        return Err(CloudGetError::NoCredential);
    };
    let mut r = st.http.get(&req.url);
    for (k, v) in
        cloud_client::CloudClient::new(&st.config.cloud_base_url).headers_for(&req.url, &auth)
    {
        r = r.header(k, v);
    }
    if let Some(language) = headers.get(axum::http::header::ACCEPT_LANGUAGE) {
        r = r.header(axum::http::header::ACCEPT_LANGUAGE, language);
    }
    let resp = r
        .send()
        .await
        .map_err(|e| CloudGetError::Network(e.to_string()))?;
    let status = cloud_status(resp.status().as_u16());
    // `Retry-After` admite segundos o una fecha HTTP; DRF manda siempre segundos. Una fecha o un
    // valor ilegible se ignoran (=> `None`) y el llamador aplica su default acotado: preferimos
    // una ventana nuestra a una interpretación inventada de la ajena.
    let retry_after = resp
        .headers()
        .get(axum::http::header::RETRY_AFTER)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.trim().parse::<i64>().ok());
    let body = resp
        .bytes()
        .await
        .map_err(|e| CloudGetError::Network(e.to_string()))?;
    Ok((status, retry_after, body))
}

/// Respuesta HTTP para un [`CloudGetError`] (contrato previo de `proxy_cloud_get`, sin cambios).
pub(crate) fn cloud_get_error_response(e: CloudGetError) -> Response {
    match e {
        CloudGetError::NoCredential => (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": "hub sin credencial (ni token de máquina ni Authorization: Bearer)" })),
        )
            .into_response(),
        CloudGetError::Network(detail) => (
            CLOUD_FAILED,
            Json(json!({ "ok": false, "error": cloud_unreachable(&detail) })),
        )
            .into_response(),
    }
}

/// Hub-scoped GET to the Cloud, returning its JSON untouched (see [`cloud_get_raw`]).
pub(crate) async fn proxy_cloud_get(
    st: &AppState,
    headers: &HeaderMap,
    req: cloud_client::PreparedRequest,
) -> Response {
    match cloud_get_raw(st, headers, req).await {
        Ok((status, body)) => cloud_json_passthrough(status, body),
        Err(e) => cloud_get_error_response(e),
    }
}

/// Hub-scoped call to the Cloud with a method OTHER than GET, JSON in (when there is a body) and
/// the Cloud's status + bytes out. Same credential rule as [`cloud_get_raw`]: the machine secret
/// is materialised for THIS destination only (hub#1464) and never copied around.
///
/// The method comes from the [`cloud_client::PreparedRequest`] itself, so a door that the client
/// declares as `DELETE` cannot be sent as a `POST` by the handler that proxies it.
pub(crate) async fn cloud_send_raw(
    st: &AppState,
    headers: &HeaderMap,
    req: cloud_client::PreparedRequest,
    body: Option<&Value>,
) -> Result<(StatusCode, axum::body::Bytes), CloudGetError> {
    let Some(auth) = auth::hub_scoped_auth(headers, st) else {
        return Err(CloudGetError::NoCredential);
    };
    let method = reqwest::Method::from_bytes(req.method.as_bytes())
        .map_err(|e| CloudGetError::Network(e.to_string()))?;
    let mut r = st.http.request(method, &req.url);
    for (k, v) in
        cloud_client::CloudClient::new(&st.config.cloud_base_url).headers_for(&req.url, &auth)
    {
        r = r.header(k, v);
    }
    if let Some(language) = headers.get(axum::http::header::ACCEPT_LANGUAGE) {
        r = r.header(axum::http::header::ACCEPT_LANGUAGE, language);
    }
    if let Some(body) = body {
        r = r.json(body);
    }
    let resp = r
        .send()
        .await
        .map_err(|e| CloudGetError::Network(e.to_string()))?;
    let status = cloud_status(resp.status().as_u16());
    let bytes = resp
        .bytes()
        .await
        .map_err(|e| CloudGetError::Network(e.to_string()))?;
    Ok((status, bytes))
}

/// Hub-scoped non-GET call to the Cloud, returning its answer untouched (see [`cloud_send_raw`]).
pub(crate) async fn proxy_cloud_send(
    st: &AppState,
    headers: &HeaderMap,
    req: cloud_client::PreparedRequest,
    body: Option<&Value>,
) -> Response {
    match cloud_send_raw(st, headers, req, body).await {
        Ok((status, bytes)) => cloud_body_passthrough(status, bytes),
        Err(e) => cloud_get_error_response(e),
    }
}

/// Like [`cloud_json_passthrough`], but an EMPTY answer stays empty: a `204 No Content` (what the
/// SaaS returns when it drops a WhatsApp template) must not grow a `content-type: application/json`
/// and a zero-byte body that `response.json()` in the browser then chokes on.
pub(crate) fn cloud_body_passthrough(status: StatusCode, body: axum::body::Bytes) -> Response {
    if body.is_empty() {
        return status.into_response();
    }
    cloud_json_passthrough(status, body)
}

// ── The ENVELOPE, for the proxy doors a MODULE can reach (hub#1688) ──────────────────────────
//
// Everything above hands the SaaS's body back as it came, and for the doors the SHELL calls that
// is right: `apps/web/src/lib/runtime.ts` fetches them itself and reads the SaaS's own fields.
//
// A door a MODULE reaches is a different contract. Module code never fetches: it goes through
// `@erplora/module-sdk`, whose transport ends EVERY call in `unwrap(env)` — «the runtime always
// answers `application/json`, even its 4xx domain refusal travels in an envelope with a `code`»
// (`packages/module-sdk/src/index.ts`). Query, command, flows, events, print and the media list
// all answer that way; so must a proxy the SDK can call, or the module gets `unknown error` with
// the code stripped off, which is exactly what hub#1682 shipped.
//
// Wrapping does NOT reinterpret the SaaS: the payload travels whole inside `data` and a refusal
// keeps its own `code`. It is the opposite — the envelope is the only channel through which that
// code reaches the module at all, which is what `whatsapp_templates.rs` wanted from the passthrough
// and did not get.

/// The SaaS answered and said no, and did not name a code (DRF's own throttle and auth failures
/// answer `detail` and nothing else). Same code the members and fiscal-identity doors use.
pub(crate) const CLOUD_REJECTED: &str = "cloud_rejected";
/// The SaaS did not answer at all (network, DNS, timeout): nothing to correct, retry later.
pub(crate) const CLOUD_UNREACHABLE: &str = "cloud_unreachable";

/// The `reqwest` detail of a call that never got through, sent WHERE IT BELONGS (hub#1689).
///
/// Its `Display` is `error sending request for url (http://…/api/v1/…)`: the address this hub
/// dials erplora.com on, and the path it dialled. An operator needs both — the business does not,
/// and neither is ours to hand out on a marketplace screen. So the detail goes to the hub's log,
/// and the caller gets back the stable code it can branch on, translate and retry.
///
/// It is the policy `/api/command` and `/api/query` have applied since hub#1074
/// (`error_redaction_door`) and the WhatsApp template doors since hub#1688; this is the same rule
/// for the doors that answer outside the envelope. Callers keep their own body shape — the string
/// IS the code, which is how the shell already reads this key (`refusalCode`, `grantFailure`).
///
/// "Network" here is the whole round trip, as [`CloudGetError::Network`] already means: a
/// connection that was refused and a body that stopped arriving are the same fact for whoever is
/// looking at the screen — erplora.com did not answer, try again.
pub(crate) fn cloud_unreachable(detail: &str) -> &'static str {
    tracing::warn!(detail = %detail, "erplora.com did not answer");
    CLOUD_UNREACHABLE
}
/// This hub has no machine credential, so there is no door to knock on (a local `pnpm dev`).
pub(crate) const HUB_NOT_ENROLLED: &str = "hub_not_enrolled";
/// The SaaS answered `2xx` with something that is not JSON — a proxy's HTML page, most likely.
pub(crate) const CLOUD_UNREADABLE: &str = "cloud_unreadable";

/// The runtime's envelope over a Cloud answer, for the doors module code reaches.
///
/// Success keeps the Cloud's status and carries its payload whole in `data`; an EMPTY body stays
/// empty (a `204` is «done» by definition of the status, and the SDK reads it as such). A refusal
/// keeps the Cloud's status too, and its `code` — `{"error": "invalid_name"}` becomes
/// `error.code = "invalid_name"` — with `detail` as the sentence for whoever never translated it.
pub(crate) fn cloud_envelope_passthrough(status: StatusCode, body: axum::body::Bytes) -> Response {
    if status.is_success() {
        if body.is_empty() {
            return status.into_response();
        }
        return match serde_json::from_slice::<Value>(&body) {
            Ok(data) => (status, Json(json!({ "ok": true, "data": data }))).into_response(),
            Err(e) => {
                tracing::warn!(status = status.as_u16(), error = %e, "erplora.com answered a success the hub could not read");
                envelope_error(
                    CLOUD_FAILED,
                    CLOUD_UNREADABLE,
                    "erplora.com answered with a body the hub could not read",
                )
            }
        };
    }
    // erplora.com CRASHED. There is no domain code to carry — DRF answers `{"detail": "Server
    // Error (500)"}`, its own English prose — and relaying the `5xx` hands the edge licence to
    // replace this body with its page (hub#1763). One code, one sentence, and a status that
    // crosses: what the module reads is «erplora.com could not attend to this», not `unknown
    // error`.
    if status.is_server_error() {
        tracing::warn!(
            status = status.as_u16(),
            "erplora.com answered a server error"
        );
        return envelope_error(
            CLOUD_FAILED,
            CLOUD_REJECTED,
            "erplora.com could not attend to this request",
        );
    }
    // A refusal: the Cloud's own `code` is the contract (saas#1902) and travels untouched. What it
    // never named, we name `cloud_rejected` rather than dropping — a refusal with no code at all is
    // the `unknown error` this whole envelope exists to stop.
    let parsed: Option<Value> = serde_json::from_slice(&body).ok();
    let code = parsed
        .as_ref()
        .and_then(|v| v.get("error"))
        .and_then(Value::as_str)
        .unwrap_or(CLOUD_REJECTED);
    let message = parsed
        .as_ref()
        .and_then(|v| v.get("detail"))
        .and_then(Value::as_str)
        .map(str::to_owned)
        .unwrap_or_else(|| code.to_owned());
    envelope_error(status, code, &message)
}

/// [`cloud_envelope_passthrough`] for a refusal whose `5xx` the SaaS NAMED on purpose.
///
/// The shared passthrough drops the code of a `5xx`, because a DRF crash names none. Some doors
/// name one deliberately — `502 media_unavailable` (hub#2114), `503 whatsapp_not_configured` and
/// `502 meta_template_failed` (hub#2232) — and that name is what lets the module offer «Retry» or
/// «reconnect WhatsApp» instead of «error». So a `5xx` that carries a code keeps it, still under
/// [`CLOUD_FAILED`] so the edge does not swap the body for its page (hub#1763); one that does not
/// (a real crash) falls through to the passthrough and reads `cloud_rejected`.
pub(crate) fn cloud_envelope_named_refusal(
    status: StatusCode,
    body: axum::body::Bytes,
) -> Response {
    if status.is_server_error() {
        let named = serde_json::from_slice::<Value>(&body).ok().and_then(|v| {
            let code = v.get("error")?.as_str()?.to_string();
            let detail = v
                .get("detail")
                .and_then(Value::as_str)
                .map(str::to_owned)
                .unwrap_or_else(|| code.clone());
            Some((code, detail))
        });
        if let Some((code, detail)) = named {
            tracing::warn!(
                status = status.as_u16(),
                code = %code,
                "erplora.com named its server error"
            );
            return envelope_error(CLOUD_FAILED, &code, &detail);
        }
    }
    cloud_envelope_passthrough(status, body)
}

/// One refusal, one shape: `{"ok": false, "error": {"code", "message"}}` — what `unwrap` reads.
fn envelope_error(status: StatusCode, code: &str, message: &str) -> Response {
    (
        status,
        Json(json!({ "ok": false, "error": { "code": code, "message": message } })),
    )
        .into_response()
}

/// [`cloud_get_error_response`] in the envelope shape, for the same doors.
///
/// The `reqwest` detail does NOT travel: it carries the control plane's internal URL
/// (`error_redaction_door`), and a module has nothing to do with it. It goes to the hub's log,
/// which is where an operator looks — the caller gets a code it can act on and retry.
pub(crate) fn cloud_envelope_error_response(e: CloudGetError) -> Response {
    match e {
        CloudGetError::NoCredential => envelope_error(
            StatusCode::UNAUTHORIZED,
            HUB_NOT_ENROLLED,
            "this hub has no machine credential for erplora.com",
        ),
        CloudGetError::Network(detail) => envelope_error(
            CLOUD_FAILED,
            cloud_unreachable(&detail),
            "the hub could not reach erplora.com",
        ),
    }
}

/// [`proxy_cloud_get`] for a door module code reaches: same call, [`cloud_envelope_passthrough`]
/// on the way out.
pub(crate) async fn proxy_cloud_get_enveloped(
    st: &AppState,
    headers: &HeaderMap,
    req: cloud_client::PreparedRequest,
) -> Response {
    match cloud_get_raw(st, headers, req).await {
        Ok((status, body)) => cloud_envelope_passthrough(status, body),
        Err(e) => cloud_envelope_error_response(e),
    }
}

/// [`proxy_cloud_send`] for a door module code reaches (see [`proxy_cloud_get_enveloped`]).
pub(crate) async fn proxy_cloud_send_enveloped(
    st: &AppState,
    headers: &HeaderMap,
    req: cloud_client::PreparedRequest,
    body: Option<&Value>,
) -> Response {
    match cloud_send_raw(st, headers, req, body).await {
        Ok((status, bytes)) => cloud_envelope_passthrough(status, bytes),
        Err(e) => cloud_envelope_error_response(e),
    }
}

/// Hands the front the Cloud's JSON as it came: same status, `no-store`, nothing reinterpreted.
///
/// With ONE exception, and it is the point of hub#1763: a `5xx` of erplora.com is not relayed.
/// Relaying it hands the edge licence to replace this body with its own `error code: 502` page, so
/// what the business reads on the marketplace, on its photos or on the plan usage is the proxy's
/// page instead of a reason. The status becomes [`CLOUD_FAILED`] and the body becomes OURS: the
/// Cloud's crash carries no domain code, only DRF's English prose, and that prose is not for a
/// Spanish screen (hub#1214).
pub(crate) fn cloud_json_passthrough(status: StatusCode, body: axum::body::Bytes) -> Response {
    if status.is_server_error() {
        tracing::warn!(
            status = status.as_u16(),
            "erplora.com answered a server error"
        );
        return (
            CLOUD_FAILED,
            [(axum::http::header::CACHE_CONTROL, "no-store")],
            Json(json!({ "ok": false, "error": CLOUD_REJECTED })),
        )
            .into_response();
    }
    (
        status,
        [
            (axum::http::header::CONTENT_TYPE, "application/json"),
            (axum::http::header::CACHE_CONTROL, "no-store"),
        ],
        body,
    )
        .into_response()
}

/// GET público al Cloud. Solo se usa para metadatos publicados del catálogo Demo; nunca para
/// descargas, entitlement ni operaciones de un Hub. No añade identidad de usuario o máquina.
pub(crate) async fn proxy_public_cloud_get(
    st: &AppState,
    headers: &HeaderMap,
    req: cloud_client::PreparedRequest,
) -> Response {
    let mut request = st.http.get(&req.url);
    for (name, value) in req.headers {
        request = request.header(name, value);
    }
    if let Some(language) = headers.get(axum::http::header::ACCEPT_LANGUAGE) {
        request = request.header(axum::http::header::ACCEPT_LANGUAGE, language);
    }
    let response = match request.send().await {
        Ok(response) => response,
        Err(error) => {
            return (
                CLOUD_FAILED,
                Json(json!({ "ok": false, "error": cloud_unreachable(&error.to_string()) })),
            )
                .into_response()
        }
    };
    let status = cloud_status(response.status().as_u16());
    match response.bytes().await {
        // Same rule as the hub-scoped doors: a `5xx` of erplora.com does not travel, or the edge
        // replaces it with its page and the marketplace catalogue reads `error code: 502`
        // (hub#1763). `cloud_json_passthrough` is the one place that decides it.
        Ok(body) => cloud_json_passthrough(status, body),
        Err(error) => (
            CLOUD_FAILED,
            Json(json!({ "ok": false, "error": cloud_unreachable(&error.to_string()) })),
        )
            .into_response(),
    }
}

/// GET /api/entitlement — entitlement firmado del hub (proxy de `/api/v1/hub/device/entitlement/`).
///
/// **Aditivo** (revalidación híbrida, `crate::entitlement`): a la respuesta del Cloud se le añade
/// el bloque `revalidation` (`blocked_modules` + `grace_until` + `last_check`…) con el estado
/// local del job periódico — también cuando el Cloud no responde (fallo de red), que es justo
/// cuando la UI necesita pintar «funcionará hasta {fecha}». El contrato previo no cambia:
/// mismo status y mismos campos, solo se AÑADE la clave.
pub(crate) async fn proxy_entitlement(State(st): State<AppState>, headers: HeaderMap) -> Response {
    {
        let rt = st.runtime.read().await;
        if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    // `entitlement(auth)` solo usa `auth` para las cabeceras; las reescribe `cloud_get_raw`.
    let placeholder = cloud_client::Auth::HubToken {
        hub_id: st.hub_id(),
        token: String::new(),
    };

    // Estado local de revalidación sobre los módulos INSTALADOS de este hub.
    let installed: Vec<String> = {
        let rt = st.runtime.read().await;
        rt.modules().into_iter().map(|m| m.id).collect()
    };
    let revalidation = st
        .entitlement
        .read()
        .map(|g| g.revalidation_json(&installed, entitlement::now_unix()))
        .unwrap_or(Value::Null);

    let now = entitlement::now_unix();

    // ¿Hace falta salir a la red? El shell pregunta una vez por `focus` de ventana y otra por cada
    // vista de módulo que monta; sin este corte cada una de esas veces era una llamada al SaaS.
    let decision = st
        .entitlement_proxy
        .read()
        .map(|cache| cache.decide(now))
        .unwrap_or(entitlement::Decision::Ask);
    match decision {
        entitlement::Decision::Serve(body) => {
            return entitlement_response(StatusCode::OK, body, revalidation)
        }
        entitlement::Decision::RateLimited => return rate_limited_response(revalidation),
        entitlement::Decision::Ask => {}
    }

    match cloud_get_raw_full(&st, &headers, cloud.entitlement(&placeholder)).await {
        // El SaaS nos está limitando la tasa. Ni el status ni su prosa pueden llegar al navegador:
        // el shell lee el error como «no hay módulos» y degrada pantallas de módulos ya comprados,
        // y el `{"detail":"Request was throttled…"}` de DRF es inglés dentro de una UI en español.
        Ok((StatusCode::TOO_MANY_REQUESTS, retry_after, _body)) => {
            let served = match st.entitlement_proxy.write() {
                Ok(mut cache) => {
                    cache.open_backoff(retry_after, now);
                    cache.last_good().cloned()
                }
                Err(_) => None,
            };
            report_cloud_rate_limited(retry_after, served.is_some());
            match served {
                Some(body) => entitlement_response(StatusCode::OK, body, revalidation),
                None => rate_limited_response(revalidation),
            }
        }
        // erplora.com crashed. Its body carries no entitlement and no code — and relayed as a
        // `5xx` it would be replaced by the edge's page (hub#1763), so the shell could not even
        // read `revalidation`, which is the ONE thing it needs here: «this hub works until
        // {date}». Same shape as the branch below, which is the other way this call fails.
        Ok((status, _retry_after, _body)) if status.is_server_error() => {
            tracing::warn!(
                status = status.as_u16(),
                "erplora.com answered a server error"
            );
            (
                CLOUD_FAILED,
                Json(json!({
                    "ok": false,
                    "error": CLOUD_REJECTED,
                    "revalidation": revalidation,
                })),
            )
                .into_response()
        }
        Ok((status, _retry_after, body)) => match serde_json::from_slice::<Value>(&body) {
            // Body objeto JSON → se le inyecta la clave aditiva.
            Ok(Value::Object(obj)) => {
                // Sólo se guarda lo que el Cloud dio por bueno: cachear un 4xx/5xx lo convertiría
                // en la verdad del hub durante toda la ventana de frescura.
                if status.is_success() {
                    if let Ok(mut cache) = st.entitlement_proxy.write() {
                        cache.store_success(Value::Object(obj.clone()), now);
                    }
                }
                entitlement_response(status, Value::Object(obj), revalidation)
            }
            // Body no-objeto (raro: HTML de error, vacío) → tal cual, como antes.
            _ => (
                status,
                [(axum::http::header::CONTENT_TYPE, "application/json")],
                body,
            )
                .into_response(),
        },
        Err(CloudGetError::Network(detail)) => (
            CLOUD_FAILED,
            Json(json!({
                "ok": false,
                "error": cloud_unreachable(&detail),
                "revalidation": revalidation,
            })),
        )
            .into_response(),
        Err(e) => cloud_get_error_response(e),
    }
}

/// Respuesta del proxy de entitlement: el cuerpo del Cloud con el bloque aditivo `revalidation`,
/// que SIEMPRE se recalcula (es estado local, y es justo lo que la UI necesita cuando el Cloud no
/// contesta) y por eso nunca se guarda en la caché.
pub(crate) fn entitlement_response(
    status: StatusCode,
    body: Value,
    revalidation: Value,
) -> Response {
    match body {
        Value::Object(mut obj) => {
            obj.insert("revalidation".into(), revalidation);
            (status, Json(Value::Object(obj))).into_response()
        }
        other => (status, Json(other)).into_response(),
    }
}

/// El único caso en que el rate-limit del Cloud se le cuenta al shell: no había ningún entitlement
/// bueno que servir. Viaja con **código estable** en el envelope de siempre
/// (`{"ok":false,"error":{"code":…}}`) para que la UI lo traduzca por código (ADR-0055) en vez de
/// pintar la frase inglesa que escribió DRF.
pub(crate) fn rate_limited_response(revalidation: Value) -> Response {
    (
        StatusCode::TOO_MANY_REQUESTS,
        Json(json!({
            "ok": false,
            "error": {
                "code": entitlement::CLOUD_RATE_LIMITED,
                "message": "the Cloud is rate-limiting this hub; the entitlement could not be refreshed",
            },
            "revalidation": revalidation,
        })),
    )
        .into_response()
}

/// Deja el rate-limit VISIBLE. Un límite que falla en silencio es peor que uno que grita: sin esto
/// la única huella era una línea roja en la consola del navegador del cajero, que nadie recoge.
/// Va al log del runtime **y** al registro de errores, que es el canal que llega al Cloud.
pub(crate) fn report_cloud_rate_limited(retry_after: Option<i64>, served_from_cache: bool) {
    use erplora_runtime::error_registry::{ErrorEvent, ErrorRegistry};

    tracing::warn!(
        retry_after_secs = retry_after.unwrap_or(-1),
        served_from_cache,
        "el Cloud limita la tasa del entitlement (saas#1640)"
    );
    ErrorRegistry::global().report(
        ErrorEvent::new(
            erplora_runtime::error_registry::source::HUB,
            entitlement::CLOUD_RATE_LIMITED,
            "el Cloud respondió 429 al refrescar el entitlement",
            erplora_runtime::error_registry::severity::UNEXPECTED,
        )
        .with_context(json!({
            "retry_after_secs": retry_after,
            // `cache` = el cajero no se enteró; `none` = se le contó el fallo, que es lo grave.
            "outcome": if served_from_cache { "cache" } else { "none" },
        })),
    );
}

/// GET /api/marketplace/catalog — the real marketplace catalogue.
///
/// A registered Hub uses `/api/v1/marketplace/modules/` with its machine token so the answer is
/// scoped to that Hub. Demo, the one exception to registration, consumes the public metadata
/// catalogue `/api/v1/marketplace/catalog/`; no protected operation ever becomes public.
///
/// **On the way through it records what the marketplace offered** (hub#371). This is the only time
/// the hub ever sees the catalogue, and the "your apps" item of `hub.setup.status` needs it to tell
/// *"you still have to install an app"* apart from *"there is nothing you can install"* — which is
/// not the user's task but our own breakdown. The query cannot ask for itself: it is read by the
/// dashboard, by the assistant and by a strip on every screen, so a round-trip to the SaaS would put
/// the control plane on the critical path of every page. The whole rule of what counts as an answer
/// lives in `setup_status::record_catalog_response`, not here: a 403 or an odd body records nothing.
///
/// Demo is deliberately left out: its public catalogue is SaaS metadata, not *"what THIS hub can
/// install"*, so counting its rows would answer a different question.
/// Which build of the installable app the Cloud publishes right now (hub#400).
///
/// The page asks the runtime instead of the Cloud because it is served under
/// `connect-src 'self' ipc:`: a cross-origin fetch dies in the browser, without a log the till
/// could show. Here there is no CSP and the Cloud address is already configured.
///
/// **No credential travels.** The version of a public download is public (it is on the store
/// listing), and asking anonymously is what lets a hub in demo, unenrolled or just woken up still
/// tell its till that a newer app exists — with a token those hubs would get a 401, which the page
/// reads as "nothing new". Note the asymmetry with the marketplace proxy right above: that one
/// grants entitlements, this one reports a number.
///
/// A Cloud that does not answer produces an error status, never a version: the page turns anything
/// that is not a version into `unknown` — silence — and a number invented here would point a till
/// at an installer that does not exist.
pub(crate) async fn proxy_app_release(State(st): State<AppState>, headers: HeaderMap) -> Response {
    {
        let rt = st.runtime.read().await;
        if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    proxy_public_cloud_get(&st, &headers, cloud.app_release()).await
}

/// `GET /api/marketplace/modules/:id` — lo que el marketplace dice de UN módulo, tal cual (hub#1134).
///
/// **Por qué no vale el catálogo**: el listado del marketplace sólo sirve `publication_status =
/// 'listed'`, así que un módulo RETIRADO (ADR-0380) que este hub ya tiene sencillamente no sale en
/// él — y ese es exactamente el que «Mis apps» tiene que poder distinguir de uno sano. La puerta de
/// detalle sí contesta por él, y contesta al token de máquina del propio hub.
///
/// El cuerpo viaja **sin tocar**: `publication_status` lo lee la pantalla; aquí no se interpreta
/// nada. Un Cloud que no contesta es un 502, nunca un estado inventado — «no lo sé» y «se sigue
/// ofreciendo» son hechos distintos y la pantalla no pinta ninguno de los dos por el otro.
pub(crate) async fn proxy_marketplace_module(
    State(st): State<AppState>,
    Path(module_id): Path<String>,
    headers: HeaderMap,
) -> Response {
    {
        let rt = st.runtime.read().await;
        if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }
    // El id se incrusta en una ruta del Cloud FIRMADA con el token de máquina, así que se comprueba
    // antes de llegar ahí: axum ya lo ha percent-decodificado, y un `..` por el medio sacaría al
    // proxy del marketplace hacia cualquier otro endpoint del Cloud con la credencial del hub.
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
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    let placeholder = cloud_client::Auth::HubToken {
        hub_id: st.hub_id(),
        token: String::new(),
    };
    proxy_cloud_get(&st, &headers, cloud.module_detail(&placeholder, &module_id)).await
}

/// ¿Se puede meter este id en una ruta del Cloud sin salirse de ella? (hub#1134)
///
/// El alfabeto de un slug de módulo y nada más: sin `/`, sin `.`, sin `%`, y nunca vacío. Todo lo
/// que llega por `:id` y acaba dentro de una URL del Cloud pasa por aquí — una regla en un sitio,
/// no una comprobación distinta por handler.
pub(crate) fn module_id_is_safe(module_id: &str) -> bool {
    !module_id.is_empty()
        && module_id.len() <= 128
        && module_id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
}

pub(crate) async fn proxy_marketplace_catalog(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<LocaleQuery>,
) -> Response {
    // **The country the catalogue is asked about is read HERE, from this hub's own settings**
    // (ADR-0062, hub#69) — never from the request. The page cannot widen what its till is offered,
    // and it does not have to know the rule: what comes back is already filtered.
    //
    // **The language is the opposite case, and on purpose** (hub#1003, ADR-0364). The Cloud serves
    // the catalogue per language now, but only to a caller that says which one — silence means
    // English, which is the bug. Unlike the country, it comes from `?locale=` (ADR-0055, the same
    // param `navigation` takes): the country is a fact about the *hub* and a page must not be able
    // to widen it, whereas the language is a fact about the *person reading right now*, and only
    // the page knows which one that is. Widening nothing is exactly what it can do with it.
    //
    // The hub's stored `language` is the fallback, not the source — that is what serves a caller
    // that has not said (an old web build, a script), and it beats defaulting to English for a hub
    // that has told us in its settings which language it reads in.
    let catalog = {
        let rt = st.runtime.read().await;
        if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
        let (country_code, region_code) = rt.country_and_region().await;
        let requested = q.locale.unwrap_or_default();
        let language = if requested.trim().is_empty() {
            rt.language().await
        } else {
            requested
        };
        cloud_client::CatalogQuery::new(
            cloud_client::CountryFilter::new(&country_code, &region_code),
            &language,
        )
    };
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    if st.is_dev_hub() {
        return proxy_public_cloud_get(&st, &headers, cloud.public_marketplace_modules(&catalog))
            .await;
    }
    let placeholder = cloud_client::Auth::HubToken {
        hub_id: st.hub_id(),
        token: String::new(),
    };
    match cloud_get_raw(
        &st,
        &headers,
        cloud.marketplace_modules(&placeholder, &catalog),
    )
    .await
    {
        Ok((status, body)) => {
            let rt = st.runtime.read().await;
            if let Err(e) = erplora_runtime::setup_status::record_catalog_response(
                rt.db(),
                status.as_u16(),
                &body,
            )
            .await
            {
                // Recording is a side effect of the proxy: if it fails the catalogue is served all
                // the same and the checklist is left not knowing — which is "pending", never a
                // false "unavailable".
                tracing::warn!(error = %e, "could not record the catalogue offer for the checklist");
            }
            cloud_json_passthrough(status, body)
        }
        Err(e) => cloud_get_error_response(e),
    }
}

/// GET /api/blueprints/catalog — catálogo de blueprints (proxy de `/api/v1/catalog/blueprints/`).
///
/// La **«fuente nube»** del panel de import (Ajustes → Datos). [ADR-0121]
pub(crate) async fn proxy_blueprints_catalog(
    State(st): State<AppState>,
    headers: HeaderMap,
) -> Response {
    {
        let rt = st.runtime.read().await;
        if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    let placeholder = cloud_client::Auth::HubToken {
        hub_id: st.hub_id(),
        token: String::new(),
    };
    proxy_cloud_get(&st, &headers, cloud.blueprints_catalog(&placeholder)).await
}

/// GET /api/blueprints/:slug/download — baja el `.blueprint.zip` y lo sirve al front.
///
/// El runtime hace de intermediario a propósito (ADR-0003): pide al SaaS la **URL firmada** con su
/// `X-Hub-Token` —que **nunca** llega al navegador—, descarga el zip de Object Storage y
/// **verifica el SHA256 ANTES de entregarlo**. Un hash que no casa aborta con 502 sin devolver
/// bytes: es el mismo contrato no-saltable que el install de módulos (ADR-0015).
///
/// Devuelve el zip crudo, así que el front lo trata **igual que un fichero local** y reusa el
/// flujo existente `inspect` → `import` (cero lógica de import duplicada).
pub(crate) async fn download_blueprint(
    State(st): State<AppState>,
    Path(slug): Path<String>,
    headers: HeaderMap,
) -> Response {
    {
        let rt = st.runtime.read().await;
        if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
            return unauthorized(e);
        }
    }
    // Credencial hub-scoped: el token de máquina NUNCA llega al navegador (ADR-0003).
    let Some(auth) = auth::hub_scoped_auth(&headers, &st) else {
        return cloud_get_error_response(CloudGetError::NoCredential);
    };
    // El panel de import baja por slug sin idioma: si el catálogo tuviera ese slug en dos idiomas,
    // el SaaS contesta 400 y el front lo enseña — elegir uno al azar sería peor.
    match fetch_blueprint(&st, &auth, &slug, None).await {
        Ok(fetched) => (
            StatusCode::OK,
            [(axum::http::header::CONTENT_TYPE, "application/zip")],
            fetched.zip,
        )
            .into_response(),
        // The SaaS's own refusal (a slug in two languages is a 400 the panel shows), relayed by
        // the one place that decides what a `5xx` of erplora.com becomes (hub#1763).
        Err(BlueprintFetchError::Cloud { status, body }) => cloud_json_passthrough(status, body),
        Err(BlueprintFetchError::Network(msg)) => {
            cloud_get_error_response(CloudGetError::Network(msg))
        }
        Err(BlueprintFetchError::Other(msg)) => cloud_failed(msg),
    }
}

/// Un `.blueprint.zip` ya descargado y **verificado**, con la versión que dijo el SaaS.
pub(crate) struct FetchedBlueprint {
    pub zip: axum::body::Bytes,
    pub version: String,
}

/// Por qué no se pudo traer un blueprint. Separa lo que el SaaS contestó (se reenvía tal cual al
/// front) de lo que pasó de camino, para que el llamador HTTP conserve su contrato de error.
pub(crate) enum BlueprintFetchError {
    /// El SaaS contestó un status de error (404 sin bundle, 400 slug ambiguo, 5xx…).
    Cloud {
        status: StatusCode,
        body: axum::body::Bytes,
    },
    /// No se pudo hablar con el Cloud / con Object Storage.
    Network(String),
    /// Respuesta ilegible o **integridad rota**: el mensaje ya es legible.
    Other(String),
}

impl BlueprintFetchError {
    /// Motivo en una línea (log, informe de error al Cloud).
    pub fn message(&self) -> String {
        match self {
            BlueprintFetchError::Cloud { status, body } => format!(
                "el SaaS contestó {status} al resolver el blueprint: {}",
                String::from_utf8_lossy(body)
            ),
            BlueprintFetchError::Network(msg) => msg.clone(),
            BlueprintFetchError::Other(msg) => msg.clone(),
        }
    }
}

/// Resuelve, descarga y **verifica** un `.blueprint.zip` del catálogo del SaaS.
///
/// Es el cuerpo de [`download_blueprint`] sin el guard de sesión de usuario, porque el arranque
/// (ADR-0212) hace exactamente esto **sin nadie logueado**: se autentica con el token de máquina.
/// El orden no es negociable (ADR-0015/ADR-0121): 1) el SaaS da URL firmada + `sha256`, 2) se baja
/// el zip de Object Storage, 3) **se verifica el hash ANTES de devolver un solo byte**.
pub(crate) async fn fetch_blueprint(
    st: &AppState,
    auth: &cloud_client::Auth,
    slug: &str,
    locale: Option<&str>,
) -> Result<FetchedBlueprint, BlueprintFetchError> {
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    let req = cloud.blueprint_download(slug, locale, auth);

    // 1) URL firmada + sha256 + versión (hub-scoped: se autentica el runtime, no el usuario).
    let mut r = st.http.get(&req.url);
    for (k, v) in cloud.headers_for(&req.url, auth) {
        r = r.header(k, v);
    }
    let resp = r
        .send()
        .await
        .map_err(|e| BlueprintFetchError::Network(e.to_string()))?;
    let status = cloud_status(resp.status().as_u16());
    let body = resp
        .bytes()
        .await
        .map_err(|e| BlueprintFetchError::Network(e.to_string()))?;
    if !status.is_success() {
        return Err(BlueprintFetchError::Cloud { status, body });
    }

    let info: Value = serde_json::from_slice(&body)
        .map_err(|e| BlueprintFetchError::Other(format!("respuesta de blueprint ilegible: {e}")))?;
    let (Some(url), Some(expected)) = (info["url"].as_str(), info["sha256"].as_str()) else {
        return Err(BlueprintFetchError::Other(
            "el SaaS no expuso url/sha256 del blueprint".to_string(),
        ));
    };
    let version = info["version"].as_str().unwrap_or_default().to_string();

    // 2) Descarga directa de Object Storage (URL prefirmada: sin credenciales nuestras).
    let zip = match st.http.get(url).send().await {
        Ok(r) if r.status().is_success() => r
            .bytes()
            .await
            .map_err(|e| BlueprintFetchError::Network(format!("descarga interrumpida: {e}")))?,
        Ok(r) => {
            return Err(BlueprintFetchError::Other(format!(
                "Object Storage devolvió {} al bajar el blueprint",
                r.status()
            )))
        }
        Err(e) => {
            return Err(BlueprintFetchError::Network(format!(
                "no se pudo descargar el blueprint: {e}"
            )))
        }
    };

    // 3) 🔴 Integridad NO-SALTABLE (ADR-0015): si el hash no casa, no se entrega ni un byte.
    let actual = {
        use sha2::{Digest, Sha256};
        let mut h = Sha256::new();
        h.update(&zip);
        format!("{:x}", h.finalize())
    };
    if actual != expected {
        return Err(BlueprintFetchError::Other(format!(
            "integridad del blueprint «{slug}»: sha256 esperado {expected}, obtenido {actual} — import abortado"
        )));
    }

    Ok(FetchedBlueprint { zip, version })
}

/// «La llamada a erplora.com es lo que falló», con el motivo en JSON: mismo contrato de error que
/// el resto de proxies y el mismo status, [`CLOUD_FAILED`] — un `5xx` aquí se lo comería el borde
/// y el motivo no llegaría a la pantalla (hub#1763).
pub(crate) fn cloud_failed(reason: String) -> Response {
    (CLOUD_FAILED, Json(json!({ "ok": false, "error": reason }))).into_response()
}
