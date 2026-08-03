//! Capacidad de host `host.notify(channel, payload)` (ADR-0012): envío externo de alto nivel
//! (`email`/`sms`/`whatsapp`) que el **runtime** ejecuta porque el WASM no tiene red.
//!
//! **Entrega vía Outbox (espejo de `outbox.rs`)**: un command de módulo NO envía inline. Emite
//! un evento `*.reminder.due` cuyo payload es la intención `{channel, to, template, vars}`; el
//! runtime registra un **listener-host** sintético sobre ese evento y el **relay** del outbox lo
//! entrega con reintentos/backoff/dead-letter **gratis** (la misma máquina ya probada). Aquí no
//! se reimplementan los reintentos: solo el cliente de cada canal + el routing del secreto.
//!
//! Routing del secreto por canal (ADR-0012, columna del humano — aquí solo se implementa):
//!  - **tenant** (SMTP propio, WhatsApp self-hosted) → secreto **local** cifrado del hub; el host
//!    llama directo, sin cuota ERPlora.
//!  - **WhatsApp premium de ERPlora** → la llamada sale **por el proxy de Cloud** (como los LLM);
//!    Cloud aplica `check_quota` (ADR-0006), inyecta el token de Meta y bloquea al agotar cuota.
//!
//! El **cliente real** (SMTP/SMS/HTTP) es una **decisión de dependencia del humano** (lettre,
//! reqwest…). Aquí se define el TRAIT [`NotifyTransport`] + un [`MockTransport`] que registra los
//! envíos en memoria, de modo que la mecánica Outbox (reintentos/dead-letter) queda real y
//! testeada. La integración real del transporte queda como TODO (ver más abajo).
//!
//! ## Las tres puertas antes de que salga nada del hub (hub#240)
//!
//! El listener-host se disparaba con **solo** ver un evento acabado en `.reminder.due`: ni
//! capability, ni canal, ni control del destinatario. Cualquier módulo con un handler alcanzaba
//! así email/SMS/WhatsApp con el `to` que quisiera (exfiltración + gasto). Hoy, `outbox.rs` exige
//! antes de llamar al transporte:
//!
//! 1. **Capability del módulo emisor** — `notify` declarada **y concedida**
//!    (`capabilities::require`, default-deny). El emisor se persiste por fila de outbox
//!    (`_event_outbox.module_id`): sin atribución no se autoriza a nadie.
//! 2. **Canal declarado** — [`assert_channel_declared`]: declarar `email` no habilita WhatsApp.
//! 3. **Destinatario resuelto desde datos del HUB** — [`assert_recipient_allowed`]: allowlist de
//!    `hub_settings` o email de un usuario del hub. Nunca una dirección libre del payload.
use std::sync::{Arc, Mutex};

use serde::{Deserialize, Serialize};
use serde_json::Value as Json;

use crate::errors::{Result, RuntimeError};

/// Canal de notificación de alto nivel. Conjunto **cerrado** (ADR-0012: añadir uno = tocar el
/// runtime). El módulo declara qué canal usa en `notify.channels` del manifest, NO dónde viven
/// los secretos/cuota.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Channel {
    Email,
    Sms,
    Whatsapp,
}

/// Referencia opaca a un contacto propiedad de un módulo. El módulo emisor solo conoce el id; el
/// runtime ejecuta el resolver declarado por el módulo propietario y obtiene la dirección final.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
pub struct RecipientRef {
    pub resolver: String,
    pub id: String,
}

/// Artefacto inmutable ya materializado por un módulo o por el servicio genérico de documentos.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
pub struct ArtifactRef {
    pub id: String,
    #[serde(default)]
    pub filename: String,
    #[serde(default)]
    pub content_type: String,
}

/// Documento HTML producido por el módulo para que el transporte lo convierta en un artefacto
/// PDF. El core lo trata como bytes opacos: no conoce facturas, tickets ni sus plantillas.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
pub struct DocumentSpec {
    pub filename: String,
    pub html: String,
    #[serde(default)]
    pub share: bool,
}

impl Channel {
    /// Parsea el nombre del canal (`email`/`sms`/`whatsapp`).
    pub fn parse(s: &str) -> Option<Channel> {
        match s {
            "email" => Some(Channel::Email),
            "sms" => Some(Channel::Sms),
            "whatsapp" => Some(Channel::Whatsapp),
            _ => None,
        }
    }
}

