//! **The photo, video or PDF of a WhatsApp header, uploaded from a flow step** (hub#2335, hub#2347).
//!
//! `POST /api/hub/flows/whatsapp-header-images` (multipart: `kind` = `image` | `video` |
//! `document`, and the `file`) → `201 {"ok": true, "data": {"ref", "mime_type", "size"}}`. With no
//! `kind` the header is a photo — the form of hub#2335, which the editors of that release still
//! send.
//!
//! A template approved with a media header sends that media every time, and Meta takes it as a link
//! it downloads itself. The owner of a salon has no public link to her promotion's video or her
//! restaurant's menu — she has the file. So the step's editor hands the file here, the runtime
//! stores it in the hub's own `media/` under [`HEADER_MEDIA_FOLDER`], and the step keeps the
//! reference it gets back; every send asks erplora.com for a freshly signed link to it
//! (`notify_transport.rs`), so the link never expires in the queue and the file never has to be
//! public.
//!
//! **Vetted here, not relayed.** Unlike a template's header SAMPLE (hub#2232, streamed to the SaaS
//! untouched) this file is ours to keep, so the runtime decides what it is: a JPEG or a PNG, an MP4
//! or a PDF **by its bytes**, never by its name or the type the browser declared — and it must be
//! the kind its header asks for, at most Meta's own cap for it (5 MB, 16 MB, 100 MB). Anything else
//! would be stored only to fail at every send. And the runtime names it: the SHA-256 of its bytes
//! with the extension of what it is — the extension is what the send reads to know which header
//! the file can fill (`notify_transport::header_media_kind`), so what she called it never reaches
//! a path, and the same file saved twice is one file.
//!
//! **Streamed, never held whole**: a 100 MB PDF does not fit a hub that runs in 96 MiB, so the
//! file goes to a temporary file on disk while it is read and hashed, and from there to the store.
//!
//! Same door as the rest of the flows (`flows_api::admin_session!`): a human owner/admin session,
//! and — when a module is the caller — the module the owner granted `manage_flows`.
use std::io::Write;

use axum::extract::multipart::{Field, MultipartRejection};
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
/// Meta's cap for a WhatsApp header video: 16 MB.
pub(crate) const MAX_VIDEO_BYTES: usize = 16 * 1024 * 1024;
/// Meta's cap for a WhatsApp header document: 100 MB.
pub(crate) const MAX_DOCUMENT_BYTES: usize = 100 * 1024 * 1024;

/// The body limit of the route: the largest file (a document) plus the form around it (a boundary,
/// the `kind` and a couple of part headers). A body bigger than this is refused by axum while it is
/// being read, and the handler still answers it with the code of its kind (`…_too_large`).
pub(crate) fn body_limit() -> DefaultBodyLimit {
    DefaultBodyLimit::max(MAX_DOCUMENT_BYTES + 64 * 1024)
}

const KIND_UNKNOWN: &str = "whatsapp.header_media_kind_unknown";
const NOT_A_FORM: &str = "whatsapp.invalid_header_image_upload";

/// The header a file is uploaded for — the media kinds of a WhatsApp template header.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum HeaderKind {
    Image,
    Video,
    Document,
}

impl HeaderKind {
    /// The form's `kind`, exactly as the SDK writes it; anything else is not a header Meta takes a
    /// file for.
    pub(crate) fn parse(raw: &str) -> Option<Self> {
        match raw {
            "image" => Some(Self::Image),
            "video" => Some(Self::Video),
            "document" => Some(Self::Document),
            _ => None,
        }
    }

