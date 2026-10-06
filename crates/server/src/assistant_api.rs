//! Assistant endpoints: config, checkout and the SSE chat stream — split out of `lib.rs` verbatim (hub#1404).

use crate::*;

/// POST /api/assistant/chat/stream — proxy SSE hacia el Cloud (ARQUITECTURA.md §9.3).
/// Reenvía el `Authorization: Bearer` + `X-Hub-Id` entrantes; ensambla las tools permitidas
/// (§9.2) y traduce el stream del Cloud al contrato del frontend (`token`/`done`).
/// **Qué plan tiene este hub** (saas#1540): tier, consumo del mes y planes contratables.
///
/// El hub solo descubría su plan cuando ya lo había AGOTADO, así que quedarse sin mensajes solo
/// podía presentarse como una avería. Va por el runtime y no desde el navegador porque la
/// credencial hub-scoped es **secreto del runtime** (ADR-0003): el web app no tiene —ni debe
/// tener— con qué firmar esta llamada.
///
/// Reutiliza `proxy_cloud_get`, que ya devuelve el JSON del Cloud sin reinterpretar: un 402/429
/// del SaaS es información que el llamador necesita, y traducirlo a un genérico es exactamente el
/// fallo que esta issue documenta.
pub(crate) async fn assistant_config(State(st): State<AppState>, headers: HeaderMap) -> Response {
    // The hub's machine token further down (`hub_scoped_auth`) is the credential the runtime uses
    // to TALK to the Cloud, not a gate on who is asking (ADR-0003): without this session check the
    // route answered anybody who reached the hub's URL — ERPlora/hub#1254. A read any signed-in
    // user needs (the drawer prints the tier and what is left of the month), so: session.
    {
        let rt = st.runtime.read().await;
        if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
            return auth_rejected(e);
        }
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    let placeholder = cloud_client::Auth::HubToken {
        hub_id: String::new(),
        token: String::new(),
    };
    proxy_cloud_get(&st, &headers, cloud.assistant_config(&placeholder)).await
}

/// **Abrir el checkout del plan del asistente** (saas#1540, ADR-0033) → `{"checkout_url": …}`.
///
/// Sin este camino, un «ver planes» no lleva a ninguna parte: el único momento de conversión del
/// tier gratuito moría en una frase.
pub(crate) async fn assistant_checkout(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(body): Json<Value>,
) -> Response {
    // Contracting the plan is billed to the hub, so it is the ADMIN door — the same one as
    // settings, API keys and the certificate. Until ERPlora/hub#1254 the only credential here was
    // the OUTBOUND machine token, and any anonymous caller who reached the hub could open Stripe
    // checkout sessions in its name.
    {
        let rt = st.runtime.read().await;
        if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
            return auth_rejected(e);
        }
    }
    let Some(auth) = auth::hub_scoped_auth(&headers, &st) else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": "hub sin credencial" })),
        )
            .into_response();
    };
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    let req = cloud.assistant_checkout(&auth);
    let mut r = st.http.post(&req.url);
    for (k, v) in cloud.headers_for(&req.url, &auth) {
        r = r.header(k, v);
    }
    match r.json(&body).send().await {
        Ok(resp) => {
            let status = cloud_proxy::cloud_status(resp.status().as_u16());
            let bytes = resp.bytes().await.unwrap_or_default();
            cloud_json_passthrough(status, bytes)
        }
        // Never a `5xx` of our own: the edge replaces that body with its page and the assistant
        // drawer loses the code it translates (hub#1763).
        Err(e) => (
            cloud_proxy::CLOUD_FAILED,
            Json(json!({ "ok": false, "error": cloud_proxy::cloud_unreachable(&e.to_string()) })),
        )
            .into_response(),
    }
}

