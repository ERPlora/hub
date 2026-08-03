//! Real `host.notify` email transport: managed/OAuth via SaaS, custom SMTP direct.

use std::time::Duration;

use async_trait::async_trait;
use erplora_runtime::email_channel::{self, EmailConnection, EmailMode, SmtpSecurity};
use erplora_runtime::host_notify::{
    Channel, MaterializedArtifact, NotifyIntent, NotifyTransport, Routing, SendOutcome,
};
use erplora_runtime::{Result, RuntimeError};
use lettre::message::{header::ContentType, Attachment, Mailbox, MultiPart, SinglePart};
use lettre::transport::smtp::authentication::Credentials;
use lettre::{AsyncSmtpTransport, AsyncTransport, Message, Tokio1Executor};
use serde::Deserialize;
use serde_json::{json, Value as Json};

use crate::state::MachineToken;

#[derive(Debug, Clone, Deserialize)]
struct CloudArtifact {
    id: String,
    filename: String,
    content_type: String,
    download_url: String,
    #[serde(default)]
    share_url: String,
}

impl From<&CloudArtifact> for MaterializedArtifact {
    fn from(value: &CloudArtifact) -> Self {
        Self {
            id: value.id.clone(),
            filename: value.filename.clone(),
            content_type: value.content_type.clone(),
            download_url: value.download_url.clone(),
            share_url: value.share_url.clone(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct EmailNotifyTransport {
    http: reqwest::Client,
    cloud: cloud_client::CloudClient,
    machine_token: MachineToken,
}

impl EmailNotifyTransport {
    pub fn new(
        http: reqwest::Client,
        cloud_base_url: impl Into<String>,
        machine_token: MachineToken,
    ) -> Self {
        Self {
            http,
            cloud: cloud_client::CloudClient::new(cloud_base_url),
            machine_token,
        }
    }

    fn auth(&self, hub_id: &str) -> Result<cloud_client::Auth> {
        let token = self
            .machine_token
            .read()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .clone()
            .filter(|value| !value.trim().is_empty())
            .ok_or_else(|| {
                RuntimeError::Notify(
                    "el relay/OAuth requiere que el Hub esté enrolado en el SaaS".into(),
                )
            })?;
        Ok(cloud_client::Auth::HubToken {
            hub_id: hub_id.to_string(),
            token,
        })
    }

    fn request(&self, prepared: cloud_client::PreparedRequest) -> reqwest::RequestBuilder {
        let mut request = match prepared.method {
            "GET" => self.http.get(prepared.url),
            "DELETE" => self.http.delete(prepared.url),
            _ => self.http.post(prepared.url),
        };
        for (name, value) in prepared.headers {
            request = request.header(name, value);
        }
        request
    }

    async fn cloud_error(response: reqwest::Response, context: &str) -> RuntimeError {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        let detail = serde_json::from_str::<Json>(&body)
            .ok()
            .and_then(|value| {
                value
                    .get("error")
                    .and_then(Json::as_str)
                    .map(str::to_string)
            })
            .unwrap_or_else(|| format!("HTTP {status}"));
        RuntimeError::Notify(format!("{context}: {detail}"))
    }

    async fn materialize_document(
        &self,
        hub_id: &str,
        source_module: &str,
        intent: &NotifyIntent,
    ) -> Result<Option<CloudArtifact>> {
        let auth = self.auth(hub_id)?;
        if let Some(document) = &intent.document {
            let prepared = self.cloud.create_artifact(&auth);
            let response = self
                .request(prepared)
                .json(&json!({
                    "source_module": source_module,
                    "external_id": intent.correlation_id,
                    "idempotency_key": format!("{}:artifact", intent.idempotency_key),
                    "filename": document.filename,
                    "html": document.html,
                    "share": document.share,
                }))
                .send()
                .await
                .map_err(|e| RuntimeError::Notify(format!("materializando documento: {e}")))?;
            if !response.status().is_success() {
                return Err(Self::cloud_error(response, "materializando documento").await);
            }
            return response
                .json::<CloudArtifact>()
                .await
                .map(Some)
                .map_err(|e| {
                    RuntimeError::Notify(format!("respuesta de artefacto inválida: {e}"))
                });
        }
        let Some(reference) = intent.artifact_refs.first() else {
            return Ok(None);
        };
        let prepared = self.cloud.artifact(&reference.id, &auth);
        let response = self
            .request(prepared)
            .send()
            .await
            .map_err(|e| RuntimeError::Notify(format!("obteniendo artefacto: {e}")))?;
        if !response.status().is_success() {
            return Err(Self::cloud_error(response, "obteniendo artefacto").await);
        }
        response
            .json::<CloudArtifact>()
            .await
            .map(Some)
            .map_err(|e| RuntimeError::Notify(format!("respuesta de artefacto inválida: {e}")))
    }

    async fn send_cloud_email(
        &self,
        hub_id: &str,
        source_module: &str,
        config: &EmailConnection,
        intent: &NotifyIntent,
        artifact: Option<&CloudArtifact>,
    ) -> Result<SendOutcome> {
        let auth = self.auth(hub_id)?;
        let prepared = self.cloud.notify_email(&auth);
        let body_text = intent
            .vars
            .get("text")
            .and_then(Json::as_str)
            .unwrap_or("Documento adjunto.");
        let body_html = intent
            .vars
            .get("html")
            .and_then(Json::as_str)
            .unwrap_or_default();
        let response = self
            .request(prepared)
            .json(&json!({
                "provider_mode": match config.mode {
                    EmailMode::Managed => "managed",
                    EmailMode::GoogleOauth => "google_oauth",
                    EmailMode::MicrosoftOauth => "microsoft_oauth",
                    EmailMode::Smtp => "smtp",
                },
                "oauth_connection_id": config.oauth_connection_id,
                "source_module": source_module,
                "recipient_ref": intent.recipient_ref,
                "to": intent.resolved_to()?,
                "subject": intent.subject,
                "text": body_text,
                "html": body_html,
                "reply_to": config.reply_to,
                "idempotency_key": intent.idempotency_key,
                "artifact_id": artifact.map(|value| value.id.as_str()),
            }))
            .send()
            .await
            .map_err(|e| RuntimeError::Notify(format!("enviando email por SaaS: {e}")))?;
        if !response.status().is_success() {
            return Err(Self::cloud_error(response, "enviando email por SaaS").await);
        }
        Ok(SendOutcome::Sent {
            artifact: artifact.map(MaterializedArtifact::from),
        })
    }

    async fn send_smtp(
        &self,
        config: &EmailConnection,
        intent: &NotifyIntent,
        artifact: Option<&CloudArtifact>,
    ) -> Result<SendOutcome> {
        let from_address = config
            .from_email
            .parse()
            .map_err(|e| RuntimeError::Notify(format!("remitente SMTP inválido: {e}")))?;
        let to_address = intent
            .resolved_to()?
            .parse()
            .map_err(|e| RuntimeError::Notify(format!("destinatario SMTP inválido: {e}")))?;
        let mut builder = Message::builder()
            .from(Mailbox::new(
                (!config.from_name.is_empty()).then(|| config.from_name.clone()),
                from_address,
            ))
            .to(Mailbox::new(None, to_address))
            .subject(&intent.subject)
            .header(lettre::message::header::MessageId::from(format!(
                "<{}@hub.erplora>",
                intent.idempotency_key.replace(['<', '>', '@', ' '], "-")
            )));
        if !config.reply_to.is_empty() {
            let reply = config
                .reply_to
                .parse()
                .map_err(|e| RuntimeError::Notify(format!("Reply-To SMTP inválido: {e}")))?;
            builder = builder.reply_to(Mailbox::new(None, reply));
        }
        let text = intent
            .vars
            .get("text")
            .and_then(Json::as_str)
            .unwrap_or("Documento adjunto.")
            .to_string();
        let html = intent
            .vars
            .get("html")
            .and_then(Json::as_str)
            .unwrap_or_default()
            .to_string();
        let alternative = if html.is_empty() {
            MultiPart::alternative().singlepart(SinglePart::plain(text))
        } else {
            MultiPart::alternative()
                .singlepart(SinglePart::plain(text))
                .singlepart(SinglePart::html(html))
        };
        let message = if let Some(artifact) = artifact {
            let bytes = self
                .http
                .get(&artifact.download_url)
                .send()
                .await
                .map_err(|e| RuntimeError::Notify(format!("descargando adjunto: {e}")))?
                .error_for_status()
                .map_err(|e| RuntimeError::Notify(format!("descargando adjunto: {e}")))?
                .bytes()
                .await
                .map_err(|e| RuntimeError::Notify(format!("leyendo adjunto: {e}")))?;
            if bytes.len() > 20 * 1024 * 1024 {
                return Err(RuntimeError::Notify("el adjunto supera 20 MB".into()));
            }
            let content_type = ContentType::parse(&artifact.content_type)
                .unwrap_or(ContentType::parse("application/pdf").expect("MIME PDF válido"));
            builder
                .multipart(MultiPart::mixed().multipart(alternative).singlepart(
                    Attachment::new(artifact.filename.clone()).body(bytes.to_vec(), content_type),
                ))
                .map_err(|e| RuntimeError::Notify(format!("construyendo email SMTP: {e}")))?
        } else {
            builder
                .multipart(alternative)
                .map_err(|e| RuntimeError::Notify(format!("construyendo email SMTP: {e}")))?
        };

        let credentials = Credentials::new(config.username.clone(), config.password.clone());
        let mut transport = match config.security {
            SmtpSecurity::Tls => AsyncSmtpTransport::<Tokio1Executor>::relay(&config.host),
            SmtpSecurity::Starttls => {
                AsyncSmtpTransport::<Tokio1Executor>::starttls_relay(&config.host)
            }
            SmtpSecurity::None => Ok(AsyncSmtpTransport::<Tokio1Executor>::builder_dangerous(
                &config.host,
            )),
        }
        .map_err(|e| RuntimeError::Notify(format!("configurando SMTP: {e}")))?
        .port(config.port)
        .timeout(Some(Duration::from_secs(20)));
        if !config.username.is_empty() {
            transport = transport.credentials(credentials);
        }
        transport
            .build()
            .send(message)
            .await
            .map_err(|e| RuntimeError::Notify(format!("SMTP: {e}")))?;
        Ok(SendOutcome::Sent {
            artifact: artifact.map(MaterializedArtifact::from),
        })
    }

    pub async fn send_test(
        &self,
        db: &dyn erplora_db::DatabaseAdapter,
        hub_id: &str,
        recipient: &str,
    ) -> Result<SendOutcome> {
        let nonce = uuid::Uuid::new_v4().to_string();
        let intent = NotifyIntent {
            channel: Channel::Email,
            to: Some(recipient.to_string()),
            recipient_ref: Some(erplora_runtime::host_notify::RecipientRef {
                resolver: "core.admin".into(),
                id: recipient.to_string(),
            }),
            template: "core.email_test".into(),
            subject: "Prueba de correo de ERPlora".into(),
            vars: json!({
                "text": "La configuración de correo funciona correctamente.",
                "html": "<p>La configuración de correo funciona correctamente.</p>"
            }),
            artifact_refs: vec![],
            document: None,
            correlation_id: nonce.clone(),
            idempotency_key: format!("core-email-test:{nonce}"),
        };
        self.send(db, hub_id, "core", &intent, Routing::Tenant)
            .await
    }
}

#[async_trait]
impl NotifyTransport for EmailNotifyTransport {
    async fn send(
        &self,
        db: &dyn erplora_db::DatabaseAdapter,
        hub_id: &str,
        source_module: &str,
        intent: &NotifyIntent,
        _routing: Routing,
    ) -> Result<SendOutcome> {
        if intent.channel != Channel::Email {
            return Err(RuntimeError::Notify(format!(
                "el transporte de correo no implementa el canal {:?}",
                intent.channel
            )));
        }
        let config = email_channel::load(db, hub_id).await?;
        let artifact = self
            .materialize_document(hub_id, source_module, intent)
            .await?;
        match config.mode {
            EmailMode::Managed | EmailMode::GoogleOauth | EmailMode::MicrosoftOauth => {
                self.send_cloud_email(hub_id, source_module, &config, intent, artifact.as_ref())
                    .await
            }
            EmailMode::Smtp => self.send_smtp(&config, intent, artifact.as_ref()).await,
        }
    }
}
