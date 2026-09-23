//! **The public door** — the hub's first page served to somebody with no session (hub#963).
//!
//! A diner takes their ticket home. On it, next to the VeriFactu QR, there is a second QR and a
//! sixteen-character locator. They open it, type their tax details, and the hub issues the
//! complete invoice (F3) that substitutes their simplified one — no waiter typing a NIF at the
//! counter, no queue behind them, no employee involved. Ágora ships this as *CREAR FACTURA* and
//! Cuiner as *QuieroFactura*; the reglamento's blessed shape for it is the F3 with
//! `FacturasSustituidas`, and the hub already emits that (`invoice.substitute`, ADR-0140).
//!
//! ## The whole security model, in one paragraph
//!
//! **There is no session here, so the locator is the entire authorisation** — and it authorises
//! exactly one command, on exactly one subject, once. Everything else is sealed into the row at
//! the counter by [`erplora_runtime::public_claim`]: the amounts, the lines, the ticket being
//! substituted. What the visitor sends is filtered against `public_fields` before it reaches the
//! dispatcher, so a POST that names `items` or `original_invoice_id` changes nothing.
//!
//! The permission is not the visitor's, because a visitor has none. The door stamps **the
//! permission the claim's own command declares**, read from the registry — never a wildcard, never
//! a role. Whoever minted the claim had that permission already; the claim is a delegation of it,
//! narrowed to one row and one shot.
//!
//! ## Why the page is server-rendered HTML with no JavaScript
//!
//! The hub's CSP is `script-src 'self'` with no `'unsafe-inline'` (ADR-0050/0308) and the SPA is a
//! Vue app that assumes a session. Neither fits a stranger's phone on a restaurant's wifi. A plain
//! `<form method="post">` needs no script at all, works with the back button, and cannot be broken
//! by a hydration failure — the trap that already cost `<noscript>` once. Inline `<style>` **is**
//! allowed by the same policy, so the page can still look like something.
//!
//! One exception, and it is optional (sales#335): the module that mints a claim may offer the
//! answers a field accepts (`field_choices`, rendered as `<select>`s). When one of them is a list
//! of ISO region codes — which codes is the module's knowledge, never the core's (hub#1407) — the
//! page loads ONE same-origin file ([`NAMES_SCRIPT_PATH`]) that names them with the browser's
//! `Intl.DisplayNames`. Nothing inline, no handler attributes, and the form submits the same
//! without it (the codes are the labels then).
//!
//! Spanish and English both, chosen from the hub's own `language` setting and overridable with
//! `?lang=`: the page is read by the merchant's CUSTOMER, who never logged in anywhere and whose
//! browser is the only hint we have.

use axum::extract::{Path, Query, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use erplora_runtime::public_claim::{self, ClaimRefusal, NewClaim};
use erplora_runtime::registry::RequestContext;
use serde::Deserialize;
use serde_json::{json, Value};

use crate::auth;
use crate::state::AppState;

/// Where the public page lives. Short on purpose: it is printed under a QR on 80 mm of thermal
/// paper and, when the camera fails, typed by hand into a phone.
pub const PUBLIC_PREFIX: &str = "/p";

/// Paths the machine-registration gate must let through even on a hub that has not enrolled yet.
/// The customer holding the ticket cannot enrol anything, and a hub that already printed a
/// locator has to honour it.
pub fn is_public_path(path: &str) -> bool {
    path == PUBLIC_PREFIX || path.starts_with("/p/")
}

// ── minting (session-gated) ─────────────────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct MintRequest {
    pub kind: String,
    pub subject_id: String,
    pub command: String,
    #[serde(default)]
    pub sealed_payload: Value,
    #[serde(default)]
    pub public_fields: Vec<String>,
    /// sales#335 — the answers the minter offers for some of `public_fields` (see
    /// [`NewClaim::field_choices`]). A separate key on purpose: a hub that predates it ignores it
    /// and still mints, so the ticket never loses its QR over a newer module.
    #[serde(default)]
    pub public_field_choices: Value,
    #[serde(default)]
    pub expires_at: Option<String>,
}

/// The most options one field may carry. A claim is a row per printed ticket; a country list is
/// ~250, so this leaves room without letting a minter park anything in it.
const MAX_CHOICE_OPTIONS: usize = 400;

/// `public_field_choices`, kept to the fields the visitor may actually fill, or `None` when it is
/// not an object of `{options: [...]}` within [`MAX_CHOICE_OPTIONS`].
fn accepted_choices(raw: &Value, fields: &[String]) -> Option<Value> {
    if raw.is_null() {
        return Some(json!({}));
    }
    let map = raw.as_object()?;
    let mut kept = serde_json::Map::new();
    for (field, spec) in map {
        let options = spec.get("options")?.as_array()?;
        if options.len() > MAX_CHOICE_OPTIONS {
            return None;
        }
        if fields.contains(field) {
            kept.insert(field.clone(), spec.clone());
        }
    }
    Some(Value::Object(kept))
}

