//! Perfil del usuario autenticado. No existe `/:user_id`: el objetivo siempre se resuelve desde
//! `X-Hub-Session`, lo que impide editar el perfil de otra persona.

use std::path::{Component, Path};

use axum::body::Body;
use axum::extract::{Multipart, State};
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use erplora_runtime::user_profile::{UpdateUserProfile, UserProfile};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::{auth, state::AppState};

const MAX_AVATAR_BYTES: usize = 2 * 1024 * 1024;

fn error(status: StatusCode, message: impl Into<String>) -> Response {
    (
        status,
        Json(json!({ "ok": false, "error": message.into() })),
    )
        .into_response()
}

fn profile_json(profile: UserProfile, permissions: impl IntoIterator<Item = String>) -> Value {
    let avatar_url = profile.avatar_path.as_ref().map(|_| "/api/profile/avatar");
    json!({
        "id": profile.id,
        "name": profile.name,
        "first_name": profile.first_name,
        "last_name": profile.last_name,
        "email": profile.email,
        "role": profile.role,
        "cloud_user_id": profile.cloud_user_id,
        "avatar_url": avatar_url,
        "preferences": profile.preferences,
        "permissions": permissions.into_iter().collect::<Vec<_>>(),
    })
}

async fn current_user_id(
    st: &AppState,
    headers: &HeaderMap,
) -> Result<
    (
        crate::state::SharedRuntime,
        String,
    ),
    Response,
> {
    let arc = st
        .runtime_for(&st.hub_id())
        .await
        .map_err(crate::tenant_rejected)?;
    let user_id = {
        let rt = arc.read().await;
        // Incluso en AuthMode::Dev, si el shell trae una sesión local válida (login PIN/cloud),
        // úsala. El modo Dev normalmente confía en X-User-Id, pero runtimeHeaders no suplanta esa
        // cabecera y la sesión sigue siendo la identidad real del usuario visible en el shell.
        if let Some(token) = auth::session_token(headers) {
            if let Some(user) = rt
                .resolve_session(&token)
                .await
                .map_err(|e| error(StatusCode::UNAUTHORIZED, e.to_string()))?
            {
                return Ok((arc.clone(), user.id));
            }
        }
        let ctx = auth::require_user_session(headers, &st.config, &rt)
            .await
            .map_err(|e| error(StatusCode::UNAUTHORIZED, e.message()))?;
        if st.config.auth_mode == crate::AuthMode::Dev {
            let name = headers
                .get("x-user-name")
                .and_then(|v| v.to_str().ok())
                .filter(|v| !v.trim().is_empty())
                .unwrap_or("Demo");
            let role = headers
                .get("x-user-role")
                .and_then(|v| v.to_str().ok())
                .filter(|v| !v.trim().is_empty())
                .unwrap_or("admin");
            rt.ensure_dev_user(&ctx.user_id, name, role)
                .await
                .map_err(crate::err_response)?;
        }
        ctx.user_id
    };
    Ok((arc, user_id))
}

pub async fn get_profile(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let (arc, user_id) = match current_user_id(&st, &headers).await {
        Ok(value) => value,
        Err(response) => return response,
    };
    let rt = arc.read().await;
    match rt.user_profile(&user_id).await {
        Ok(profile) => {
            let permissions = rt.session_permissions(&profile.role);
            Json(profile_json(profile, permissions)).into_response()
        }
        Err(e) => crate::err_response(e),
    }
}

pub async fn put_profile(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(input): Json<UpdateUserProfile>,
) -> Response {
    let (arc, user_id) = match current_user_id(&st, &headers).await {
        Ok(value) => value,
        Err(response) => return response,
    };
    let rt = arc.read().await;
    match rt.update_user_profile(&user_id, &input).await {
        Ok(profile) => {
            let permissions = rt.session_permissions(&profile.role);
            Json(profile_json(profile, permissions)).into_response()
        }
        Err(e) => crate::err_response(e),
    }
}

fn safe_relative(path: &str) -> bool {
    !path.is_empty()
        && Path::new(path)
            .components()
            .all(|c| matches!(c, Component::Normal(_)))
}

pub async fn get_avatar(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let (arc, user_id) = match current_user_id(&st, &headers).await {
        Ok(value) => value,
        Err(response) => return response,
    };
    let profile = {
        let rt = arc.read().await;
        match rt.user_profile(&user_id).await {
            Ok(profile) => profile,
            Err(e) => return crate::err_response(e),
        }
    };
    let Some(relative) = profile.avatar_path.filter(|p| safe_relative(p)) else {
        return error(StatusCode::NOT_FOUND, "foto no encontrada");
    };
    let target = st.config.media_dir.join(&relative);
    let bytes = match tokio::fs::read(&target).await {
        Ok(bytes) => bytes,
        Err(_) => return error(StatusCode::NOT_FOUND, "foto no encontrada"),
    };
    let content_type = match target.extension().and_then(|s| s.to_str()) {
        Some("png") => "image/png",
        Some("webp") => "image/webp",
        _ => "image/jpeg",
    };
    Response::builder()
        .status(StatusCode::OK)
        .header(header::CONTENT_TYPE, content_type)
        .header(header::CACHE_CONTROL, "private, no-cache")
        .header("X-Content-Type-Options", "nosniff")
        .body(Body::from(bytes))
        .unwrap_or_else(|_| error(StatusCode::INTERNAL_SERVER_ERROR, "respuesta inválida"))
}