pub(crate) async fn assistant_chat_stream(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(frontend): Json<Value>,
) -> Response {
    // Credencial hub-scoped: token de máquina del hub si está enrolado; si no, el JWT del usuario.
    // Así un cajero solo-local (sesión por PIN, sin JWT cloud) también usa el asistente.
    let Some(auth) = auth::hub_scoped_auth(&headers, &st) else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": "hub sin credencial (ni token de máquina ni Authorization: Bearer)" })),
        )
            .into_response();
    };
    // La sesión LOCAL del hub da el contexto/permisos para ensamblar las tools (gate = el de la UI)
    // y el id del usuario activo, que se manda como metadata de coste/auditoría (no permisos).
    let (all_tools, active_user, active_modules, instructions) = {
        let rt = st.runtime.read().await;
        let ctx = match auth::authenticate(&headers, &st.config, &rt).await {
            Ok(c) => c,
            Err(e) => return unauthorized(e),
        };
        let tools = assistant::assemble_tools(rt.registry(), &ctx);
        let active = rt.registry().active_module_count();
        // El system prompt del turno (§9.2). Se arma con el MISMO lock que las tools: el mapa de
        // módulos que describe y el catálogo que ofrece tienen que ser la misma foto del registry.
        // Absorbe además los `system` del cliente (el briefing de `hub.setup.status`, ADR-0230),
        // que el Cloud descarta en su frontera — `instructions` es el único canal que sobrevive.
        // La fecha/hora ACTUAL viaja en cada turno: el reloj del modelo se congeló al entrenar,
        // y en un ERP «hoy» es estructural (ventas de hoy, trimestre, vencimientos).
        let now = chrono::Utc::now();
        let instructions = assistant::build_instructions(
            rt.registry(),
            &assistant::client_system_messages(&frontend),
            &format!(
                "{} ({})",
                now.format("%Y-%m-%dT%H:%M:%SZ"),
                now.format("%A")
            ),
        );
        (tools, ctx.user_id.clone(), active, instructions)
    };

    // Router de tools por vectores (§9.2b): embebe la última petición del usuario, busca en el
    // índice y recorta los tools a los módulos relevantes. Degrada a "todos los tools" si no hay
    // índice, si hay pocos módulos, o ante cualquier fallo del prefiltro (§9.5). El permiso lo
    // revalida igual el runtime: el router solo abarata el prompt, no es un gate.
    let tools = match &st.vector {
        Some(store) => {
            let query = assistant::last_user_message(&frontend);
            let embedder =
                embed::CloudEmbedder::new(st.http.clone(), &st.config.cloud_base_url, auth.clone());
            router::assemble_routed_tools(
                &embedder,
                store.as_ref(),
                &st.hub_id(),
                &query,
                all_tools,
                active_modules,
                router::RouterConfig::default(),
            )
            .await
        }
        None => all_tools,
    };

    // Lo que el catálogo YA resolvió sobre cada tool, para anotar los eventos `function_call`
    // que reenviamos. El drawer no tiene catálogo propio donde consultarlo, y ninguna de estas
    // tres cosas puede venir del modelo — son hechos del manifest:
    //
    //   · `kind`         — el web app auto-ejecuta las LECTURAS y confirma las ESCRITURAS (§9.2).
    //   · `risk`         — cuánto daño hace la operación (hub#1042).
    //   · `money_fields` — qué argumentos son dinero, para que la tarjeta enseñe «15,00 €» y no
    //                      `price_cents: 1500` (hub#1040): el único punto donde un humano puede
    //                      cazar un ×100, y el único del producto donde no salía en euros.
    let tool_notes = assistant::tool_notes(&tools);

    let body = assistant::build_cloud_body(&frontend, tools, Some(&active_user), &instructions);

    // Construye la petición al Cloud (POST, Bearer + X-Hub-Id) y abre el stream.
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    let req = cloud.assistant_chat_stream(&auth);
    // The stream outlives the shared client's ceiling (hub#2509): it asks for the transfer one.
    let mut r = st.http.post(&req.url).json(&body).timeout(crate::state::CLOUD_TRANSFER_TIMEOUT);
    for (k, v) in &req.headers {
        r = r.header(*k, v);
    }

    let upstream = match r.send().await.and_then(|resp| resp.error_for_status()) {
        Ok(resp) => resp,
        Err(e) => {
            // Devuelve un único frame de error en el propio stream SSE. `error` viaja como CÓDIGO
            // estable, no como la prosa de `reqwest`: esa nombra la dirección del plano de control
            // (hub#1689) y el drawer la trata como el motivo del fallo.
            let code = cloud_proxy::cloud_unreachable(&e.to_string());
            let frame = assistant::sse(&json!({ "type": "error", "error": code, "code": code }));
            return sse_response(Body::from(frame));
        }
    };

    // Re-streamea: parte el cuerpo del Cloud en líneas SSE y las traduce al contrato frontend.
    // Un buffer mantiene líneas partidas entre chunks de red.
    let mut buf = String::new();
    let mut byte_stream = upstream.bytes_stream();
    // Set once the cut has been reported: past the transfer limit every read fails the same way,
    // and polling on would send the browser an endless run of error frames (hub#2509).
    let mut cut = false;

    let translated = futures_util::stream::poll_fn(move |cx| {
        use std::task::Poll;
        if cut {
            return Poll::Ready(None);
        }
        loop {
            // Vacía líneas completas ya bufferizadas.
            if let Some(idx) = buf.find('\n') {
                let line: String = buf.drain(..=idx).collect();
                let line = line.trim_end_matches(['\r', '\n']);
                if let Some(frame) = assistant::translate_sse_line(line, &tool_notes) {
                    return Poll::Ready(Some(Ok::<_, std::io::Error>(bytes_from(frame))));
                }
                continue;
            }
            // Pide más bytes al Cloud.
            match byte_stream.poll_next_unpin(cx) {
                Poll::Ready(Some(Ok(chunk))) => {
                    buf.push_str(&String::from_utf8_lossy(&chunk));
                }
                Poll::Ready(Some(Err(e))) => {
                    // The stream was cut halfway: same code as when it does not open (hub#1689),
                    // sent once, and then the stream ends.
                    cut = true;
                    let code = cloud_proxy::cloud_unreachable(&e.to_string());
                    let frame =
                        assistant::sse(&json!({ "type": "error", "error": code, "code": code }));
                    return Poll::Ready(Some(Ok(bytes_from(frame))));
                }
                Poll::Ready(None) => {
                    // Fin del stream del Cloud: procesa cualquier resto + cierra.
                    if !buf.is_empty() {
                        let rest = std::mem::take(&mut buf);
                        if let Some(frame) = assistant::translate_sse_line(rest.trim(), &tool_notes)
                        {
                            return Poll::Ready(Some(Ok(bytes_from(frame))));
                        }
                    }
                    return Poll::Ready(None);
                }
                Poll::Pending => return Poll::Pending,
            }
        }
    });

    sse_response(Body::from_stream(translated))
}

pub(crate) fn bytes_from(s: String) -> axum::body::Bytes {
    axum::body::Bytes::from(s.into_bytes())
}

/// Envuelve un cuerpo como respuesta SSE (`text/event-stream`, sin buffering del proxy).
pub(crate) fn sse_response(body: Body) -> Response {
    Response::builder()
        .header(header::CONTENT_TYPE, "text/event-stream")
        .header(header::CACHE_CONTROL, "no-cache")
        .header("X-Accel-Buffering", "no")
        .body(body)
        .unwrap()
        .into_response()
}