    fn name(self) -> &'static str {
        match self {
            Self::Image => "image",
            Self::Video => "video",
            Self::Document => "document",
        }
    }

    /// Meta's cap for a header of this kind.
    pub(crate) fn max_bytes(self) -> usize {
        match self {
            Self::Image => MAX_IMAGE_BYTES,
            Self::Video => MAX_VIDEO_BYTES,
            Self::Document => MAX_DOCUMENT_BYTES,
        }
    }

    /// `whatsapp.header_<kind>_<reason>` — for an image, the codes of hub#2335 unchanged.
    fn code(self, reason: &str) -> String {
        format!("whatsapp.header_{}_{reason}", self.name())
    }

    fn what(self) -> &'static str {
        match self {
            Self::Image => "a JPEG or a PNG",
            Self::Video => "an MP4",
            Self::Document => "a PDF",
        }
    }

    fn cap(self) -> &'static str {
        match self {
            Self::Image => "5 MB",
            Self::Video => "16 MB",
            Self::Document => "100 MB",
        }
    }
}

/// What a header file IS, told apart by its first bytes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum HeaderMedia {
    Jpeg,
    Png,
    Mp4,
    Pdf,
}

impl HeaderMedia {
    /// The bytes [`Self::sniff`] needs to decide (an MP4's brand ends at byte 12).
    const SNIFF_LEN: usize = 12;

    /// What the bytes ARE: a JPEG starts `FF D8 FF`, a PNG with its eight-byte signature, a PDF
    /// with `%PDF-`, an MP4 with an `ftyp` box whose brand is not QuickTime's (`qt  `) nor 3GPP's
    /// (`3g…`) — Meta plays neither as an MP4. A name or a declared type says nothing — a PDF renamed
    /// `.jpg` is still a PDF, and Meta refuses it.
    pub(crate) fn sniff(bytes: &[u8]) -> Option<Self> {
        if bytes.starts_with(&[0xFF, 0xD8, 0xFF]) {
            Some(Self::Jpeg)
        } else if bytes.starts_with(b"\x89PNG\r\n\x1a\n") {
            Some(Self::Png)
        } else if bytes.starts_with(b"%PDF-") {
            Some(Self::Pdf)
        } else if bytes.len() >= Self::SNIFF_LEN
            && &bytes[4..8] == b"ftyp"
            && !bytes[8..12].starts_with(b"qt")
            && !bytes[8..12].starts_with(b"3g")
        {
            Some(Self::Mp4)
        } else {
            None
        }
    }

    pub(crate) fn kind(self) -> HeaderKind {
        match self {
            Self::Jpeg | Self::Png => HeaderKind::Image,
            Self::Mp4 => HeaderKind::Video,
            Self::Pdf => HeaderKind::Document,
        }
    }

    fn extension(self) -> &'static str {
        match self {
            Self::Jpeg => "jpg",
            Self::Png => "png",
            Self::Mp4 => "mp4",
            Self::Pdf => "pdf",
        }
    }

    fn mime_type(self) -> &'static str {
        match self {
            Self::Jpeg => "image/jpeg",
            Self::Png => "image/png",
            Self::Mp4 => "video/mp4",
            Self::Pdf => "application/pdf",
        }
    }
}

/// The name a file is stored under: the hex SHA-256 of its bytes and the extension of what it is.
pub(crate) fn stored_name(digest_hex: &str, media: HeaderMedia) -> String {
    format!("{digest_hex}.{}", media.extension())
}

fn hex(digest: &[u8]) -> String {
    digest.iter().map(|b| format!("{b:02x}")).collect()
}

fn refusal(status: StatusCode, code: &str, message: &str) -> Response {
    (
        status,
        Json(json!({ "ok": false, "error": { "code": code, "message": message } })),
    )
        .into_response()
}

fn not_a_form() -> Response {
    refusal(
        StatusCode::BAD_REQUEST,
        NOT_A_FORM,
        "send the file as a multipart form with its boundary, in the field `file`",
    )
}

fn unsupported(kind: HeaderKind) -> Response {
    refusal(
        StatusCode::UNSUPPORTED_MEDIA_TYPE,
        &kind.code("unsupported"),
        &format!("a WhatsApp header {} must be {}", kind.name(), kind.what()),
    )
}