pub async fn upload_avatar(
    State(st): State<AppState>,
    headers: HeaderMap,
    mut multipart: Multipart,
) -> Response {
    let (arc, user_id) = match current_user_id(&st, &headers).await {
        Ok(value) => value,
        Err(response) => return response,
    };

    let mut upload: Option<(Vec<u8>, &'static str)> = None;
    while let Ok(Some(field)) = multipart.next_field().await {
        if field.name() != Some("avatar") {
            continue;
        }
        let extension = match field.content_type() {
            Some("image/jpeg") => "jpg",
            Some("image/png") => "png",
            Some("image/webp") => "webp",
            _ => {
                return error(
                    StatusCode::UNSUPPORTED_MEDIA_TYPE,
                    "usa una imagen JPG, PNG o WebP",
                )
            }
        };
        let bytes = match field.bytes().await {
            Ok(bytes) if !bytes.is_empty() && bytes.len() <= MAX_AVATAR_BYTES => bytes.to_vec(),
            Ok(bytes) if bytes.len() > MAX_AVATAR_BYTES => {
                return error(StatusCode::PAYLOAD_TOO_LARGE, "la foto supera 2 MB")
            }
            _ => return error(StatusCode::BAD_REQUEST, "foto vacía o inválida"),
        };
        let valid_signature = match extension {
            "jpg" => bytes.starts_with(&[0xff, 0xd8, 0xff]),
            "png" => bytes.starts_with(b"\x89PNG\r\n\x1a\n"),
            "webp" => bytes.len() >= 12 && bytes.starts_with(b"RIFF") && &bytes[8..12] == b"WEBP",
            _ => false,
        };
        if !valid_signature {
            return error(
                StatusCode::UNSUPPORTED_MEDIA_TYPE,
                "el contenido no corresponde a una imagen válida",
            );
        }
        upload = Some((bytes, extension));
        break;
    }
    let Some((bytes, extension)) = upload else {
        return error(StatusCode::BAD_REQUEST, "falta el campo avatar");
    };
    let previous = {
        let rt = arc.read().await;
        rt.user_profile(&user_id)
            .await
            .ok()
            .and_then(|profile| profile.avatar_path)
    };

    let key = format!(
        "{:x}",
        Sha256::digest(format!("{}:{user_id}", st.hub_id()).as_bytes())
    );
    let relative = format!("_profiles/{key}.{extension}");
    let directory = st.config.media_dir.join("_profiles");
    if tokio::fs::create_dir_all(&directory).await.is_err() {
        return error(
            StatusCode::INTERNAL_SERVER_ERROR,
            "no se pudo guardar la foto",
        );
    }
    let target = st.config.media_dir.join(&relative);
    if tokio::fs::write(&target, bytes).await.is_err() {
        return error(
            StatusCode::INTERNAL_SERVER_ERROR,
            "no se pudo guardar la foto",
        );
    }

    let saved = {
        let rt = arc.read().await;
        rt.set_user_avatar(&user_id, &relative).await
    };
    match saved {
        Ok(profile) => {
            if let Some(old) = previous.filter(|old| old != &relative && safe_relative(old)) {
                let _ = tokio::fs::remove_file(st.config.media_dir.join(old)).await;
            }
            let permissions = {
                let rt = arc.read().await;
                rt.session_permissions(&profile.role)
            };
            Json(profile_json(profile, permissions)).into_response()
        }
        Err(e) => {
            let _ = tokio::fs::remove_file(target).await;
            crate::err_response(e)
        }
    }
}

pub async fn delete_avatar(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let (arc, user_id) = match current_user_id(&st, &headers).await {
        Ok(value) => value,
        Err(response) => return response,
    };
    let previous = {
        let rt = arc.read().await;
        match rt.user_profile(&user_id).await {
            Ok(profile) => profile.avatar_path,
            Err(e) => return crate::err_response(e),
        }
    };
    let profile = {
        let rt = arc.read().await;
        match rt.set_user_avatar(&user_id, "").await {
            Ok(profile) => profile,
            Err(e) => return crate::err_response(e),
        }
    };
    if let Some(relative) = previous.filter(|p| safe_relative(p)) {
        let _ = tokio::fs::remove_file(st.config.media_dir.join(relative)).await;
    }
    let permissions = {
        let rt = arc.read().await;
        rt.session_permissions(&profile.role)
    };
    Json(profile_json(profile, permissions)).into_response()
}
