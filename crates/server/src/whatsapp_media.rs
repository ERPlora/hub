//! A WhatsApp **attachment**, hub → SaaS → Meta (hub#2114) — the hub half of saas#2285.
//!
//! A customer sends a photo, a voice note, a video or a document. Meta hands the business an asset
//! id, never the file, and the only party that can swap that id for the bytes is the SaaS, which
//! holds the business's Meta token (ADR-0012). The inbox module cannot call the SaaS itself — that
//! door opens with the hub's **machine credential**, a secret of the runtime that never reaches
//! the browser (ADR-0003) — so the runtime proxies it, read-only, exactly like the templates door
//! next to it ([`crate::whatsapp_templates`]).
//!
//! **Bytes out, in streaming.** A document can weigh 100 MB; the body goes through as it arrives,
//! never gathered in the runtime first. That makes this the one module-reachable WhatsApp door that
//! does NOT answer its success in the envelope: the SDK reads it as a `Blob`
//! (`WhatsappMediaApi.get`). Every REFUSAL still does, with its own `code`, because the inbox tells
//! «no longer available» (`media_not_found`) from «try again» (`media_unavailable`) from «reconnect
//! WhatsApp» (`meta_permission_denied`) — ADR-0055.
use crate::*;
use erplora_runtime::host_notify;
use erplora_runtime::manifest::CapabilityKind;

/// The permission that lets a person read the inbox's conversations. Seeing the photo a customer
/// sent IS reading the conversation, so a role the owner kept out of the inbox cannot pull its
/// attachments by id either. The name is the inbox module's own (its `module.json`); the kernel
/// already names that module where it serves it (`whatsapp_quota::QUOTA_COMMAND`).
pub(crate) const VIEW_CONVERSATION: &str = "whatsapp_inbox.view_conversation";

/// The code both halves answer for an id that is not Meta's: the SaaS says it too
/// (`invalid_media_id`, saas#2289), so the module reads ONE word whichever side refused.
const INVALID_MEDIA_ID: &str = "invalid_media_id";

/// A Meta media id is a number (`^\d{1,32}$`, the SaaS's own rule). Anything else must not reach
/// a Cloud path — same rule as `phone_number_id_is_safe` (hub#1134).
pub(crate) fn media_id_is_safe(id: &str) -> bool {
    !id.is_empty() && id.len() <= 32 && id.chars().all(|c| c.is_ascii_digit())
}

fn refused(status: StatusCode, code: &str, message: &str) -> Response {
    (
        status,
        Json(json!({ "ok": false, "error": { "code": code, "message": message } })),
    )
        .into_response()
}

/// The gate, three halves and all three default-deny:
///
/// 1. **A person** with a local session — any role, because the cashier who answers the inbox is
///    the one who needs to see the photo. An API key is not a person and does not pass.
/// 2. **Who may read the inbox**: [`VIEW_CONVERSATION`]. The inbox's own permission, the one its
///    list of conversations is already gated on.
/// 3. **The calling module**, when the request names one: `notify` declared and granted, AND the
///    `whatsapp` channel declared — the criterion of the templates door
///    ([`crate::whatsapp_templates`]), so a module the owner never pointed at WhatsApp cannot read
///    the business's customers' photos.
async fn require_inbox_reader(st: &AppState, headers: &HeaderMap) -> Result<(), Response> {
    let rt = st.runtime.read().await;
    let ctx = match auth::require_user_session(headers, &st.config, &rt).await {
        Ok(ctx) => ctx,
        Err(e) => {
            return Err(refused(
                StatusCode::UNAUTHORIZED,
                "unauthenticated",
                &e.message(),
            ))
        }
    };
    if !erplora_runtime::permissions::has(&ctx, VIEW_CONVERSATION) {
        return Err(crate::err_response(
            erplora_runtime::RuntimeError::PermissionDenied(VIEW_CONVERSATION.to_string()),
        ));
    }
    let module =
        crate::flows_api::require_module_capability(headers, &rt, CapabilityKind::Notify).await?;
    if let Some(module) = module {
        host_notify::assert_channel_declared(
            rt.registry(),
            &module,
            host_notify::Channel::Whatsapp,
        )
        .map_err(crate::err_response)?;
    }
    Ok(())
}