/// `POST /api/hub/public-claims` — mint the locator for a ticket.
///
/// Session-gated, and gated **again** on the permission the target command declares: minting a
/// claim is handing out the right to run that command, so anyone who could mint one for a command
/// they cannot run themselves would have found a way to escalate by printing a receipt.
///
/// Idempotent, which is what lets the POS call it on every print without tracking whether it
/// already did: a reprint returns the locator the customer's first copy already carries.
pub async fn mint_claim(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<MintRequest>,
) -> Response {
    let hub_id = st.hub_id();
    let runtime = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(error) => return crate::tenant_rejected(error),
    };
    let rt = runtime.read().await;
    let ctx = match auth::authenticate(&headers, &st.config, &rt).await {
        Ok(ctx) => ctx,
        Err(e) => return crate::unauthorized(e),
    };
    let Some(command) = rt.registry().get_command(&req.command) else {
        return refusal(
            StatusCode::BAD_REQUEST,
            "unknown_command",
            "no such command in this hub",
        );
    };
    let needed = command.def.permission.clone();
    // The dispatcher's own predicate, not a re-implementation: two answers to "may this context
    // run this?" would eventually disagree, and the half that says yes is the one that matters.
    if !needed.is_empty() && !erplora_runtime::permissions::has(&ctx, &needed) {
        return refusal(
            StatusCode::FORBIDDEN,
            "permission_denied",
            "minting a claim hands out this command; you must be able to run it yourself",
        );
    }
    let Some(field_choices) = accepted_choices(&req.public_field_choices, &req.public_fields)
    else {
        return refusal(
            StatusCode::BAD_REQUEST,
            "invalid_choices",
            "public_field_choices must map fields to {options: [...]} of at most 400 options",
        );
    };
    let spec = NewClaim {
        kind: req.kind,
        subject_id: req.subject_id,
        command: req.command,
        sealed_payload: if req.sealed_payload.is_null() {
            json!({})
        } else {
            req.sealed_payload
        },
        public_fields: req.public_fields,
        field_choices,
        expires_at: req.expires_at,
        created_by: ctx.user_id.clone(),
    };
    match public_claim::mint(rt.db(), &hub_id, spec).await {
        Ok(locator) => Json(json!({
            "ok": true,
            "locator": locator,
            "url": format!("{PUBLIC_PREFIX}/{locator}"),
        }))
        .into_response(),
        Err(e) => crate::err_response(e),
    }
}

// ── the public page ─────────────────────────────────────────────────────────────────────────

#[derive(Debug, Default, Deserialize)]
pub struct PageQuery {
    /// `es` / `en`. Absent → the hub's own `language` setting.
    pub lang: Option<String>,
}

/// `GET /p/:locator` — the form, or the invoice if it was already issued.
pub async fn show(
    State(st): State<AppState>,
    Path(locator): Path<String>,
    Query(q): Query<PageQuery>,
    headers: HeaderMap,
) -> Response {
    let (hub_id, runtime) = match resolve(&st).await {
        Ok(v) => v,
        Err(r) => return r,
    };
    let rt = runtime.read().await;
    let lang = language(&st, &rt, q.lang.as_deref()).await;
    let key = throttle_key(&headers, &locator);
    if let Some(retry) = st.login_throttle.locked_for(&key) {
        return page(
            StatusCode::TOO_MANY_REQUESTS,
            &lang,
            Body::Message(t(&lang, "tooMany").replace("{secs}", &retry.to_string())),
            &locator,
        );
    }
    let now = public_claim::now();
    match public_claim::redeemable(rt.db(), &hub_id, &locator, &now).await {
        Ok(Ok(claim)) => {
            st.login_throttle.record_success(&key);
            let (fields, choices) = (claim.public_fields, claim.field_choices);
            page(
                StatusCode::OK,
                &lang,
                Body::Form { fields, choices },
                &locator,
            )
        }
        Ok(Err(ClaimRefusal::AlreadyRedeemed(_))) => {
            st.login_throttle.record_success(&key);
            let reference = public_claim::find(rt.db(), &hub_id, &locator)
                .await
                .ok()
                .flatten()
                .map(|c| c.result_ref)
                .unwrap_or_default();
            page(StatusCode::OK, &lang, Body::Done { reference }, &locator)
        }
        Ok(Err(ClaimRefusal::Expired(until))) => page(
            StatusCode::GONE,
            &lang,
            Body::Message(t(&lang, "expired").replace("{date}", &day_of(&until))),
            &locator,
        ),
        Ok(Err(ClaimRefusal::NotFound)) => {
            st.login_throttle.record_failure(&key);
            page(
                StatusCode::NOT_FOUND,
                &lang,
                Body::Message(t(&lang, "unknown").into()),
                &locator,
            )
        }
        Err(e) => {
            eprintln!("[public-door] lookup failed: {e}");
            page(
                StatusCode::INTERNAL_SERVER_ERROR,
                &lang,
                Body::Message(t(&lang, "oops").into()),
                &locator,
            )
        }
    }
}

/// What the visitor typed. Everything is optional at this layer: the claim's own command schema is
/// the authority on what is required, and duplicating that here would be a second contract that
/// eventually disagrees with the first.
#[derive(Debug, Default, Deserialize)]
pub struct RedeemForm {
    #[serde(flatten)]
    pub fields: std::collections::BTreeMap<String, String>,
}

