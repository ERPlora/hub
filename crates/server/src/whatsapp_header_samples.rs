//! A WhatsApp template's **header sample**, hub → SaaS → Meta (hub#2232) — the hub half of
//! saas#2377.
//!
//! Meta registers a template whose header is a photo, a video or a PDF only with an example of
//! that file already uploaded to it, named by a `header_handle`. The upload is made with the
//! business's Meta token, which only the SaaS holds (ADR-0012), and the SaaS door opens with the
//! hub's **machine credential**, a secret of the runtime that never reaches the browser
//! (ADR-0003). So the module's «Plantillas» tab hands the file to the runtime and the runtime
//! relays it.
//!
//! **Relayed, not read.** The browser's multipart form goes to the SaaS as it came — boundary,
//! bytes and length — in streaming: a PDF sample can weigh 100 MB, and a hub holding it whole in
//! memory for every upload is a hub that runs out of it. Nothing about the file is decided here:
//! what kind it is and how big each kind may be is the SaaS's call (it sniffs the bytes), because
//! it is the half that knows what Meta takes. The only line the runtime holds is the one it can
//! hold without reading the body: the declared length, against the largest sample Meta takes.
//!
//! Same gate as registering the template the sample belongs to
//! ([`whatsapp_templates::require_owner_and_notify`]), and the SaaS's answer travels in the
//! runtime's envelope with its own `code`, `5xx` included ([`cloud_proxy::cloud_envelope_named_refusal`]).
use crate::*;

/// The largest sample Meta takes is a 100 MB PDF (saas#2377, `MB = 1024 * 1024`); the form around
/// it adds a boundary and a couple of part headers. One MiB of slack covers that framing with room
/// to spare while still refusing, from its declared length alone, a body no sample could fill.
pub(crate) const MAX_UPLOAD_BYTES: u64 = 100 * 1024 * 1024 + 1024 * 1024;

/// The code both halves answer for a sample that is too big: the SaaS says it too, so the tab reads
/// ONE word whichever side refused.
const TOO_LARGE: &str = "header_sample_too_large";

/// Whether a form of `declared` bytes may be relayed at all.
pub(crate) fn declared_length_fits(declared: u64) -> bool {
    declared <= MAX_UPLOAD_BYTES
}

/// `multipart/form-data` WITH its boundary: without the boundary the SaaS cannot find the `file`
/// field, so the form would travel 100 MB only to be refused.
pub(crate) fn is_multipart_form(content_type: &str) -> bool {
    let mut parts = content_type.split(';');
    let essence = parts.next().unwrap_or_default().trim();
    essence.eq_ignore_ascii_case("multipart/form-data")
        && parts.any(|p| {
            p.trim()
                .split_once('=')
                .is_some_and(|(k, v)| k.trim().eq_ignore_ascii_case("boundary") && !v.is_empty())
        })
}

fn refused(status: StatusCode, code: &str, message: &str) -> Response {
    (
        status,
        Json(json!({ "ok": false, "error": { "code": code, "message": message } })),
    )
        .into_response()
}

/// `POST /api/hub/whatsapp/template-header-samples` (multipart field `file`) →
/// `201 {header_handle, format, mime_type, size}` in the envelope. The tab keeps `header_handle`
/// and sends it, with `header_format`, when it registers the template.
pub(crate) async fn whatsapp_template_header_sample(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Body,
) -> Response {
    if let Err(r) = whatsapp_templates::require_owner_and_notify(&st, &headers).await {
        return r;
    }
    let Some(content_type) = headers
        .get(header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .filter(|ct| is_multipart_form(ct))
        .map(str::to_owned)
    else {
        return refused(
            StatusCode::BAD_REQUEST,
            "whatsapp.invalid_header_sample_upload",
            "expected a multipart/form-data body with the sample in its `file` field",
        );
    };
    let Some(declared) = headers
        .get(header::CONTENT_LENGTH)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.trim().parse::<u64>().ok())
    else {
        return refused(
            StatusCode::LENGTH_REQUIRED,
            "whatsapp.header_sample_length_required",
            "the upload must declare its Content-Length",
        );
    };
    if !declared_length_fits(declared) {
        return refused(
            StatusCode::PAYLOAD_TOO_LARGE,
            TOO_LARGE,
            "no header sample Meta takes is this big",
        );
    }
    let Some(auth) = auth::hub_scoped_auth(&headers, &st) else {
        return cloud_proxy::cloud_envelope_error_response(
            cloud_proxy::CloudGetError::NoCredential,
        );
    };
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    let req = cloud.whatsapp_template_header_sample(&auth);
    let mut call = st
        .http
        .post(&req.url)
        .header(header::CONTENT_TYPE, content_type)
        // Declared, so the body leaves with its length and not chunked: the SaaS and the edge in
        // front of it know up front how much is coming.
        .header(header::CONTENT_LENGTH, declared)
        .body(reqwest::Body::wrap_stream(body.into_data_stream()))
        .timeout(crate::state::CLOUD_TRANSFER_TIMEOUT);
    for (k, v) in cloud.headers_for(&req.url, &auth) {
        call = call.header(k, v);
    }
    if let Some(language) = headers.get(header::ACCEPT_LANGUAGE) {
        call = call.header(header::ACCEPT_LANGUAGE, language);
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
    match upstream.bytes().await {
        Ok(answer) => cloud_proxy::cloud_envelope_named_refusal(status, answer),
        Err(e) => cloud_proxy::cloud_envelope_error_response(cloud_proxy::CloudGetError::Network(
            e.to_string(),
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::{declared_length_fits, is_multipart_form, MAX_UPLOAD_BYTES};

    #[test]
    fn the_largest_sample_meta_takes_fits_with_its_framing_and_nothing_bigger() {
        let largest_pdf = 100 * 1024 * 1024;
        assert!(declared_length_fits(largest_pdf));
        assert!(declared_length_fits(largest_pdf + 1024 * 1024));
        assert!(declared_length_fits(MAX_UPLOAD_BYTES));
        assert!(!declared_length_fits(MAX_UPLOAD_BYTES + 1));
        assert!(!declared_length_fits(u64::MAX));
    }

    #[test]
    fn only_a_form_with_its_boundary_is_relayed() {
        for good in [
            "multipart/form-data; boundary=----WebKitFormBoundaryx",
            "Multipart/Form-Data;boundary=abc",
            "multipart/form-data; charset=utf-8; boundary=\"abc\"",
        ] {
            assert!(is_multipart_form(good), "{good:?} was refused");
        }
        for bad in [
            "",
            "multipart/form-data",
            "multipart/form-data; boundary=",
            "multipart/mixed; boundary=abc",
            "application/json",
            "image/jpeg; boundary=abc",
            "multipart/form-data-x; boundary=abc",
        ] {
            assert!(!is_multipart_form(bad), "{bad:?} passed");
        }
    }
}