fn too_large(kind: HeaderKind) -> Response {
    refusal(
        StatusCode::PAYLOAD_TOO_LARGE,
        &kind.code("too_large"),
        &format!("a WhatsApp header {} can weigh {} at most", kind.name(), kind.cap()),
    )
}

/// The `file` field as it was read.
enum File {
    /// Its first bytes are none of the kinds a header takes; nothing of it was kept.
    Unrecognised,
    /// It is `media`, but longer than Meta's cap for its kind; nothing of it was kept.
    TooLarge(HeaderMedia),
    /// It is `media`, whole, in `tmp` (deleted when dropped, on every path).
    Kept {
        media: HeaderMedia,
        tmp: tempfile::NamedTempFile,
        size: usize,
        digest_hex: String,
    },
}

/// Why a form could not be read to the end.
enum Broken {
    /// Not a multipart body, or one cut short.
    Form,
    /// The body is bigger than the route takes: the file in it is too large for any header.
    TooLarge,
    /// The temporary file could not be written — the hub's disk, not her file.
    Disk,
}

fn broken(error: &axum::extract::multipart::MultipartError) -> Broken {
    if error.status() == StatusCode::PAYLOAD_TOO_LARGE {
        Broken::TooLarge
    } else {
        Broken::Form
    }
}