/// `POST /p/:locator` — issue the document and show it.
pub async fn redeem(
    State(st): State<AppState>,
    Path(locator): Path<String>,
    Query(q): Query<PageQuery>,
    headers: HeaderMap,
    axum::extract::Form(form): axum::extract::Form<RedeemForm>,
) -> Response {
    let (hub_id, runtime) = match resolve(&st).await {
        Ok(v) => v,
        Err(r) => return r,
    };
    let rt = runtime.read().await;
    let lang = language(&st, &rt, q.lang.as_deref()).await;
    let key = throttle_key(&headers, &locator);
    if let Some(retry) = st.login_throttle.locked_for(&key) {
        return page(
            StatusCode::TOO_MANY_REQUESTS,
            &lang,
            Body::Message(t(&lang, "tooMany").replace("{secs}", &retry.to_string())),
            &locator,
        );
    }
    let now = public_claim::now();
    let claim = match public_claim::redeemable(rt.db(), &hub_id, &locator, &now).await {
        Ok(Ok(claim)) => claim,
        Ok(Err(ClaimRefusal::AlreadyRedeemed(_))) => {
            // Not an error: the second tab, or the customer pressing back and submitting again.
            // Showing them their invoice is the only answer that is both true and useful.
            let reference = public_claim::find(rt.db(), &hub_id, &locator)
                .await
                .ok()
                .flatten()
                .map(|c| c.result_ref)
                .unwrap_or_default();
            return page(StatusCode::OK, &lang, Body::Done { reference }, &locator);
        }
        Ok(Err(ClaimRefusal::Expired(until))) => {
            return page(
                StatusCode::GONE,
                &lang,
                Body::Message(t(&lang, "expired").replace("{date}", &day_of(&until))),
                &locator,
            )
        }
        Ok(Err(ClaimRefusal::NotFound)) => {
            st.login_throttle.record_failure(&key);
            return page(
                StatusCode::NOT_FOUND,
                &lang,
                Body::Message(t(&lang, "unknown").into()),
                &locator,
            );
        }
        Err(e) => {
            eprintln!("[public-door] lookup failed: {e}");
            return page(
                StatusCode::INTERNAL_SERVER_ERROR,
                &lang,
                Body::Message(t(&lang, "oops").into()),
                &locator,
            );
        }
    };

    // The permission comes from the command the claim names, read from the registry. Not a
    // wildcard and not a role: the claim delegates exactly what its command asks for.
    let Some(registered) = rt.registry().get_command(&claim.command) else {
        return page(
            StatusCode::CONFLICT,
            &lang,
            Body::Message(t(&lang, "unavailable").into()),
            &locator,
        );
    };
    let permission = registered.def.permission.clone();
    let payload = public_claim::merge_payload(&claim, &json!(form.fields));

    // Spend FIRST. A claim spent on a command that then fails is recoverable at the counter; a
    // command that succeeds twice is two complete invoices substituting one ticket, in a fiscal
    // chain that cannot be un-sent.
    match public_claim::spend(rt.db(), &hub_id, &claim.id, "", &now).await {
        Ok(true) => {}
        Ok(false) => {
            let reference = public_claim::find(rt.db(), &hub_id, &locator)
                .await
                .ok()
                .flatten()
                .map(|c| c.result_ref)
                .unwrap_or_default();
            return page(StatusCode::OK, &lang, Body::Done { reference }, &locator);
        }
        Err(e) => return crate::err_response(e),
    }

    let ctx = RequestContext::new(
        hub_id.clone(),
        format!("public-claim:{}", claim.id),
        std::iter::once(permission).filter(|p| !p.is_empty()),
    );
    match rt.execute_command(&claim.command, &payload, &ctx).await {
        Ok(result) => {
            let reference = reference_of(&result);
            let _ = public_claim::record_result(rt.db(), &hub_id, &claim.id, &reference).await;
            page(StatusCode::OK, &lang, Body::Done { reference }, &locator)
        }
        Err(e) => {
            // Hand the claim back: the visitor mistyped a NIF, or the hub is missing its fiscal
            // identity. Burning their one shot on our refusal would send them back to the counter
            // for something they can fix in five seconds.
            let _ = public_claim::release(rt.db(), &hub_id, &claim.id).await;
            st.login_throttle.record_failure(&key);
            let detail = domain_detail(&e).unwrap_or_else(|| t(&lang, "rejected").into());
            page(
                StatusCode::UNPROCESSABLE_ENTITY,
                &lang,
                Body::Retry {
                    problem: detail,
                    // hub#1989: what they typed comes back — only the fields they may fill.
                    typed: form
                        .fields
                        .into_iter()
                        .filter(|(key, _)| claim.public_fields.contains(key))
                        .collect(),
                    fields: claim.public_fields.clone(),
                    choices: claim.field_choices.clone(),
                },
                &locator,
            )
        }
    }
}

// ── plumbing ────────────────────────────────────────────────────────────────────────────────

type Resolved = (String, crate::state::SharedRuntime);

async fn resolve(st: &AppState) -> Result<Resolved, Response> {
    let hub_id = st.hub_id();
    match st.runtime_for(&hub_id).await {
        Ok(rt) => Ok((hub_id, rt)),
        Err(error) => Err(crate::tenant_rejected(error)),
    }
}

/// What the brute-force guard counts against.
///
/// The client's address when a proxy tells us one, otherwise the locator itself. Never both:
/// keying only on the locator would let an enumerator rotate targets freely, and keying only on
/// the address would lock out a whole restaurant's wifi the moment one guest mistypes.
///
/// 🔴 **The LAST entry of `X-Forwarded-For`, not the first.** The header is a list a client can
/// start: anybody may send `X-Forwarded-For: whatever` and, reading the first hop, get themselves
/// a brand-new counter on every request — a throttle that an attacker resets at will is not a
/// throttle. The nearest proxy **appends** the peer it actually saw, so the last entry is the only
/// one this hub did not take somebody's word for. (Traefik in production, ADR-0092; the hub is
/// never exposed directly.)
///
/// Enumeration itself is not what this stops — eighty bits of HMAC output is what stops that. This
/// is the second lock, for the case where a locator leaks and somebody grinds at the form.
fn throttle_key(headers: &HeaderMap, locator: &str) -> String {
    let client = headers
        .get("x-forwarded-for")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.rsplit(',').next())
        .map(str::trim)
        .filter(|v| !v.is_empty());
    match client {
        Some(ip) => format!("public-claim:ip:{ip}"),
        None => format!(
            "public-claim:loc:{}",
            public_claim::normalize_locator(locator)
        ),
    }
}

/// The language the page is written in: `?lang=` if it names one we have, else the hub's own
/// `language` setting, else Spanish.
async fn language(
    _st: &AppState,
    rt: &erplora_runtime::Runtime,
    requested: Option<&str>,
) -> String {
    if let Some(want) = requested {
        let want = want.trim().to_ascii_lowercase();
        if want == "en" || want == "es" {
            return want;
        }
    }
    let settings = rt.get_settings().await.unwrap_or_else(|_| json!({}));
    match settings.get("language").and_then(Value::as_str) {
        Some("en") => "en".into(),
        _ => "es".into(),
    }
}

