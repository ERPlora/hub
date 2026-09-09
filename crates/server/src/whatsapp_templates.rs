//! The business's WhatsApp **templates**, hub → SaaS → Meta (hub#1610) — the hub half of saas#1899.
//!
//! The owner writes a template in the WhatsApp module's «Plantillas» tab. For a message to leave
//! the business outside the 24 h since the customer last wrote, Meta has to have approved that
//! template first, and who talks to Meta is the SaaS (ADR-0012: the Meta token never leaves it).
//! The module cannot call that door itself — it opens with the hub's **machine credential**, a
//! secret of the runtime that never reaches the browser (ADR-0003) — so the runtime proxies it.
//!
//! Three doors, same gate as the four of [`crate::whatsapp_connect`]: **owner/admin session**,
//! because what the business promises Meta is management, not the shift. Nothing the SaaS says is
//! reinterpreted: the payload travels whole and a refusal keeps its own `code` (`invalid_name`,
//! `missing_example`, `meta_rate_limited`…, saas#1902/#1905), because it is the MODULE that turns
//! each one into a sentence with its `en` + `es` strings (ADR-0055). A code translated to prose
//! here is a code the tab can no longer act on.
//!
//! 🔴 **But it travels in the runtime's ENVELOPE, not as the SaaS's bare body** (hub#1688). These
//! are the only cloud proxies module code can reach, and module code never fetches: it goes
//! through `@erplora/module-sdk`, whose transport ends every call in `unwrap(env)` and reads
//! `{ok:true,data}` / `{ok:false,error:{code,message}}`. Handed the SaaS's plain body, that
//! transport threw `unknown error` on EVERY call — a template Meta had accepted was reported to
//! the business as «error», and `invalid_name` arrived with the code stripped off. The envelope is
//! not a reinterpretation of the SaaS: it is the only channel through which its code reaches the
//! module at all. See [`cloud_proxy::cloud_envelope_passthrough`].
use crate::*;
use erplora_runtime::host_notify;
use erplora_runtime::manifest::CapabilityKind;

/// The gate of the three doors: the human **and**, when the caller names a module, the `notify`
/// capability declared in its manifest and granted by the owner (hub#1682).
///
/// The human half does not move — it is [`whatsapp_connect::require_owner`], the same one the four
/// connect doors use, so an anonymous caller is still `401` and a cashier still `403`.
///
/// The module half is new because the CALLER is new. Until hub#1682 nothing in module code could
/// reach these routes: `ErploraClient` never exposed the transport and `coreRequest` is sealed on
/// purpose, so an admin session was the whole gate and that was the whole risk. The typed
/// `whatsappTemplates` surface of `@erplora/module-sdk` changes that — reaching it becomes possible
/// for EVERY installed module, whenever an admin happens to be logged in — and what is behind the
/// door is not a read: it is registering, in the business's own Meta account, the templates it will
/// be judged by, and DELETING the ones already approved. Losing them costs the business every
/// appointment reminder and every «your order is ready» until Meta approves them again, which takes
/// days.
///
/// **`notify`, and no new capability** (the criterion of ADR-0470). It is the one the owner already
/// grants as «Notificaciones · permite enviar notificaciones por email, SMS o WhatsApp»
/// ([`crate::settings::capability_meta`]): a template approved by Meta is the ONLY thing that makes
/// a WhatsApp notification legal outside the 24 h since the customer last wrote, so this is the
/// same risk they weighed when they granted it, not a second one to explain.
///
/// ⚠️ **The hub#1677 exception does not reach here.** `admin_session_no_capability!` drops this half
/// for the flow-template switches because the call site replaces it with something NARROWER — a
/// module may only touch the recipes its own publisher wrote and signed. A Meta template has no
/// owning module: it belongs to the business, the SaaS stores it per hub, and there is no narrower
/// rule to put in the gate's place. With nothing to replace it, the default-deny gate stays.
///
/// **And the channel, not just the grant.** `notify` is granted as one switch, but the kernel
/// never lets a module SEND on a channel it did not declare — the outbox checks the grant and then
/// [`host_notify::assert_channel_declared`] («declaring `email` does not enable WhatsApp»). This
/// door keeps that second half: a module the owner granted `notify` to send e-mail receipts must
/// not be able to delete the business's approved WhatsApp templates, a channel it never asked for
/// and cannot even send on. Same function, same `capability_denied` code (`notify:whatsapp`).
async fn require_owner_and_notify(st: &AppState, headers: &HeaderMap) -> Result<(), Response> {
    whatsapp_connect::require_owner(st, headers).await?;
    let rt = st.runtime.read().await;
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
    if let Err(r) = require_owner_and_notify(&st, &headers).await {
        return r;
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    cloud_proxy::proxy_cloud_get_enveloped(
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
    if let Err(r) = require_owner_and_notify(&st, &headers).await {
        return r;
    }
    if !body.is_object() {
        return refused("whatsapp.invalid_body", "expected a JSON object");
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    cloud_proxy::proxy_cloud_send_enveloped(
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
    if let Err(r) = require_owner_and_notify(&st, &headers).await {
        return r;
    }
    if !template_name_is_safe(&name) {
        return refused(
            "whatsapp.invalid_template_name",
            "lowercase letters, digits and underscores only",
        );
    }
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    cloud_proxy::proxy_cloud_send_enveloped(
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