/// Reads the `file` field: its first bytes decide what it is — and, when the form already named
/// its `kind`, refuse a file of another kind before reading on — and the rest goes to a temporary
/// file while it is hashed, up to Meta's cap for what it is.
async fn read_file(
    mut field: Field<'_>,
    declared: Option<HeaderKind>,
) -> Result<File, Broken> {
    let mut head = Vec::with_capacity(HeaderMedia::SNIFF_LEN);
    let mut pending = Vec::new();
    let media = loop {
        match field.chunk().await.map_err(|e| broken(&e))? {
            Some(chunk) => {
                let wanted = HeaderMedia::SNIFF_LEN - head.len();
                let take = wanted.min(chunk.len());
                head.extend_from_slice(&chunk[..take]);
                if head.len() == HeaderMedia::SNIFF_LEN {
                    pending.extend_from_slice(&chunk[take..]);
                    break HeaderMedia::sniff(&head);
                }
            }
            None => break HeaderMedia::sniff(&head),
        }
    };
    let Some(media) = media else {
        return Ok(File::Unrecognised);
    };
    if declared.is_some_and(|kind| kind != media.kind()) {
        return Ok(File::Unrecognised);
    }
    let cap = media.kind().max_bytes();
    let mut tmp = tempfile::NamedTempFile::new().map_err(|_| Broken::Disk)?;
    let mut hasher = Sha256::new();
    let mut size = 0usize;
    let mut write = |bytes: &[u8]| -> Result<bool, Broken> {
        size += bytes.len();
        if size > cap {
            return Ok(false);
        }
        hasher.update(bytes);
        tmp.write_all(bytes).map_err(|_| Broken::Disk)?;
        Ok(true)
    };
    if !write(&head)? || !write(&pending)? {
        return Ok(File::TooLarge(media));
    }
    loop {
        match field.chunk().await {
            Ok(Some(chunk)) => {
                if !write(&chunk)? {
                    return Ok(File::TooLarge(media));
                }
            }
            Ok(None) => break,
            Err(e) => {
                return match broken(&e) {
                    Broken::TooLarge => Ok(File::TooLarge(media)),
                    other => Err(other),
                }
            }
        }
    }
    tmp.flush().map_err(|_| Broken::Disk)?;
    Ok(File::Kept {
        media,
        tmp,
        size,
        digest_hex: hex(&hasher.finalize()),
    })
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
    // hold or write anything.
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

    let Ok(mut form) = form else {
        return not_a_form();
    };
    // The whole form is read before deciding: the `kind` may come before the file or after it.
    let mut declared: Option<HeaderKind> = None;
    let mut file: Option<File> = None;
    let mut cut: Option<Broken> = None;
    loop {
        let field = match form.next_field().await {
            Ok(Some(field)) => field,
            Ok(None) => break,
            Err(e) => {
                cut = Some(broken(&e));
                break;
            }
        };
        match field.name() {
            Some("kind") => {
                let raw = match field.text().await {
                    Ok(raw) => raw,
                    Err(e) => {
                        cut = Some(broken(&e));
                        break;
                    }
                };
                let Some(kind) = HeaderKind::parse(&raw) else {
                    return refusal(
                        StatusCode::BAD_REQUEST,
                        KIND_UNKNOWN,
                        "`kind` must be `image`, `video` or `document`",
                    );
                };
                declared = Some(kind);
            }
            Some("file") if file.is_none() => match read_file(field, declared).await {
                Ok(read) => file = Some(read),
                Err(e) => {
                    cut = Some(e);
                    break;
                }
            },
            _ => {}
        }
    }
    let kind = declared.unwrap_or(HeaderKind::Image);
    match cut {
        Some(Broken::Form) => return not_a_form(),
        Some(Broken::Disk) => {
            tracing::warn!("flows: the WhatsApp header file could not be written to a temporary file");
            return refusal(
                StatusCode::INTERNAL_SERVER_ERROR,
                &kind.code("not_saved"),
                "the hub could not hold the file to store it",
            );
        }
        // The body outgrew the route while it was being read: past the largest cap of all.
        Some(Broken::TooLarge) if file.is_none() => return too_large(kind),
        _ => {}
    }
    let (media, tmp, size, digest_hex) = match file {
        None => {
            return refusal(
                StatusCode::BAD_REQUEST,
                &kind.code("missing"),
                "the form carries no `file` field",
            )
        }
        Some(File::Unrecognised) => return unsupported(kind),
        Some(File::TooLarge(media)) if media.kind() != kind => return unsupported(kind),
        Some(File::TooLarge(_)) => return too_large(kind),
        Some(File::Kept { media, .. }) if media.kind() != kind => return unsupported(kind),
        Some(File::Kept {
            media,
            tmp,
            size,
            digest_hex,
        }) => (media, tmp, size, digest_hex),
    };
    let name = stored_name(&digest_hex, media);
    if !crate::media::store_vetted_file(
        &st,
        HEADER_MEDIA_FOLDER,
        &name,
        tmp.path(),
        size as u64,
        media.mime_type(),
    )
    .await
    {
        tracing::warn!(file = %name, "flows: the WhatsApp header file could not be stored");
        return refusal(
            StatusCode::BAD_GATEWAY,
            &kind.code("not_saved"),
            "erplora.com could not store the file",
        );
    }
    (
        StatusCode::CREATED,
        Json(json!({
            "ok": true,
            "data": {
                "ref": format!("{HEADER_MEDIA_FOLDER}/{name}"),
                "mime_type": media.mime_type(),
                "size": size,
            }
        })),
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::notify_transport::{header_media_file, header_media_kind};

    /// A form that already named its header's kind has a file of another kind refused on its first
    /// bytes: a PDF on a photo header is not written to a temporary file and hashed first (the
    /// handler would refuse it after, with the same code — this is the disk it does not spend).
    #[tokio::test]
    async fn a_file_of_another_kind_than_declared_is_refused_before_it_is_spooled() {
        use axum::extract::FromRequest;

        const B: &str = "sniffboundary";
        let mut body = format!(
            "--{B}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"menu\"\r\n\r\n"
        )
        .into_bytes();
        body.extend_from_slice(b"%PDF-1.7\n1 0 obj\n");
        body.extend_from_slice(format!("\r\n--{B}--\r\n").as_bytes());
        let request = axum::http::Request::builder()
            .header("content-type", format!("multipart/form-data; boundary={B}"))
            .body(axum::body::Body::from(body))
            .expect("request");
        let mut form = Multipart::from_request(request, &()).await.expect("a form");
        let field = form.next_field().await.expect("a field").expect("the file");
        let read = read_file(field, Some(HeaderKind::Image)).await;
        assert!(matches!(read, Ok(File::Unrecognised)), "a PDF is not a photo");
    }

    #[test]
    fn a_header_file_is_told_by_its_bytes_not_its_name() {
        assert_eq!(
            HeaderMedia::sniff(b"\xff\xd8\xff\xe0JFIF"),
            Some(HeaderMedia::Jpeg)
        );
        assert_eq!(
            HeaderMedia::sniff(b"\x89PNG\r\n\x1a\n\0\0"),
            Some(HeaderMedia::Png)
        );
        assert_eq!(HeaderMedia::sniff(b"%PDF-1.7"), Some(HeaderMedia::Pdf));
        for brand in [b"mp42", b"isom", b"M4V ", b"avc1"] {
            let mut mp4 = b"\0\0\0\x18ftyp".to_vec();
            mp4.extend_from_slice(brand);
            assert_eq!(HeaderMedia::sniff(&mp4), Some(HeaderMedia::Mp4), "{brand:?}");
        }
        for other in [
            b"".as_slice(),
            b"\xff\xd8",
            b"\x89PNG\r\n\x1a",
            b"%PDF",
            b"GIF89a",
            b"RIFF\0\0\0\0WEBP",
            b"\0\0\0\x14ftypqt  ",
            b"\0\0\0\x14ftyp3gp5",
            b"\0\0\0\x14ftyp3g2a",
            b"\0\0\0\x14ftypmp4",
            b"\0\0\0\x14moovmp42",
        ] {
            assert_eq!(HeaderMedia::sniff(other), None, "{other:?}");
        }
    }

    /// Each kind of header takes its own kinds of file, under Meta's cap for it.
    #[test]
    fn each_file_fills_the_header_of_its_kind_under_metas_cap() {
        assert_eq!(HeaderMedia::Jpeg.kind(), HeaderKind::Image);
        assert_eq!(HeaderMedia::Png.kind(), HeaderKind::Image);
        assert_eq!(HeaderMedia::Mp4.kind(), HeaderKind::Video);
        assert_eq!(HeaderMedia::Pdf.kind(), HeaderKind::Document);
        assert_eq!(HeaderKind::Image.max_bytes(), 5 * 1024 * 1024);
        assert_eq!(HeaderKind::Video.max_bytes(), 16 * 1024 * 1024);
        assert_eq!(HeaderKind::Document.max_bytes(), 100 * 1024 * 1024);
        for (raw, kind) in [
            ("image", HeaderKind::Image),
            ("video", HeaderKind::Video),
            ("document", HeaderKind::Document),
        ] {
            assert_eq!(HeaderKind::parse(raw), Some(kind));
        }
        for raw in ["", "text", "audio", "Image", " video"] {
            assert_eq!(HeaderKind::parse(raw), None, "{raw:?}");
        }
    }

    /// The name is the file's fingerprint with the extension of what it is; and it is a reference
    /// the send accepts FOR ITS KIND — the two halves agree on what a stored header looks like.
    #[test]
    fn the_stored_name_is_the_fingerprint_and_the_send_takes_it_for_its_kind() {
        let digest = hex(&Sha256::digest(b"\xff\xd8\xffone"));
        assert_eq!(digest.len(), 64);
        for (media, extension, kind) in [
            (HeaderMedia::Jpeg, "jpg", "image"),
            (HeaderMedia::Png, "png", "image"),
            (HeaderMedia::Mp4, "mp4", "video"),
            (HeaderMedia::Pdf, "pdf", "document"),
        ] {
            let name = stored_name(&digest, media);
            assert_eq!(name, format!("{digest}.{extension}"));
            let reference = format!("{HEADER_MEDIA_FOLDER}/{name}");
            assert_eq!(header_media_file(&reference), Some(reference.as_str()));
            assert_eq!(header_media_kind(&reference), Some(kind), "{reference}");
            assert_eq!(media.kind().name(), kind);
        }
    }
}