/// What the redemption produced, for the visitor to quote at the counter. Best-effort by design:
/// the core does not know what shape a module's result has, so it looks for the two keys every
/// document-issuing command in the hub already returns and falls back to nothing.
fn reference_of(result: &Value) -> String {
    for key in ["number", "invoice_number", "id", "invoice_id"] {
        if let Some(v) = result.get(key).and_then(Value::as_str) {
            if !v.is_empty() {
                return v.to_string();
            }
        }
    }
    String::new()
}

/// The part of a runtime error a **customer** may read.
///
/// Only `Domain` — that is the channel a module uses to say something true about the request
/// ("this NIF is not valid", ADR-0205). Everything else is the hub's own plumbing, and pasting a
/// pool error onto a stranger's phone tells them nothing and us too much.
fn domain_detail(e: &erplora_runtime::RuntimeError) -> Option<String> {
    match e {
        erplora_runtime::RuntimeError::Domain { message, .. } => Some(message.clone()),
        erplora_runtime::RuntimeError::InvalidPayload { detail, .. } => Some(detail.clone()),
        erplora_runtime::RuntimeError::InvalidField { detail, .. } => Some(detail.clone()),
        _ => None,
    }
}

fn day_of(rfc3339: &str) -> String {
    rfc3339.split('T').next().unwrap_or(rfc3339).to_string()
}

fn refusal(status: StatusCode, code: &str, message: &str) -> Response {
    (
        status,
        Json(json!({ "ok": false, "error": { "code": code, "message": message } })),
    )
        .into_response()
}

// ── the page itself ─────────────────────────────────────────────────────────────────────────

enum Body {
    /// Ask for the tax details — only the ones the claim lets the visitor fill.
    Form { fields: Vec<String>, choices: Value },
    /// Already issued (now or before) — show the reference.
    Done { reference: String },
    /// The form again, with what went wrong on top.
    Retry {
        problem: String,
        /// What the visitor sent, already narrowed to the claim's `public_fields` (hub#1989).
        typed: Typed,
        fields: Vec<String>,
        choices: Value,
    },
    /// A dead end: unknown locator, expired, or a hub-side failure.
    Message(String),
}

/// Minimal HTML escaping. Every value that reaches the page passes through it — the locator comes
/// straight off a URL a stranger typed.
fn esc(raw: &str) -> String {
    raw.chars()
        .map(|c| match c {
            '&' => "&amp;".to_string(),
            '<' => "&lt;".to_string(),
            '>' => "&gt;".to_string(),
            '"' => "&quot;".to_string(),
            '\'' => "&#39;".to_string(),
            other => other.to_string(),
        })
        .collect()
}

/// The string table. English is the source and Spanish is its translation (ADR-0055/0199) — the
/// same rule the SPA follows, applied to the one page the SPA cannot render.
fn t(lang: &str, key: &str) -> &'static str {
    let en = match key {
        "title" => "Get your invoice",
        "intro" => "Turn the receipt you were given into a complete invoice with your tax details.",
        "taxId" => "Tax ID (NIF/CIF)",
        "name" => "Name or company name",
        "address" => "Address",
        "submit" => "Issue my invoice",
        "doneTitle" => "Your invoice is issued",
        "doneBody" => "Keep this reference. If you need a copy, show it at the counter.",
        "unknown" => "This code does not correspond to any receipt from this business. Check that you typed it exactly as printed.",
        "expired" => "The deadline for requesting an invoice for this receipt ended on {date}. Ask at the counter.",
        "tooMany" => "Too many attempts. Try again in {secs} seconds.",
        "oops" => "Something went wrong on our side. Try again in a moment.",
        "rejected" => "The details could not be accepted. Check the tax ID and try again.",
        "unavailable" => "This business cannot issue invoices right now. Ask at the counter.",
        "locator" => "Receipt code",
        "reference" => "Invoice",
        _ => "",
    };
    if lang == "en" {
        return en;
    }
    match key {
        "title" => "Pide tu factura",
        "intro" => "Convierte el tique que te han dado en una factura completa con tus datos fiscales.",
        "taxId" => "NIF/CIF",
        "name" => "Nombre o razón social",
        "address" => "Domicilio",
        "submit" => "Emitir mi factura",
        "doneTitle" => "Tu factura está emitida",
        "doneBody" => "Guarda esta referencia. Si necesitas una copia, enséñala en el mostrador.",
        "unknown" => "Este código no corresponde a ningún tique de este negocio. Comprueba que lo has escrito tal como está impreso.",
        "expired" => "El plazo para pedir factura de este tique terminó el {date}. Pregunta en el mostrador.",
        "tooMany" => "Demasiados intentos. Vuelve a probar en {secs} segundos.",
        "oops" => "Algo ha fallado por nuestra parte. Inténtalo dentro de un momento.",
        "rejected" => "No se han podido aceptar los datos. Revisa el NIF y vuelve a intentarlo.",
        "unavailable" => "Este negocio no puede emitir facturas ahora mismo. Pregunta en el mostrador.",
        "locator" => "Código del tique",
        "reference" => "Factura",
        _ => en,
    }
}