/// `GET /api/hub/whatsapp/media/:media_id` → the attachment's bytes, streamed, with the
/// `Content-Type` the SaaS gave (Meta's MIME, codec parameters included: `audio/ogg; codecs=opus`).
///
/// A customer's photo is personal data: `private, no-store` keeps it out of any shared cache,
/// `nosniff` keeps a browser from promoting a document to something it runs, and
/// `attachment` + `sandbox` make a direct navigation to this URL a download, never a page on the
/// hub's origin.
pub(crate) async fn whatsapp_media(
    State(st): State<AppState>,
    Path(media_id): Path<String>,
    headers: HeaderMap,
) -> Response {
    if let Err(r) = require_inbox_reader(&st, &headers).await {
        return r;
    }
    if !media_id_is_safe(&media_id) {
        return refused(
            StatusCode::BAD_REQUEST,
            INVALID_MEDIA_ID,
            "a WhatsApp media id is digits only",
        );
    }
    let Some(auth) = auth::hub_scoped_auth(&headers, &st) else {
        return cloud_proxy::cloud_envelope_error_response(
            cloud_proxy::CloudGetError::NoCredential,
        );
    };
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    let req = cloud.whatsapp_media(&auth, &media_id);
    let mut call = st.http.get(&req.url);
    for (k, v) in cloud.headers_for(&req.url, &auth) {
        call = call.header(k, v);
    }
    let upstream = match call.send().await {
        Ok(upstream) => upstream,
        Err(e) => {
            return cloud_proxy::cloud_envelope_error_response(cloud_proxy::CloudGetError::Network(
                e.to_string(),
            ))
        }
    };
    let status = cloud_proxy::cloud_status(upstream.status().as_u16());
    if !status.is_success() {
        let body = match upstream.bytes().await {
            Ok(body) => body,
            Err(e) => {
                return cloud_proxy::cloud_envelope_error_response(
                    cloud_proxy::CloudGetError::Network(e.to_string()),
                )
            }
        };
        return cloud_proxy::cloud_envelope_named_refusal(status, body);
    }

    let content_type = upstream
        .headers()
        .get(axum::http::header::CONTENT_TYPE)
        .cloned()
        .unwrap_or_else(|| HeaderValue::from_static("application/octet-stream"));
    let content_length = upstream
        .headers()
        .get(axum::http::header::CONTENT_LENGTH)
        .cloned();
    let mut response = Response::builder()
        .status(StatusCode::OK)
        .header(axum::http::header::CONTENT_TYPE, content_type)
        .header(axum::http::header::CACHE_CONTROL, "private, no-store")
        .header("x-content-type-options", "nosniff")
        .header(axum::http::header::CONTENT_DISPOSITION, "attachment")
        .header(axum::http::header::CONTENT_SECURITY_POLICY, "sandbox");
    if let Some(length) = content_length {
        response = response.header(axum::http::header::CONTENT_LENGTH, length);
    }
    match response.body(Body::from_stream(upstream.bytes_stream())) {
        Ok(response) => response,
        Err(e) => {
            tracing::warn!(error = %e, "the hub could not frame a WhatsApp attachment");
            refused(
                cloud_proxy::CLOUD_FAILED,
                cloud_proxy::CLOUD_UNREADABLE,
                "erplora.com answered with headers the hub could not relay",
            )
        }
    }
}

#[cfg(test)]
mod tests {
    use super::media_id_is_safe;

    #[test]
    fn a_meta_media_id_is_digits_only_up_to_32() {
        for good in ["1", "1234567890123456", &"9".repeat(32)] {
            assert!(media_id_is_safe(good), "{good:?} was refused");
        }
        for hostile in [
            "",
            "abc",
            "12a",
            "..",
            "../templates",
            "1/2",
            "1 2",
            "-1",
            "١٢٣",
            &"9".repeat(33),
        ] {
            assert!(!media_id_is_safe(hostile), "{hostile:?} passed");
        }
    }
}