/// La intención de notificación que un command emite en el payload del evento `*.reminder.due`.
/// El módulo de negocio solo construye esto; el host resuelve el transporte y el secreto.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
pub struct NotifyIntent {
    pub channel: Channel,
    /// Destinatario final. Solo se admite en eventos legacy y debe estar en la allowlist; en los
    /// bindings nuevos el runtime lo rellena después de resolver `recipient_ref`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub to: Option<String>,
    /// Referencia segura al contacto, obligatoria en los eventos ligados por manifest.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub recipient_ref: Option<RecipientRef>,
    /// Plantilla a renderizar (el catálogo de plantillas lo resuelve el transporte/Cloud).
    pub template: String,
    /// Asunto opcional. El transporte rechaza caracteres de control antes de enviarlo.
    #[serde(default)]
    pub subject: String,
    /// Variables de la plantilla.
    #[serde(default)]
    pub vars: Json,
    /// Artefactos existentes que se adjuntan a la entrega.
    #[serde(default)]
    pub artifact_refs: Vec<ArtifactRef>,
    /// Documento nuevo producido por el módulo. El transporte puede renderizarlo una sola vez y
    /// reutilizar el artefacto resultante en email, descarga, QR o WhatsApp.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub document: Option<DocumentSpec>,
    #[serde(default)]
    pub correlation_id: String,
    #[serde(default)]
    pub idempotency_key: String,
}

impl NotifyIntent {
    /// Extrae la intención del payload de un evento `*.reminder.due`. `Err` si falta/!encaja.
    pub fn from_event_payload(payload: &erplora_db::Params) -> Result<NotifyIntent> {
        let value = Json::Object(payload.clone());
        serde_json::from_value(value).map_err(|e| RuntimeError::InvalidPayload {
            name: "host.notify".to_string(),
            detail: format!("intención de notificación inválida: {e}"),
        })
    }

    /// Construye una intención desde un evento ligado por manifest. Canal y plantilla salen del
    /// binding, nunca del payload. Un `to` libre es un error de contrato.
    pub fn from_bound_event_payload(
        payload: &erplora_db::Params,
        binding: &crate::manifest::NotificationBinding,
    ) -> Result<NotifyIntent> {
        if payload.contains_key("to") {
            return Err(RuntimeError::InvalidPayload {
                name: binding.event.clone(),
                detail: "un evento ligado no puede incluir `to`; usa `recipient_ref`".into(),
            });
        }
        let mut value = payload.clone();
        value.insert("channel".into(), Json::String(binding.channel.clone()));
        value.insert("template".into(), Json::String(binding.template.clone()));
        Self::from_event_payload(&value)
    }

    pub fn with_resolved_recipient(&self, to: String) -> NotifyIntent {
        let mut resolved = self.clone();
        resolved.to = Some(to);
        resolved
    }

    pub fn resolved_to(&self) -> Result<&str> {
        self.to
            .as_deref()
            .filter(|s| !s.trim().is_empty())
            .ok_or_else(|| {
                RuntimeError::Notify("la intención no tiene destinatario resuelto".into())
            })
    }
}

/// Clave de `hub_settings` con la **allowlist de destinatarios** que el dueño del hub autoriza
/// para `host.notify`. Lista separada por comas / saltos de línea. Es dato del HUB, no del módulo.
pub const ALLOWED_RECIPIENTS_SETTING: &str = "notify_allowed_recipients";

/// Longitud máxima de un destinatario (RFC 5321 para email; de sobra para E.164).
const MAX_RECIPIENT_LEN: usize = 254;