/// The whole page. Inline `<style>` and no `<script>` at all: that is exactly what the hub's CSP
/// allows (`style-src 'self' 'unsafe-inline'`, `script-src 'self'`), and it is also what makes the
/// page survive a phone that blocks scripts on public wifi.
fn page(status: StatusCode, lang: &str, body: Body, locator: &str) -> Response {
    let title = esc(t(lang, "title"));
    let main = match &body {
        Body::Form { fields, choices } => {
            form_html(lang, locator, None, fields, choices, &Typed::new())
        }
        Body::Retry {
            problem,
            typed,
            fields,
            choices,
        } => form_html(lang, locator, Some(problem), fields, choices, typed),
        Body::Done { reference } => {
            let ref_line = if reference.is_empty() {
                String::new()
            } else {
                format!(
                    "<p class=\"ref\"><span>{}</span><strong>{}</strong></p>",
                    esc(t(lang, "reference")),
                    esc(reference)
                )
            };
            format!(
                "<h1>{}</h1>{ref_line}<p>{}</p>",
                esc(t(lang, "doneTitle")),
                esc(t(lang, "doneBody"))
            )
        }
        Body::Message(message) => format!("<h1>{title}</h1><p class=\"warn\">{}</p>", esc(message)),
    };
    let html = format!(
        "<!doctype html><html lang=\"{lang}\"><head>\
<meta charset=\"utf-8\">\
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\
<meta name=\"robots\" content=\"noindex,nofollow\">\
<title>{title}</title>\
<style>{STYLE}</style></head><body><main>{main}</main></body></html>"
    );
    (
        status,
        [(axum::http::header::CONTENT_TYPE, "text/html; charset=utf-8")],
        html,
    )
        .into_response()
}

fn form_html(
    lang: &str,
    locator: &str,
    problem: Option<&str>,
    fields: &[String],
    choices: &Value,
    typed: &Typed,
) -> String {
    let warn = problem
        .map(|p| format!("<p class=\"warn\">{}</p>", esc(p)))
        .unwrap_or_default();
    let (choice_selects, names_script) = choice_fields_html(lang, fields, choices, typed);
    // hub#1989: a refused attempt comes back with what was typed, as an attribute value — escaped.
    let value = |field: &str| {
        typed
            .get(field)
            .map(|v| format!(" value=\"{}\"", esc(v)))
            .unwrap_or_default()
    };
    format!(
        "<h1>{title}</h1><p>{intro}</p>{warn}\
<p class=\"loc\"><span>{loc_label}</span><code>{locator}</code></p>\
<form method=\"post\" action=\"{prefix}/{locator}?lang={lang}\">\
<label for=\"tax\">{tax}</label>\
<input id=\"tax\" name=\"customer_tax_id\"{tax_value} required autocomplete=\"off\" autocapitalize=\"characters\" spellcheck=\"false\">\
<label for=\"name\">{name}</label>\
<input id=\"name\" name=\"customer_name\"{name_value} required autocomplete=\"organization\">\
<label for=\"addr\">{address}</label>\
<input id=\"addr\" name=\"customer_address\"{address_value} autocomplete=\"street-address\">\
{choice_selects}\
<button type=\"submit\">{submit}</button>\
</form>{names_script}",
        title = esc(t(lang, "title")),
        intro = esc(t(lang, "intro")),
        loc_label = esc(t(lang, "locator")),
        locator = esc(locator),
        prefix = PUBLIC_PREFIX,
        tax = esc(t(lang, "taxId")),
        name = esc(t(lang, "name")),
        address = esc(t(lang, "address")),
        submit = esc(t(lang, "submit")),
        tax_value = value("customer_tax_id"),
        name_value = value("customer_name"),
        address_value = value("customer_address"),
    )
}

/// sales#335 — the fields a module offers answers for, as `<select>`s after the fixed inputs.
///
/// The core does not know what the answers mean: which countries a tax regime accepts, which
/// document kinds it has — that is the module's knowledge (hub#1407), sent in the claim as
/// `field_choices`. Only fields the claim lets the visitor fill are shown (an answer the door drops
/// would be worse than no question). The first option is the default. `names: "region"` marks a
/// select of ISO region codes the browser names ([`NAMES_SCRIPT`]); the second value says whether
/// the page needs that script.
fn choice_fields_html(
    lang: &str,
    fields: &[String],
    choices: &Value,
    typed: &Typed,
) -> (String, String) {
    let mut html = String::new();
    let mut wants_names = false;
    for field in fields {
        let Some(spec) = choices.get(field).filter(|c| c.is_object()) else {
            continue;
        };
        let Some(options) = spec.get("options").and_then(Value::as_array) else {
            continue;
        };
        let names = spec.get("names").and_then(Value::as_str) == Some("region");
        wants_names |= names;
        let id = format!("f-{}", esc(field));
        let value_of = |option: &Value| {
            option
                .as_str()
                .or_else(|| option.get("value").and_then(Value::as_str))
                .unwrap_or_default()
                .to_string()
        };
        // The option the visitor chose stays chosen on a retry (hub#1989) — if it is one of the
        // offered ones; otherwise the module's default (the first) is.
        let chosen = typed
            .get(field)
            .filter(|v| options.iter().any(|o| value_of(o) == **v))
            .cloned()
            .unwrap_or_else(|| options.first().map(value_of).unwrap_or_default());
        // One `selected` even if a module repeats a value.
        let first_with = |v: &str| options.iter().position(|o| value_of(o) == v).unwrap_or(0);
        let rendered: String = options
            .iter()
            .enumerate()
            .map(|(i, option)| {
                let value = option
                    .as_str()
                    .or_else(|| option.get("value").and_then(Value::as_str))
                    .unwrap_or_default();
                let label = option
                    .get("label")
                    .and_then(|l| localized(l, lang))
                    .unwrap_or(value);
                let selected = if value == chosen && i == first_with(value) {
                    " selected"
                } else {
                    ""
                };
                format!(
                    "<option value=\"{}\"{selected}>{}</option>",
                    esc(value),
                    esc(label)
                )
            })
            .collect();
        let label = spec
            .get("label")
            .and_then(|l| localized(l, lang))
            .unwrap_or(field);
        let data_names = if names { " data-names=\"region\"" } else { "" };
        html.push_str(&format!(
            "<label for=\"{id}\">{}</label>\
<select id=\"{id}\" name=\"{}\"{data_names}>{rendered}</select>",
            esc(label),
            esc(field),
        ));
    }
    let script = if wants_names {
        format!("<script src=\"{NAMES_SCRIPT_PATH}\" defer></script>")
    } else {
        String::new()
    };
    (html, script)
}

