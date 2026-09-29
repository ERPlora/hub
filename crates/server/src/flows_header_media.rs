//! **The photo of a WhatsApp header, uploaded from a flow step** (hub#2335).
//!
//! `POST /api/hub/flows/whatsapp-header-images` (multipart, one field `file`) →
//! `201 {"ok": true, "data": {"ref", "mime_type", "size"}}`.
//!
//! A template approved with a photo header sends a photo every time, and Meta takes it as a link it
//! downloads itself. The owner of a salon has no public link to her salon's picture — she has the
//! file. So the step's editor hands the file here, the runtime stores it in the hub's own `media/`
//! under [`HEADER_MEDIA_FOLDER`], and the step keeps the reference it gets back; every send asks
//! erplora.com for a freshly signed link to it (`notify_transport.rs`), so the link never expires
//! in the queue and the file never has to be public.
//!
//! **Read and vetted here, not relayed.** Unlike a template's header SAMPLE (hub#2232, up to a
//! 100 MB PDF, streamed to the SaaS untouched) this file is small and it is ours to keep, so the
//! runtime decides what it is: a JPEG or a PNG **by its bytes**, never by its name or the type the
//! browser declared, and at most [`MAX_IMAGE_BYTES`] — Meta's own cap for a header image. Anything
//! else would be stored only to fail at every send. And the runtime names it: the SHA-256 of its
//! bytes, so what she called it never reaches a path, and the same photo saved twice is one file.
//!
//! Same door as the rest of the flows (`flows_api::admin_session!`): a human owner/admin session,
//! and — when a module is the caller — the module the owner granted `manage_flows`.
use axum::extract::multipart::MultipartRejection;
use axum::extract::{DefaultBodyLimit, Multipart, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::json;
use sha2::{Digest, Sha256};

use crate::notify_transport::HEADER_MEDIA_FOLDER;
use crate::{auth, AppState};

/// Meta's cap for a WhatsApp header image: 5 MB (`1024 * 1024`).
pub(crate) const MAX_IMAGE_BYTES: usize = 5 * 1024 * 1024;

/// The body limit of the route: the largest image plus the form around it (a boundary and a couple
/// of part headers). A body bigger than this is refused by axum while it is being read, and the
/// handler still answers it with its own code ([`TOO_LARGE`]).
pub(crate) fn body_limit() -> DefaultBodyLimit {
    DefaultBodyLimit::max(MAX_IMAGE_BYTES + 64 * 1024)
}

const MISSING: &str = "whatsapp.header_image_missing";
const UNSUPPORTED: &str = "whatsapp.header_image_unsupported";
const TOO_LARGE: &str = "whatsapp.header_image_too_large";
const NOT_SAVED: &str = "whatsapp.header_image_not_saved";
const NOT_A_FORM: &str = "whatsapp.invalid_header_image_upload";

/// The two kinds Meta takes as a header image, told apart by their first bytes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum HeaderImage {
    Jpeg,
    Png,
}

impl HeaderImage {
    /// What the bytes ARE: a JPEG starts `FF D8 FF`, a PNG with its eight-byte signature. A name or
    /// a declared type says nothing — a PDF renamed `.jpg` is still a PDF, and Meta refuses it.
    pub(crate) fn sniff(bytes: &[u8]) -> Option<Self> {
        if bytes.starts_with(&[0xFF, 0xD8, 0xFF]) {
            Some(Self::Jpeg)
        } else if bytes.starts_with(b"\x89PNG\r\n\x1a\n") {
            Some(Self::Png)
        } else {
            None
        }
    }

    fn extension(self) -> &'static str {
        match self {
            Self::Jpeg => "jpg",
            Self::Png => "png",
        }
    }

    fn mime_type(self) -> &'static str {
        match self {
            Self::Jpeg => "image/jpeg",
            Self::Png => "image/png",
        }
    }
}

/// The name the file is stored under: the SHA-256 of its bytes and the extension of its kind.
pub(crate) fn stored_name(bytes: &[u8], kind: HeaderImage) -> String {
    let digest = Sha256::digest(bytes);
    let hex: String = digest.iter().map(|b| format!("{b:02x}")).collect();
    format!("{hex}.{}", kind.extension())
}

fn refusal(status: StatusCode, code: &str, message: &str) -> Response {
    (
        status,
        Json(json!({ "ok": false, "error": { "code": code, "message": message } })),
    )
        .into_response()
}

fn too_large() -> Response {
    refusal(
        StatusCode::PAYLOAD_TOO_LARGE,
        TOO_LARGE,
        "a WhatsApp header image can weigh 5 MB at most",
    )
}

fn not_a_form() -> Response {
    refusal(
        StatusCode::BAD_REQUEST,
        NOT_A_FORM,
        "send the photo as a multipart form with its boundary, in the field `file`",
    )
}