/// Valida la **forma** del destinatario para el canal (hub#240).
///
/// No autoriza nada por sí sola — solo corta lo que nunca puede ser un destinatario legítimo:
/// vacío, saltos de línea (inyección de cabeceras SMTP), varios destinatarios en un mismo `to`,
/// o un teléfono que no es E.164. La autorización real la da [`assert_recipient_allowed`].
fn check_recipient_syntax(channel: Channel, to: &str) -> Result<()> {
    let bad = |why: &str| {
        Err(RuntimeError::Notify(format!(
            "destinatario inválido para el canal {channel:?}: {why}"
        )))
    };
    let t = to.trim();
    if t.is_empty() {
        return bad("vacío");
    }
    if t.len() > MAX_RECIPIENT_LEN {
        return bad("demasiado largo");
    }
    if t.chars().any(|c| c.is_control()) {
        return bad("contiene caracteres de control (inyección de cabeceras)");
    }
    if t.contains(',') || t.contains(';') {
        return bad("solo se admite UN destinatario por notificación");
    }
    match channel {
        Channel::Email => {
            // Comprobación deliberadamente conservadora: un solo `@`, parte local no vacía y
            // dominio con punto. No pretende ser un parser de RFC 5322.
            let mut parts = t.split('@');
            let (Some(local), Some(domain), None) = (parts.next(), parts.next(), parts.next())
            else {
                return bad("no es una dirección de email");
            };
            if local.is_empty()
                || !domain.contains('.')
                || domain.starts_with('.')
                || domain.ends_with('.')
            {
                return bad("no es una dirección de email");
            }
            if t.chars().any(char::is_whitespace) {
                return bad("no es una dirección de email");
            }
        }
        Channel::Sms | Channel::Whatsapp => {
            // E.164: `+` seguido de 8..15 dígitos, sin separadores.
            let Some(digits) = t.strip_prefix('+') else {
                return bad("el teléfono debe ir en formato E.164 (`+34600000000`)");
            };
            if !(8..=15).contains(&digits.len()) || !digits.chars().all(|c| c.is_ascii_digit()) {
                return bad("el teléfono debe ir en formato E.164 (`+34600000000`)");
            }
        }
    }
    Ok(())
}

/// ¿Está `to` en la allowlist del hub? Comparación normalizada (trim + minúsculas) y separadores
/// flexibles (coma, punto y coma, espacios, saltos de línea): la lista la escribe una persona.
fn allowlist_contains(raw: &str, to: &str) -> bool {
    let needle = to.trim().to_ascii_lowercase();
    raw.split(|c: char| c == ',' || c == ';' || c.is_whitespace())
        .map(|s| s.trim().to_ascii_lowercase())
        .filter(|s| !s.is_empty())
        .any(|s| s == needle)
}

/// Exige que el **canal** esté declarado por el módulo emisor en `capabilities.notify.channels`
/// (o en el bloque `notify` deprecado). Declarar `email` no habilita mandar WhatsApp — que además
/// puede salir por el proxy de Cloud con cuota de pago. Default-deny: sin canales declarados, nada.
pub fn assert_channel_declared(
    registry: &crate::registry::Registry,
    module_id: &str,
    channel: Channel,
) -> Result<()> {
    let declared = registry
        .installed
        .iter()
        .find(|m| m.id == module_id)
        .map(|m| {
            let blocks = [m.capabilities.notify.as_ref(), m.notify.as_ref()];
            blocks
                .into_iter()
                .flatten()
                .flat_map(|n| n.channels.iter())
                .any(|c| Channel::parse(c.trim()) == Some(channel))
        })
        .unwrap_or(false);
    if declared {
        return Ok(());
    }
    Err(RuntimeError::CapabilityDenied {
        module: module_id.to_string(),
        capability: format!("notify:{}", channel_name(channel)),
    })
}

/// Nombre canónico del canal (para mensajes de error / UI).
fn channel_name(channel: Channel) -> &'static str {
    match channel {
        Channel::Email => "email",
        Channel::Sms => "sms",
        Channel::Whatsapp => "whatsapp",
    }
}

/// Exige que el destinatario **se resuelva desde datos del propio hub** (hub#240).
///
/// # Por qué
///
/// `to` llegaba tal cual desde el payload del handler: un módulo podía mandar "el recordatorio de
/// su cliente" a cualquier dirección del mundo. Con un transporte real conectado, eso es
/// exfiltración de datos del hub y gasto sin techo. El destinatario deja de ser un dato del módulo
/// y pasa a tener que existir en el hub:
///
///  1. estar en la **allowlist del dueño del hub** ([`ALLOWED_RECIPIENTS_SETTING`]), o
///  2. (canal email) ser el email de un **usuario del hub activo** (`hub_user`).
///
/// Cualquier otra cosa se rechaza. **Pendiente de decisión de producto**: cómo se autoriza el
/// contacto de un CLIENTE (los clientes viven en la tabla de un módulo, no en el core), que es lo
/// que hace falta para los recordatorios de cita reales. Hasta entonces, el operador los autoriza
/// explícitamente en la allowlist.
pub async fn assert_recipient_allowed(
    db: &dyn erplora_db::DatabaseAdapter,
    hub_id: &str,
    intent: &NotifyIntent,
) -> Result<()> {
    let to = intent.resolved_to()?.trim();
    check_recipient_syntax(intent.channel, to)?;

    // 1) Allowlist explícita del hub.
    let settings = crate::settings::get_all(db, hub_id)
        .await
        .unwrap_or(Json::Null);
    let raw = settings
        .get(ALLOWED_RECIPIENTS_SETTING)
        .and_then(|v| v.as_str())
        .unwrap_or_default();
    if allowlist_contains(raw, to) {
        return Ok(());
    }

    // 2) Email de un usuario del hub activo.
    if intent.channel == Channel::Email {
        let mut p = erplora_db::Params::new();
        p.insert("email".into(), serde_json::json!(to.to_ascii_lowercase()));
        let res = db
            .query(
                "SELECT id FROM hub_user WHERE LOWER(email) = :email AND is_active = 1",
                &p,
            )
            .await?;
        if !res.rows.is_empty() {
            return Ok(());
        }
    }

    Err(RuntimeError::Notify(format!(
        "destinatario `{to}` no resuelto desde datos del hub: añádelo a `{ALLOWED_RECIPIENTS_SETTING}` \
         en los ajustes del hub o usa el contacto de un usuario del hub (host.notify no acepta \
         destinatarios libres del payload de un módulo)"
    )))
}