/// A module-sent `{en, es}` label in the page's language, English when that one is missing.
fn localized<'a>(label: &'a Value, lang: &str) -> Option<&'a str> {
    label
        .get(lang)
        .and_then(Value::as_str)
        .or_else(|| label.get("en").and_then(Value::as_str))
        .filter(|s| !s.is_empty())
}

/// What the visitor typed, by field name (hub#1989).
type Typed = std::collections::BTreeMap<String, String>;

/// The one script the page may load, same-origin because `script-src 'self'` drops anything
/// inline. It only puts names on the country codes; the form works without it.
pub const NAMES_SCRIPT_PATH: &str = "/p/-/country-names.js";
const NAMES_SCRIPT: &str = include_str!("../assets/public-claim-names.js");

/// `GET /p/-/country-names.js` — public like the page that loads it.
pub async fn names_script() -> Response {
    (
        StatusCode::OK,
        [
            (
                axum::http::header::CONTENT_TYPE,
                "text/javascript; charset=utf-8",
            ),
            (axum::http::header::CACHE_CONTROL, "public, max-age=86400"),
        ],
        NAMES_SCRIPT,
    )
        .into_response()
}

const STYLE: &str = "\
:root{color-scheme:light dark}\
*{box-sizing:border-box}\
body{margin:0;font:16px/1.5 system-ui,-apple-system,'Segoe UI',sans-serif;background:#f6f7f9;color:#16202b}\
main{max-width:32rem;margin:0 auto;padding:2rem 1.25rem}\
h1{font-size:1.5rem;margin:0 0 .5rem}\
p{margin:0 0 1rem}\
.loc,.ref{display:flex;justify-content:space-between;gap:1rem;padding:.75rem 1rem;background:#fff;border:1px solid #dde2e8;border-radius:.5rem}\
.loc code,.ref strong{font-family:ui-monospace,monospace;letter-spacing:.08em}\
.warn{padding:.75rem 1rem;background:#fff4e5;border:1px solid #f0c48a;border-radius:.5rem}\
form{display:flex;flex-direction:column;gap:.35rem;margin-top:1.5rem}\
label{font-weight:600;font-size:.9rem;margin-top:.75rem}\
input,select{padding:.7rem .8rem;font:inherit;border:1px solid #c6cdd6;border-radius:.5rem;background:#fff;color:inherit}\
button{margin-top:1.5rem;padding:.85rem 1rem;font:inherit;font-weight:600;color:#fff;background:#1f5fd8;border:0;border-radius:.5rem;cursor:pointer}\
@media (prefers-color-scheme:dark){\
body{background:#11161c;color:#e6ebf2}\
.loc,.ref,input,select{background:#1b222b;border-color:#2f3945}\
.warn{background:#3a2a12;border-color:#7a5a22}}";

#[cfg(test)]
mod tests {
    use super::*;

    /// The page must not carry a `<script>` of any kind. Under `script-src 'self'` an inline one
    /// is silently dropped, so a page that depended on it would look fine in review and be broken
    /// on the customer's phone.
    #[test]
    fn the_page_carries_no_script_at_all() {
        let rendered = form_html(
            "es",
            "ABCD1234ABCD1234",
            None,
            &[],
            &json!({}),
            &Typed::new(),
        );
        assert!(!rendered.contains("<script"));
        assert!(!rendered.contains("onclick"));
        assert!(!rendered.contains("javascript:"));
    }

    /// The locator comes off a URL a stranger typed; it reaches the page as text, never as markup.
    #[test]
    fn a_locator_cannot_inject_markup_into_the_page() {
        let rendered = form_html(
            "es",
            "<img src=x onerror=alert(1)>",
            None,
            &[],
            &json!({}),
            &Typed::new(),
        );
        assert!(!rendered.contains("<img"));
        assert!(rendered.contains("&lt;img"));
    }

    fn claim_fields() -> Vec<String> {
        vec![
            "customer_tax_id".into(),
            "customer_name".into(),
            "customer_address".into(),
            "customer_country".into(),
            "customer_id_type".into(),
        ]
    }

    /// What a module sends (sales#335): the answers IT knows a field accepts. The core has no
    /// idea these are countries or document kinds — and must not (hub#1407).
    fn module_choices() -> Value {
        json!({
            "customer_country": {
                "label": {"en": "Country", "es": "País"},
                "names": "region",
                "options": [{"value": "", "label": {"en": "Home", "es": "Casa"}}, "US", "DE"],
            },
            "customer_id_type": {
                "label": {"en": "Your number is", "es": "Tu número es"},
                "options": [
                    {"value": "", "label": {"en": "A tax number", "es": "Un NIF"}},
                    {"value": "03", "label": {"en": "A passport", "es": "Un pasaporte"}},
                ],
            },
        })
    }

    /// A declared field with choices becomes a `<select>` in the page's language; the first option
    /// is the default; an option with no label shows its value.
    #[test]
    fn a_field_the_module_offers_choices_for_becomes_a_select() {
        let es = form_html(
            "es",
            "ABCD1234ABCD1234",
            None,
            &claim_fields(),
            &module_choices(),
            &Typed::new(),
        );
        assert!(
            es.contains("<label for=\"f-customer_country\">País</label>"),
            "{es}"
        );
        assert!(
            es.contains("<select id=\"f-customer_country\" name=\"customer_country\" data-names=\"region\">"),
            "{es}"
        );
        assert!(
            es.contains("<option value=\"\" selected>Casa</option>"),
            "{es}"
        );
        assert!(es.contains("<option value=\"US\">US</option>"), "{es}");
        assert!(
            es.contains("<select id=\"f-customer_id_type\" name=\"customer_id_type\">"),
            "{es}"
        );
        assert!(
            es.contains("<option value=\"03\">Un pasaporte</option>"),
            "{es}"
        );
        let en = form_html(
            "en",
            "ABCD1234ABCD1234",
            None,
            &claim_fields(),
            &module_choices(),
            &Typed::new(),
        );
        assert!(
            en.contains(">Country</label>") && en.contains(">A passport</option>"),
            "{en}"
        );
    }