/// The photo in the form's `file` field, read up to one byte past the cap — enough to know it does
/// not fit without holding more of it.
enum Read {
    Photo(Vec<u8>),
    Missing,
    TooLarge,
    Broken,
}

async fn read_photo(mut form: Multipart) -> Read {
    loop {
        let mut field = match form.next_field().await {
            Ok(Some(field)) => field,
            Ok(None) => return Read::Missing,
            Err(e) if e.status() == StatusCode::PAYLOAD_TOO_LARGE => return Read::TooLarge,
            Err(_) => return Read::Broken,
        };
        if field.name() != Some("file") {
            continue;
        }
        let mut bytes = Vec::new();
        loop {
            match field.chunk().await {
                Ok(Some(chunk)) => {
                    if bytes.len() + chunk.len() > MAX_IMAGE_BYTES {
                        return Read::TooLarge;
                    }
                    bytes.extend_from_slice(&chunk);
                }
                Ok(None) => return Read::Photo(bytes),
                Err(e) if e.status() == StatusCode::PAYLOAD_TOO_LARGE => return Read::TooLarge,
                Err(_) => return Read::Broken,
            }
        }
    }
}

/// `POST /api/hub/flows/whatsapp-header-images`.
pub async fn upload_whatsapp_header_image(
    State(st): State<AppState>,
    headers: HeaderMap,
    // Taken as a `Result`: a body that is not a form must still meet the gate first, and then be
    // refused in the envelope the SDK reads — not with axum's plain-text rejection.
    form: Result<Multipart, MultipartRejection>,
) -> Response {
    // The gate before a byte of the body is read: a refused caller never gets to make the hub
    // hold 5 MB.
    {
        let arc = match st.runtime_for(&st.hub_id()).await {
            Ok(arc) => arc,
            Err(e) => return crate::tenant_rejected(e),
        };
        let rt = arc.read().await;
        if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
            return crate::auth_rejected(e);
        }
        if let Err(response) = crate::flows_api::require_flows_capability(&headers, &rt).await {
            return response;
        }
    }

    let Ok(form) = form else {
        return not_a_form();
    };
    let bytes = match read_photo(form).await {
        Read::Photo(bytes) => bytes,
        Read::Missing => {
            return refusal(
                StatusCode::BAD_REQUEST,
                MISSING,
                "the form carries no `file` field",
            )
        }
        Read::TooLarge => return too_large(),
        Read::Broken => return not_a_form(),
    };
    let Some(kind) = HeaderImage::sniff(&bytes) else {
        return refusal(
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            UNSUPPORTED,
            "a WhatsApp header image must be a JPEG or a PNG",
        );
    };
    let name = stored_name(&bytes, kind);
    if !crate::media::store_vetted_file(&st, HEADER_MEDIA_FOLDER, &name, &bytes).await {
        tracing::warn!(file = %name, "flows: the WhatsApp header photo could not be stored");
        return refusal(
            StatusCode::BAD_GATEWAY,
            NOT_SAVED,
            "erplora.com could not store the photo",
        );
    }
    (
        StatusCode::CREATED,
        Json(json!({
            "ok": true,
            "data": {
                "ref": format!("{HEADER_MEDIA_FOLDER}/{name}"),
                "mime_type": kind.mime_type(),
                "size": bytes.len(),
            }
        })),
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::notify_transport::header_media_file;

    #[test]
    fn a_photo_is_told_by_its_bytes_not_its_name() {
        assert_eq!(
            HeaderImage::sniff(b"\xff\xd8\xff\xe0JFIF"),
            Some(HeaderImage::Jpeg)
        );
        assert_eq!(
            HeaderImage::sniff(b"\x89PNG\r\n\x1a\n\0\0"),
            Some(HeaderImage::Png)
        );
        for other in [
            b"".as_slice(),
            b"\xff\xd8",
            b"\x89PNG\r\n\x1a",
            b"%PDF-1.7",
            b"GIF89a",
            b"RIFF\0\0\0\0WEBP",
        ] {
            assert_eq!(HeaderImage::sniff(other), None, "{other:?}");
        }
    }

    /// The name is the photo's fingerprint: one photo, one file; and it is a reference the send
    /// accepts — the two halves of hub#2335 agree on what a stored header looks like.
    #[test]
    fn the_stored_name_is_the_fingerprint_and_the_send_accepts_it() {
        let a = stored_name(b"\xff\xd8\xffone", HeaderImage::Jpeg);
        assert_eq!(a, stored_name(b"\xff\xd8\xffone", HeaderImage::Jpeg));
        assert_ne!(a, stored_name(b"\xff\xd8\xfftwo", HeaderImage::Jpeg));
        assert!(a.ends_with(".jpg") && a.len() == 64 + 4, "{a}");
        assert!(stored_name(b"x", HeaderImage::Png).ends_with(".png"));
        let reference = format!("{HEADER_MEDIA_FOLDER}/{a}");
        assert_eq!(header_media_file(&reference), Some(reference.as_str()));
    }
}