/// Binding exacto declarado por `module_id` para `event_name`. El bloque consolidado de
/// `capabilities.notify` tiene precedencia sobre el alias top-level deprecado.
pub fn event_binding(
    registry: &crate::registry::Registry,
    module_id: &str,
    event_name: &str,
) -> Option<crate::manifest::NotificationBinding> {
    let manifest = registry.installed.iter().find(|m| m.id == module_id)?;
    let notify = manifest
        .capabilities
        .notify
        .as_ref()
        .or(manifest.notify.as_ref())?;
    notify
        .bindings
        .iter()
        .find(|b| b.event == event_name)
        .cloned()
}

/// Valida que el binding y la intención siguen siendo el mismo contrato después de parsear el
/// payload. Protege frente a manifests inconsistentes y a futuras rutas que construyan la
/// intención sin [`NotifyIntent::from_bound_event_payload`].
pub fn assert_binding_matches(
    binding: &crate::manifest::NotificationBinding,
    intent: &NotifyIntent,
) -> Result<()> {
    let Some(channel) = Channel::parse(binding.channel.trim()) else {
        return Err(RuntimeError::Notify(format!(
            "binding `{}` declara un canal desconocido `{}`",
            binding.event, binding.channel
        )));
    };
    if intent.channel != channel || intent.template != binding.template {
        return Err(RuntimeError::Notify(format!(
            "la intención no coincide con el binding `{}`",
            binding.event
        )));
    }
    let Some(reference) = &intent.recipient_ref else {
        return Err(RuntimeError::Notify(format!(
            "el evento ligado `{}` exige `recipient_ref`",
            binding.event
        )));
    };
    if reference.resolver != binding.recipient_resolver {
        return Err(RuntimeError::Notify(format!(
            "resolver `{}` no autorizado para `{}`; se esperaba `{}`",
            reference.resolver, binding.event, binding.recipient_resolver
        )));
    }
    if reference.id.trim().is_empty() || reference.id.len() > 254 {
        return Err(RuntimeError::Notify(
            "recipient_ref.id vacío o demasiado largo".into(),
        ));
    }
    if intent.idempotency_key.trim().is_empty() || intent.idempotency_key.len() > 255 {
        return Err(RuntimeError::Notify(format!(
            "el evento ligado `{}` exige `idempotency_key` (máximo 255 caracteres)",
            binding.event
        )));
    }
    if intent.correlation_id.len() > 255 {
        return Err(RuntimeError::Notify(
            "correlation_id supera 255 caracteres".into(),
        ));
    }
    validate_headers_and_document(intent)
}

fn validate_headers_and_document(intent: &NotifyIntent) -> Result<()> {
    if intent.subject.chars().any(char::is_control) {
        return Err(RuntimeError::Notify(
            "el asunto contiene caracteres de control (inyección de cabeceras)".into(),
        ));
    }
    if intent.subject.len() > 998 {
        return Err(RuntimeError::Notify("el asunto es demasiado largo".into()));
    }
    if let Some(document) = &intent.document {
        if document.filename.trim().is_empty()
            || document.filename.len() > 255
            || document.filename.contains('/')
            || document.filename.contains('\\')
            || document.filename.chars().any(char::is_control)
        {
            return Err(RuntimeError::Notify("nombre de documento inválido".into()));
        }
        if document.html.len() > 1_000_000 {
            return Err(RuntimeError::Notify(
                "el documento supera el máximo de 1 MB de HTML".into(),
            ));
        }
    }
    Ok(())
}

