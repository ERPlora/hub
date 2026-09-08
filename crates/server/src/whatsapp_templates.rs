//! The business's WhatsApp **templates**, hub → SaaS → Meta (hub#1610) — the hub half of saas#1899.
//!
//! The owner writes a template in the WhatsApp module's «Plantillas» tab. For a message to leave
//! the business outside the 24 h since the customer last wrote, Meta has to have approved that
//! template first, and who talks to Meta is the SaaS (ADR-0012: the Meta token never leaves it).
//! The module cannot call that door itself — it opens with the hub's **machine credential**, a
//! secret of the runtime that never reaches the browser (ADR-0003) — so the runtime proxies it.
//!
//! Three doors, same gate as the four of [`crate::whatsapp_connect`]: **owner/admin session**,
//! because what the business promises Meta is management, not the shift. And the same passthrough
//! rule: status and body come back untouched. That matters more here than anywhere else in this
//! file's neighbourhood — the SaaS answers refusals as a `code` (`invalid_name`, `missing_example`,
//! `meta_rate_limited`…, saas#1902/#1905) and it is the MODULE that turns each one into a sentence
//! with its `en` + `es` strings (ADR-0055). A code translated to prose here is a code the tab can
//! no longer act on.
use crate::*;

/// A Meta template name, as the SaaS defines it (`NAME_RE = ^[a-z0-9_]{1,512}$` in
/// `apps/whatsapp_inbox/services/templates.py`). Only the DELETE needs this: the name travels
/// inside a Cloud path there, and anything else must not reach it (same rule as
/// `phone_number_id_is_safe`, hub#1134). Meta itself accepts nothing wider, so a name this
/// refuses could not name a template that exists.
pub(crate) fn template_name_is_safe(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 512
        && name
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
}

fn refused(code: &str, message: &str) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({ "ok": false, "error": { "code": code, "message": message } })),
    )
        .into_response()
}

/// `GET /api/hub/whatsapp/templates` → this hub's templates with the verdict Meta gave each one,
/// plus `stale` when the SaaS could not reach Meta and is answering with what it had stored.
///
/// Read when the tab OPENS, never on a timer: the SaaS refreshes against Meta on every call and
/// that path carries no throttle of its own (reviewer of saas#1905).
pub(crate) async fn whatsapp_templates(State(st): State<AppState>, headers: HeaderMap) -> Response {
    if let Err(r) = whatsapp_connect::require_owner(&st, &headers).await {
        return r;
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    cloud_proxy::proxy_cloud_get(
        &st,
        &headers,
        cloud.whatsapp_templates(&whatsapp_connect::placeholder(&st)),
    )
    .await
}

/// `POST /api/hub/whatsapp/templates` → the template the business wrote, verbatim, to the SaaS
/// that registers it with Meta. `201` new, `200` edited in place; both go back to `PENDING`.
///
/// The body is NOT validated here beyond being an object: every rule (name, category, numbered
/// placeholders, one example per placeholder) lives in the SaaS, which is the half that knows what
/// Meta will accept. Copying those rules into the runtime would mean two places to keep in step
/// and a hub that refuses templates Meta would have taken.
pub(crate) async fn whatsapp_template_register(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(body): Json<Value>,
) -> Response {
    if let Err(r) = whatsapp_connect::require_owner(&st, &headers).await {
        return r;
    }
    if !body.is_object() {
        return refused("whatsapp.invalid_body", "expected a JSON object");
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    cloud_proxy::proxy_cloud_send(
        &st,
        &headers,
        cloud.whatsapp_template_register(&whatsapp_connect::placeholder(&st)),
        Some(&body),
    )
    .await
}

/// `DELETE /api/hub/whatsapp/templates/:name` → drop it from Meta and from the SaaS, every
/// language of it. A name outside [`template_name_is_safe`] is refused HERE, before any call: it
/// ends up inside a Cloud path and a `/` in it would steer the delete at another endpoint.
pub(crate) async fn whatsapp_template_delete(
    State(st): State<AppState>,
    Path(name): Path<String>,
    headers: HeaderMap,
) -> Response {
    if let Err(r) = whatsapp_connect::require_owner(&st, &headers).await {
        return r;
    }
    if !template_name_is_safe(&name) {
        return refused(
            "whatsapp.invalid_template_name",
            "lowercase letters, digits and underscores only",
        );
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    cloud_proxy::proxy_cloud_send(
        &st,
        &headers,
        cloud.whatsapp_template_delete(&whatsapp_connect::placeholder(&st), &name),
        None,
    )
    .await
}

#[cfg(test)]
mod tests {
    use super::template_name_is_safe;

    #[test]
    fn a_meta_template_name_is_lowercase_digits_and_underscores() {
        for good in [
            "table_ready",
            "cita_confirmada_es",
            "a",
            "b1",
            "_x",
            &"a".repeat(512),
        ] {
            assert!(template_name_is_safe(good), "{good:?} was refused");
        }
        for hostile in [
            "",
            "../notify/whatsapp",
            "table ready",
            "Table_Ready",
            "table-ready",
            "table.ready",
            "table/ready",
            "plantilla_señal",
            &"a".repeat(513),
        ] {
            assert!(!template_name_is_safe(hostile), "{hostile:?} passed");
        }
    }
}
