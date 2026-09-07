//! «Connect WhatsApp» from the hub (hub#1600, ADR-0452) — the runtime's doors to the SaaS.
//!
//! The owner connects the WhatsApp number of the business in the WhatsApp module's settings: the
//! shell (`<erp-whatsapp-connect>`) loads Meta's SDK, opens the Embedded Signup popup (the QR is
//! scanned with the WhatsApp Business app on the phone) and, when it closes, hands the runtime
//! the `code` plus the ids Meta reported. The runtime is the one that talks to the SaaS, with the
//! hub's **machine credential**: the SaaS is where the Meta token ends up (ADR-0012), and a
//! cashier signed in by PIN has no cloud JWT to lend. Who is at the till is this side's job —
//! **owner/admin session**, the same gate as the rest of the hub's management.
//!
//! Four doors, all passthrough: the SaaS's status and JSON come back untouched, so «no phone
//! number» stays the 404 the page can name, and a SaaS that does not answer is a 502, never a
//! silent ok.
use crate::*;

fn gate(e: auth::AuthError) -> Response {
    let status = match e {
        auth::AuthError::Forbidden(_) => StatusCode::FORBIDDEN,
        _ => StatusCode::UNAUTHORIZED,
    };
    (status, Json(json!({ "ok": false, "error": e.message() }))).into_response()
}

async fn require_owner(st: &AppState, headers: &HeaderMap) -> Result<(), Response> {
    let rt = st.runtime.read().await;
    auth::require_admin_session(headers, &st.config, &rt)
        .await
        .map(|_| ())
        .map_err(gate)
}

/// A Meta phone_number_id is a number. Anything else must not reach a Cloud path (hub#1134).
pub(crate) fn phone_number_id_is_safe(id: &str) -> bool {
    !id.is_empty() && id.len() <= 32 && id.chars().all(|c| c.is_ascii_digit())
}

/// Hub-scoped POST to the Cloud with the machine credential, JSON in, JSON out untouched.
async fn cloud_post_json(
    st: &AppState,
    headers: &HeaderMap,
    req: cloud_client::PreparedRequest,
    body: &Value,
) -> Response {
    let Some(auth) = auth::hub_scoped_auth(headers, st) else {
        return cloud_proxy::cloud_get_error_response(cloud_proxy::CloudGetError::NoCredential);
    };
    let mut r = st.http.post(&req.url).json(body);
    // The credential is materialised for THIS destination only (hub#1464), never copied around.
    for (k, v) in
        cloud_client::CloudClient::new(&st.config.cloud_base_url).headers_for(&req.url, &auth)
    {
        r = r.header(k, v);
    }
    if let Some(language) = headers.get(axum::http::header::ACCEPT_LANGUAGE) {
        r = r.header(axum::http::header::ACCEPT_LANGUAGE, language);
    }
    let resp = match r.send().await {
        Ok(resp) => resp,
        Err(e) => {
            return cloud_proxy::cloud_get_error_response(cloud_proxy::CloudGetError::Network(
                e.to_string(),
            ))
        }
    };
    let status = StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
    match resp.bytes().await {
        Ok(bytes) => cloud_proxy::cloud_json_passthrough(status, bytes),
        Err(e) => cloud_proxy::cloud_get_error_response(cloud_proxy::CloudGetError::Network(
            e.to_string(),
        )),
    }
}

fn placeholder(st: &AppState) -> cloud_client::Auth {
    // The real credential is chosen by `hub_scoped_auth` at send time; this only builds the URL.
    cloud_client::Auth::HubToken {
        hub_id: st.hub_id(),
        token: String::new(),
    }
}

/// `GET /api/hub/whatsapp/config` → what the page needs to open the popup: app id, Embedded
/// Signup configuration id and Graph version. Public ids; `configured:false` hides the button.
pub(crate) async fn whatsapp_config(State(st): State<AppState>, headers: HeaderMap) -> Response {
    if let Err(r) = require_owner(&st, &headers).await {
        return r;
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    cloud_proxy::proxy_cloud_get(&st, &headers, cloud.whatsapp_config(&placeholder(&st))).await
}

/// `GET /api/hub/whatsapp/numbers` → the numbers connected to this hub.
pub(crate) async fn whatsapp_numbers(State(st): State<AppState>, headers: HeaderMap) -> Response {
    if let Err(r) = require_owner(&st, &headers).await {
        return r;
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    cloud_proxy::proxy_cloud_get(&st, &headers, cloud.whatsapp_numbers(&placeholder(&st))).await
}

/// `POST /api/hub/whatsapp/connect` → the popup's result (`{code, event, waba_id,
/// phone_number_id, business_id}`), verbatim, to the SaaS that exchanges it.
pub(crate) async fn whatsapp_connect(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(body): Json<Value>,
) -> Response {
    if let Err(r) = require_owner(&st, &headers).await {
        return r;
    }
    if !body.is_object() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({ "ok": false, "error": { "code": "whatsapp.invalid_body", "message": "expected a JSON object" } })),
        )
            .into_response();
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    cloud_post_json(
        &st,
        &headers,
        cloud.whatsapp_connect(&placeholder(&st)),
        &body,
    )
    .await
}

/// `POST /api/hub/whatsapp/disconnect/:phone_number_id` → stop routing that number here.
pub(crate) async fn whatsapp_disconnect(
    State(st): State<AppState>,
    Path(phone_number_id): Path<String>,
    headers: HeaderMap,
) -> Response {
    if let Err(r) = require_owner(&st, &headers).await {
        return r;
    }
    if !phone_number_id_is_safe(&phone_number_id) {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({ "ok": false, "error": { "code": "whatsapp.invalid_phone_number_id", "message": "invalid phone_number_id" } })),
        )
            .into_response();
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    cloud_post_json(
        &st,
        &headers,
        cloud.whatsapp_disconnect(&placeholder(&st), &phone_number_id),
        &json!({}),
    )
    .await
}

#[cfg(test)]
mod tests {
    use super::phone_number_id_is_safe;

    #[test]
    fn a_meta_phone_number_id_is_digits_and_nothing_else() {
        assert!(phone_number_id_is_safe("1122349777617204"));
        for hostile in [
            "",
            "../notify/whatsapp",
            "123/",
            "12 34",
            "1234567890123456789012345678901234",
        ] {
            assert!(!phone_number_id_is_safe(hostile), "{hostile:?} passed");
        }
    }
}