/// Resuelve `recipient_ref` mediante el contrato aportado por el módulo propietario del contacto.
/// `Ok(None)` significa que la referencia existe/no existe pero no tiene contacto para el canal:
/// es un skip de producto, no un fallo reintentable. Una dirección libre solo se conserva para el
/// camino legacy y sigue pasando por la allowlist de [`assert_recipient_allowed`].
pub async fn resolve_recipient(
    db: &dyn erplora_db::DatabaseAdapter,
    registry: &crate::registry::Registry,
    hub_id: &str,
    intent: &NotifyIntent,
    binding: Option<&crate::manifest::NotificationBinding>,
) -> Result<Option<String>> {
    let Some(reference) = &intent.recipient_ref else {
        assert_recipient_allowed(db, hub_id, intent).await?;
        return Ok(Some(intent.resolved_to()?.trim().to_string()));
    };
    let binding = binding.ok_or_else(|| {
        RuntimeError::Notify("recipient_ref solo se admite en eventos ligados por manifest".into())
    })?;
    assert_binding_matches(binding, intent)?;

    let mut providers = registry.installed.iter().filter(|manifest| {
        registry.is_active(&manifest.id)
            && manifest
                .notification_recipient_resolvers
                .contains_key(&reference.resolver)
    });
    // El módulo propietario del contacto es opcional: si no está instalado o activo, el negocio
    // sigue pudiendo emitir el documento y la entrega se registra como `skipped_missing_contact`.
    // La ausencia de un módulo no debe bloquear una venta ni convertir el outbox en dead-letter.
    let Some(provider) = providers.next() else {
        return Ok(None);
    };
    if providers.next().is_some() {
        return Err(RuntimeError::Notify(format!(
            "resolver de destinatario duplicado `{}`",
            reference.resolver
        )));
    }
    let resolver = &provider.notification_recipient_resolvers[&reference.resolver];
    let owner = resolver.query.split('.').next().unwrap_or_default();
    if owner != provider.id {
        return Err(RuntimeError::Notify(format!(
            "resolver `{}` intenta usar una query ajena `{}`",
            reference.resolver, resolver.query
        )));
    }
    let query = registry.get_query(&resolver.query).ok_or_else(|| {
        RuntimeError::Notify(format!(
            "query `{}` del resolver `{}` no disponible",
            resolver.query, reference.resolver
        ))
    })?;
    if query.module_id != provider.id {
        return Err(RuntimeError::Notify(format!(
            "query `{}` no pertenece al módulo proveedor `{}`",
            resolver.query, provider.id
        )));
    }
    let field = resolver
        .channels
        .get(channel_name(intent.channel))
        .filter(|f| !f.trim().is_empty())
        .ok_or_else(|| {
            RuntimeError::Notify(format!(
                "resolver `{}` no ofrece el canal {}",
                reference.resolver,
                channel_name(intent.channel)
            ))
        })?;
    let mut params = erplora_db::Params::new();
    params.insert(
        resolver.id_param.clone(),
        Json::String(reference.id.clone()),
    );
    // La resolución es una operación interna del host. La query sigue estando fijada por el
    // manifest del proveedor y recibe un único id; el contacto no se devuelve al módulo emisor.
    let ctx = crate::registry::RequestContext::new(
        hub_id,
        "system:notification-resolver",
        ["*".to_string()],
    );
    let rows = crate::queries::execute(db, registry, &resolver.query, &params, &ctx).await?;
    let Some(row) = rows.first() else {
        return Ok(None);
    };
    let Some(to) = row.get(field).and_then(Json::as_str).map(str::trim) else {
        return Ok(None);
    };
    if to.is_empty() {
        return Ok(None);
    }
    check_recipient_syntax(intent.channel, to)?;
    Ok(Some(to.to_string()))
}

/// De dónde sale el secreto/transporte de un canal (ADR-0012). Lo decide el host por canal y por
/// `tier` del módulo, no el módulo.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Routing {
    /// Secreto local cifrado del hub; el host llama directo (sin cuota ERPlora).
    Tenant,
    /// Proxy de Cloud con `check_quota` (WhatsApp premium de ERPlora).
    CloudProxy,
}