    /// A label the module did not translate falls back to English, then to the field's own name —
    /// never an empty label.
    #[test]
    fn an_untranslated_label_falls_back_to_english_then_to_the_name() {
        let choices = json!({
            "customer_country": {"label": {"en": "Country"}, "options": ["US"]},
            "customer_id_type": {"options": [{"value": "03", "label": {"en": "A passport"}}]},
        });
        let es = form_html(
            "es",
            "ABCD1234ABCD1234",
            None,
            &claim_fields(),
            &choices,
            &Typed::new(),
        );
        assert!(es.contains(">Country</label>"), "{es}");
        assert!(es.contains(">customer_id_type</label>"), "{es}");
        assert!(
            es.contains("<option value=\"03\" selected>A passport</option>"),
            "{es}"
        );
    }

    /// Choices for a field the claim does not let the visitor fill are not shown: the door would
    /// drop the answer, so the customer would pick «United States» and get a Spanish NIF. And a
    /// claim with no choices — every ticket printed before sales#335 — keeps the old form.
    #[test]
    fn choices_only_show_for_declared_fields() {
        let old: Vec<String> = vec![
            "customer_tax_id".into(),
            "customer_name".into(),
            "customer_address".into(),
        ];
        let rendered = form_html(
            "es",
            "ABCD1234ABCD1234",
            None,
            &old,
            &module_choices(),
            &Typed::new(),
        );
        assert!(!rendered.contains("<select"), "{rendered}");
        assert!(!rendered.contains("<script"), "{rendered}");
        let plain = form_html(
            "es",
            "ABCD1234ABCD1234",
            None,
            &claim_fields(),
            &json!({}),
            &Typed::new(),
        );
        assert!(!plain.contains("<select"), "{plain}");
    }

    /// Labels and values are the module's, but they reach a stranger's page: text, never markup.
    #[test]
    fn choices_cannot_inject_markup_into_the_page() {
        let choices = json!({
            "customer_country": {
                "label": {"es": "<b>x</b>"},
                "options": ["\"><script>alert(1)</script>", {"value": "a", "label": {"es": "<img src=x>"}}],
            }
        });
        let rendered = form_html(
            "es",
            "ABCD1234ABCD1234",
            None,
            &claim_fields(),
            &choices,
            &Typed::new(),
        );
        assert!(!rendered.contains("<script>alert"), "{rendered}");
        assert!(
            !rendered.contains("<img") && !rendered.contains("<b>"),
            "{rendered}"
        );
    }

    /// Names for region codes come from the customer's own browser (`Intl.DisplayNames`), through
    /// ONE same-origin file, loaded only when a select asks for it. Nothing inline.
    #[test]
    fn region_names_come_from_one_same_origin_script() {
        let rendered = form_html(
            "es",
            "ABCD1234ABCD1234",
            None,
            &claim_fields(),
            &module_choices(),
            &Typed::new(),
        );
        assert_eq!(rendered.matches("<script").count(), 1, "{rendered}");
        assert!(rendered.contains(&format!(
            "<script src=\"{NAMES_SCRIPT_PATH}\" defer></script>"
        )));
        assert!(NAMES_SCRIPT_PATH.starts_with("/p/") && is_public_path(NAMES_SCRIPT_PATH));
        assert!(!rendered.contains("onclick") && !rendered.contains("onchange"));
        assert!(NAMES_SCRIPT.contains("Intl.DisplayNames"));
        let mut no_region = module_choices();
        no_region["customer_country"]
            .as_object_mut()
            .unwrap()
            .remove("names");
        let rendered = form_html(
            "es",
            "ABCD1234ABCD1234",
            None,
            &claim_fields(),
            &no_region,
            &Typed::new(),
        );
        assert!(!rendered.contains("<script"), "{rendered}");
    }

    /// A claim is a row per printed ticket: only choices for fields the visitor may fill are
    /// kept (the page would never show the rest), each list is capped, and a malformed map is a
    /// refusal rather than something stored half-read.
    #[test]
    fn minted_choices_keep_only_declared_fields_within_the_cap() {
        let fields = vec!["customer_country".to_string()];
        let raw = json!({
            "customer_country": {"options": ["US"]},
            "sealed_thing": {"options": ["x"]},
        });
        assert_eq!(
            accepted_choices(&raw, &fields),
            Some(json!({"customer_country": {"options": ["US"]}}))
        );
        assert_eq!(accepted_choices(&Value::Null, &fields), Some(json!({})));
        let too_many: Vec<Value> = (0..=MAX_CHOICE_OPTIONS)
            .map(|i| json!(i.to_string()))
            .collect();
        assert_eq!(
            accepted_choices(&json!({"customer_country": {"options": too_many}}), &fields),
            None
        );
        assert_eq!(accepted_choices(&json!(["US"]), &fields), None);
        assert_eq!(
            accepted_choices(&json!({"customer_country": "US"}), &fields),
            None
        );
    }