/// Resultado de un intento de envío. `Sent` = entregado al proveedor; `QuotaExceeded` = Cloud
/// bloqueó por cuota agotada (no se reintenta: el relay lo manda a dead-letter como fallo
/// terminal cuando el transporte lo marca así devolviendo `Err` con este detalle).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MaterializedArtifact {
    pub id: String,
    pub filename: String,
    pub content_type: String,
    pub download_url: String,
    #[serde(default)]
    pub share_url: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SendOutcome {
    Sent {
        artifact: Option<MaterializedArtifact>,
    },
}

/// Transporte de notificación: el cliente real de un canal. **Trait inyectable** para no atar el
/// runtime a una dependencia concreta de SMTP/SMS/HTTP (decisión del humano). El host elige el
/// `Routing` y llama aquí; un `Err` se traduce en reintento del relay (backoff) y, tras
/// `MAX_ATTEMPTS`, dead-letter — exactamente como un listener que falla.
#[async_trait::async_trait]
pub trait NotifyTransport: Send + Sync + std::fmt::Debug {
    /// Envía `intent` por `routing`. `Ok(SendOutcome::Sent)` si se entregó al proveedor; `Err`
    /// para que el relay reintente (fallo transitorio) o, si es terminal (cuota agotada / canal
    /// no configurado), lo registre como fallo (acabará en dead-letter tras los reintentos).
    async fn send(
        &self,
        db: &dyn erplora_db::DatabaseAdapter,
        hub_id: &str,
        source_module: &str,
        intent: &NotifyIntent,
        routing: Routing,
    ) -> Result<SendOutcome>;
}

/// Decide el routing de un canal según el `tier` del módulo (ADR-0012/ADR-0006). Hoy: WhatsApp en
/// un módulo `premium` de ERPlora sale por el proxy de Cloud (cuota); el resto (email/sms y
/// WhatsApp self-hosted del tenant) usa el secreto local. El `tier` lo conoce el host (no el
/// manifest del Hub: la clasificación vive en Cloud, ADR-0007) — se pasa como hint.
pub fn route_channel(channel: Channel, premium_whatsapp: bool) -> Routing {
    match channel {
        Channel::Whatsapp if premium_whatsapp => Routing::CloudProxy,
        _ => Routing::Tenant,
    }
}

/// Transporte **mock** para tests y arranque sin transporte real configurado: registra cada envío
/// en memoria y devuelve `Sent`. Permite probar la mecánica Outbox (reintentos/dead-letter) sin
/// red. La integración real (SMTP/SMS/WhatsApp) la conecta el host sustituyendo este transporte.
#[derive(Debug, Default, Clone)]
pub struct MockTransport {
    sent: Arc<Mutex<Vec<(NotifyIntent, Routing)>>>,
    /// Si `true`, `send` devuelve `Err` (para probar el camino de reintento/dead-letter del relay).
    fail: bool,
}

impl MockTransport {
    pub fn new() -> Self {
        Self::default()
    }

    /// Variante que siempre falla (para tests del backoff/dead-letter del relay).
    pub fn failing() -> Self {
        Self {
            sent: Arc::default(),
            fail: true,
        }
    }

    /// Envíos registrados (clon) — para aserciones en tests.
    pub fn sent(&self) -> Vec<(NotifyIntent, Routing)> {
        self.sent.lock().map(|g| g.clone()).unwrap_or_default()
    }
}

#[async_trait::async_trait]
impl NotifyTransport for MockTransport {
    async fn send(
        &self,
        _db: &dyn erplora_db::DatabaseAdapter,
        _hub_id: &str,
        _source_module: &str,
        intent: &NotifyIntent,
        routing: Routing,
    ) -> Result<SendOutcome> {
        if self.fail {
            return Err(RuntimeError::Notify(
                "transporte mock configurado para fallar".into(),
            ));
        }
        if let Ok(mut g) = self.sent.lock() {
            g.push((intent.clone(), routing));
        }
        Ok(SendOutcome::Sent { artifact: None })
    }
}

// ── TODO (decisión de dependencia del humano) ────────────────────────────────────────────────
// El transporte REAL requiere dependencias nuevas que son columna del humano:
//   - email  → `lettre` (SMTP) con el secreto SMTP local cifrado del hub.
//   - sms    → cliente HTTP (`reqwest`, ya en el workspace de server) al proveedor del tenant.
//   - whatsapp tenant   → Graph API de Meta (HTTP) con el token local cifrado del hub.
//   - whatsapp premium  → `erplora-cloud-client::notify_whatsapp` (proxy Cloud, check_quota).
// El cifrado del secreto local del hub debe seguir el patrón de ADR-0016 (Fernet/master key en
// env), igual que el PKCS#12 de verifactu. NO se inventa aquí: se deja el trait y el mock.

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::Params;
    use serde_json::json;

    fn intent_params(channel: &str) -> Params {
        let mut p = Params::new();
        p.insert("channel".into(), json!(channel));
        p.insert("to".into(), json!("a@b.com"));
        p.insert("template".into(), json!("appointment_reminder"));
        p.insert("vars".into(), json!({"when": "10:00"}));
        p
    }

    #[test]
    fn parses_intent_from_event_payload() {
        let intent = NotifyIntent::from_event_payload(&intent_params("email")).unwrap();
        assert_eq!(intent.channel, Channel::Email);
        assert_eq!(intent.to.as_deref(), Some("a@b.com"));
        assert_eq!(intent.template, "appointment_reminder");
    }

    #[test]
    fn rejects_unknown_channel() {
        let err = NotifyIntent::from_event_payload(&intent_params("carrier_pigeon")).unwrap_err();
        assert!(
            matches!(err, RuntimeError::InvalidPayload { .. }),
            "got {err:?}"
        );
    }

    #[test]
    fn routing_premium_whatsapp_goes_to_cloud() {
        assert_eq!(route_channel(Channel::Whatsapp, true), Routing::CloudProxy);
        assert_eq!(route_channel(Channel::Whatsapp, false), Routing::Tenant);
        assert_eq!(route_channel(Channel::Email, true), Routing::Tenant);
        assert_eq!(route_channel(Channel::Sms, true), Routing::Tenant);
    }

    // ── Destinatario y canal (hub#240) ───────────────────────────────────────────────────────
    //
    // `to` venía TAL CUAL del payload del handler: un módulo podía mandar el recordatorio de
    // "su" cliente a cualquier dirección/teléfono del mundo. Con `host.notify` conectado a un
    // transporte real eso es exfiltración de datos del hub + gasto sin techo. Ahora el
    // destinatario tiene que **resolverse desde datos del hub** y el canal tiene que estar
    // declarado por el módulo emisor.

    fn intent(channel: Channel, to: &str) -> NotifyIntent {
        NotifyIntent {
            channel,
            to: Some(to.to_string()),
            recipient_ref: None,
            template: "t".into(),
            subject: String::new(),
            vars: json!({}),
            artifact_refs: vec![],
            document: None,
            correlation_id: String::new(),
            idempotency_key: String::new(),
        }
    }

    #[test]
    fn recipient_syntax_rejects_injection_and_multiple_addresses() {
        // Salto de línea = inyección de cabeceras SMTP.
        assert!(check_recipient_syntax(Channel::Email, "a@b.com\r\nbcc: x@y.com").is_err());
        // Varios destinatarios en un solo `to`.
        assert!(check_recipient_syntax(Channel::Email, "a@b.com,c@d.com").is_err());
        assert!(check_recipient_syntax(Channel::Email, "a@b.com; c@d.com").is_err());
        // Vacío / sin arroba / sin dominio.
        assert!(check_recipient_syntax(Channel::Email, "").is_err());
        assert!(check_recipient_syntax(Channel::Email, "not-an-email").is_err());
        assert!(check_recipient_syntax(Channel::Email, "a@localhost").is_err());
        // Válido.
        check_recipient_syntax(Channel::Email, "cliente@ejemplo.com").unwrap();
    }

    #[test]
    fn phone_channels_require_e164() {
        check_recipient_syntax(Channel::Sms, "+34600000000").unwrap();
        check_recipient_syntax(Channel::Whatsapp, "+34600000000").unwrap();
        assert!(check_recipient_syntax(Channel::Sms, "600000000").is_err()); // sin prefijo
        assert!(check_recipient_syntax(Channel::Sms, "+34-600-000-000").is_err());
        assert!(check_recipient_syntax(Channel::Sms, "+1").is_err()); // demasiado corto
    }

    /// La allowlist del hub (`hub_settings.notify_allowed_recipients`) es texto libre del
    /// **dueño del hub**, no del módulo: separadores flexibles y comparación normalizada.
    #[test]
    fn allowlist_matching_is_normalized() {
        let list = "  Cliente@Ejemplo.com , +34600000000\n otro@x.es ";
        assert!(allowlist_contains(list, "cliente@ejemplo.com"));
        assert!(allowlist_contains(list, "+34600000000"));
        assert!(allowlist_contains(list, "OTRO@X.ES"));
        assert!(!allowlist_contains(list, "atacante@evil.com"));
        assert!(!allowlist_contains("", "cliente@ejemplo.com"));
    }

    /// El canal tiene que estar declarado por el módulo emisor: declarar `email` no habilita
    /// mandar WhatsApp (que además puede ir con cuota de pago).
    #[test]
    fn channel_must_be_declared_by_the_emitting_module() {
        use crate::registry::Registry;
        let mut reg = Registry::new();
        reg.installed.push(
            serde_json::from_str(
                r#"{"id":"appt","name":"Appointments","version":"1.0.0",
                    "capabilities":{"notify":{"channels":["email"]}}}"#,
            )
            .unwrap(),
        );
        assert_channel_declared(&reg, "appt", Channel::Email).unwrap();
        assert!(assert_channel_declared(&reg, "appt", Channel::Whatsapp).is_err());
        // Módulo que ni siquiera está instalado.
        assert!(assert_channel_declared(&reg, "otro", Channel::Email).is_err());
    }

    /// Un módulo que declara `notify` **sin** lista de canales no obtiene todos: sin canales
    /// declarados no puede enviar por ninguno (default-deny).
    #[test]
    fn notify_without_channels_declares_nothing() {
        use crate::registry::Registry;
        let mut reg = Registry::new();
        reg.installed.push(
            serde_json::from_str(
                r#"{"id":"appt","name":"Appointments","version":"1.0.0",
                    "capabilities":{"notify":{}}}"#,
            )
            .unwrap(),
        );
        assert!(assert_channel_declared(&reg, "appt", Channel::Email).is_err());
    }

    /// Puerta 3, camino 2: un email de un **usuario del hub activo** se resuelve desde datos
    /// del hub sin pasar por la allowlist (comparación insensible a mayúsculas); desactivar al
    /// usuario vuelve a cerrar la puerta, y un email de fuera nunca resuelve.
    #[tokio::test]
    async fn recipient_resolves_from_an_active_hub_user_email() {
        let db = erplora_db::testutil::fresh_db().await;
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        crate::system_migrations::apply(&db, "h1").await.unwrap();

        crate::identity::create_login_user(&db, "empleado@hub.com", "employee")
            .await
            .unwrap();
        assert_recipient_allowed(&db, "h1", &intent(Channel::Email, "Empleado@Hub.com"))
            .await
            .unwrap();

        // Un email que no es de nadie en el hub no resuelve (ni allowlist ni hub_user).
        assert!(
            assert_recipient_allowed(&db, "h1", &intent(Channel::Email, "atacante@evil.com"))
                .await
                .is_err()
        );
        // El mismo destinatario por SMS tampoco: el camino hub_user es SOLO email.
        assert!(
            assert_recipient_allowed(&db, "h1", &intent(Channel::Sms, "+34600000000"))
                .await
                .is_err()
        );

        // Baja del usuario → la puerta se cierra.
        crate::identity::deactivate_login_user(&db, "empleado@hub.com")
            .await
            .unwrap();
        assert!(
            assert_recipient_allowed(&db, "h1", &intent(Channel::Email, "empleado@hub.com"))
                .await
                .is_err()
        );
    }

    #[tokio::test]
    async fn mock_transport_records_send() {
        let db = erplora_db::testutil::fresh_db().await;
        let t = MockTransport::new();
        let intent = NotifyIntent::from_event_payload(&intent_params("sms")).unwrap();
        let out = t
            .send(&db, "h1", "appt", &intent, Routing::Tenant)
            .await
            .unwrap();
        assert_eq!(out, SendOutcome::Sent { artifact: None });
        assert_eq!(t.sent().len(), 1);
        assert_eq!(t.sent()[0].1, Routing::Tenant);
    }

    #[tokio::test]
    async fn failing_transport_errors() {
        let db = erplora_db::testutil::fresh_db().await;
        let t = MockTransport::failing();
        let intent = NotifyIntent::from_event_payload(&intent_params("email")).unwrap();
        assert!(t
            .send(&db, "h1", "appt", &intent, Routing::Tenant)
            .await
            .is_err());
    }
}