    /// hub#1989 — on a retry the chosen option stays chosen; a value the module never offered
    /// (a tampered POST) leaves the module's default explicitly selected, never no selection.
    #[test]
    fn a_retry_keeps_the_chosen_option_and_ignores_one_never_offered() {
        let mut typed = Typed::new();
        typed.insert("customer_country".into(), "DE".into());
        let kept = form_html(
            "es",
            "ABCD1234ABCD1234",
            None,
            &claim_fields(),
            &module_choices(),
            &typed,
        );
        assert!(
            kept.contains("<option value=\"DE\" selected>DE</option>"),
            "{kept}"
        );
        assert!(kept.contains("<option value=\"\">Casa</option>"), "{kept}");
        typed.insert("customer_country".into(), "ZZ".into());
        let tampered = form_html(
            "es",
            "ABCD1234ABCD1234",
            None,
            &claim_fields(),
            &module_choices(),
            &typed,
        );
        assert!(
            tampered.contains("<option value=\"\" selected>Casa</option>"),
            "{tampered}"
        );
        assert!(!tampered.contains("ZZ"), "{tampered}");
    }

    /// hub#1989 — the three text fields come back on a retry, the address included (the issue
    /// names it and nothing else asked for it), each one as an attribute value, never as markup.
    #[test]
    fn a_retry_keeps_the_address_and_the_rest_as_attribute_text() {
        let mut typed = Typed::new();
        typed.insert("customer_tax_id".into(), "B1234567X".into());
        typed.insert("customer_name".into(), "Bar \"Pepe\" & Co".into());
        typed.insert("customer_address".into(), "Calle Mayor 1 <b>2º</b>".into());
        let kept = form_html(
            "es",
            "ABCD1234ABCD1234",
            None,
            &claim_fields(),
            &module_choices(),
            &typed,
        );
        assert!(
            kept.contains("name=\"customer_tax_id\" value=\"B1234567X\""),
            "{kept}"
        );
        assert!(
            kept.contains("name=\"customer_name\" value=\"Bar &quot;Pepe&quot; &amp; Co\""),
            "{kept}"
        );
        assert!(
            kept.contains(
                "name=\"customer_address\" value=\"Calle Mayor 1 &lt;b&gt;2º&lt;/b&gt;\""
            ),
            "{kept}"
        );
        assert!(!kept.contains("<b>"), "{kept}");
    }

    /// hub#1989 — a module that repeats a value gets exactly one `selected`, on the first copy.
    #[test]
    fn a_repeated_option_value_is_selected_once() {
        let choices = json!({
            "customer_country": {"options": ["ES", "DE", "DE"]},
        });
        let mut typed = Typed::new();
        typed.insert("customer_country".into(), "DE".into());
        let kept = form_html(
            "es",
            "ABCD1234ABCD1234",
            None,
            &claim_fields(),
            &choices,
            &typed,
        );
        assert_eq!(kept.matches(" selected").count(), 1, "{kept}");
        assert!(
            kept.contains("<option value=\"ES\">ES</option><option value=\"DE\" selected>DE</option><option value=\"DE\">DE</option>"),
            "{kept}"
        );
    }

    /// Both languages, and the customer's page is the Spanish one by default — the merchant's
    /// customer never chose a locale anywhere.
    #[test]
    fn every_string_exists_in_both_languages() {
        for key in [
            "title",
            "intro",
            "taxId",
            "name",
            "address",
            "submit",
            "doneTitle",
            "doneBody",
            "unknown",
            "expired",
            "tooMany",
            "oops",
            "rejected",
            "unavailable",
            "locator",
            "reference",
        ] {
            let en = t("en", key);
            let es = t("es", key);
            assert!(!en.is_empty(), "missing English for `{key}`");
            assert!(!es.is_empty(), "missing Spanish for `{key}`");
            assert_ne!(en, es, "`{key}` was never translated");
        }
    }

    /// The two messages that carry a value must keep their placeholder, or the customer is told
    /// the deadline ended on `{date}`.
    #[test]
    fn the_messages_with_a_value_keep_their_placeholder() {
        for lang in ["en", "es"] {
            assert!(t(lang, "expired").contains("{date}"));
            assert!(t(lang, "tooMany").contains("{secs}"));
        }
    }

    /// Behind a proxy the guard counts per client, so one guest mistyping does not lock the
    /// restaurant out; with no proxy header it falls back to the locator rather than lumping every
    /// visitor into one bucket.
    ///
    /// 🔴 And it reads the **last** hop. A client can start the list itself, so trusting the first
    /// entry hands an attacker a fresh counter on every request — the throttle would be decorative.
    #[test]
    fn the_throttle_counts_the_hop_the_client_could_not_forge() {
        let mut headers = HeaderMap::new();
        // What an attacker sends (`198.51.100.9`) followed by what the proxy actually saw.
        headers.insert(
            "x-forwarded-for",
            "198.51.100.9, 203.0.113.7".parse().unwrap(),
        );
        assert_eq!(
            throttle_key(&headers, "ABCD1234ABCD1234"),
            "public-claim:ip:203.0.113.7",
            "the forged first hop must not open a new bucket"
        );
        assert_eq!(
            throttle_key(&HeaderMap::new(), "abcd1234abcd1234"),
            "public-claim:loc:ABCD1234ABCD1234"
        );
    }

    /// Only `/p` and below is public. A prefix that also matched `/print` or `/pos` would open
    /// doors this issue never asked for.
    #[test]
    fn only_the_public_prefix_is_public() {
        assert!(is_public_path("/p"));
        assert!(is_public_path("/p/ABCD1234ABCD1234"));
        assert!(!is_public_path("/print"));
        assert!(!is_public_path("/pos"));
        assert!(!is_public_path("/api/command"));
    }

    /// The reference shown to the customer is whatever the module called its document number,
    /// and nothing at all when it named none — never `null` on the page.
    #[test]
    fn the_reference_reads_whatever_the_module_called_its_number() {
        assert_eq!(
            reference_of(&json!({"number": "FACT-2026-000012"})),
            "FACT-2026-000012"
        );
        assert_eq!(reference_of(&json!({"invoice_id": "abc"})), "abc");
        assert_eq!(reference_of(&json!({"number": ""})), "");
        assert_eq!(reference_of(&json!({})), "");
    }
}
