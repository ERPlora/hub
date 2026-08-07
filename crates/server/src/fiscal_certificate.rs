//! Fetching ERPlora's DELEGATED fiscal certificate from the control plane (ADR-0202 §2 — hub#317).
//!
//! The SaaS custodies one `.p12` with which **ERPlora** identifies itself before the AEAT for every
//! hub that signed a power of attorney, and hands it down over
//! `GET /api/v1/hub/device/fiscal/certificate/` (saas#1125). This module is the hub half: it asks
//! for it with the machine credential, and stores it in the `delegated` slot of the core
//! (`erplora_runtime::certificate::set_delegated` — AES-GCM at rest, fail-closed).
//!
//! # This module handles somebody else's PRIVATE KEY
//!
//! Not the customer's: one leak compromises the whole fleet, not one business. Three rules hold it:
//!
//! 1. **Nothing of the container or the passphrase enters a log or an error string.** Errors here
//!    name the URL and the status code and stop there — the response BODY is never interpolated,
//!    not even when it fails to parse (that is exactly the body most likely to hold the key). The
//!    SaaS side does the same and drops `exc_info` on its decrypt branch for the same reason.
//! 2. **It never reaches the browser.** This runs in the runtime, with the `cloud_api_token`, and
//!    the value is stored — never proxied, unlike `cloud_json_passthrough`'s endpoints.
//! 3. **It never reaches disk in the clear**, nor a bundle: storage goes through the core's
//!    encrypted writer, and `certificate::exportable_der_bytes` keeps the slot out of every export.
//!
//! # What this module does NOT do (yet)
//!
//! It exposes the fetch; **it does not schedule it.** The three refetch triggers of ADR-0202 §2
//! point 4 (boot · heartbeat · TLS failure against the AEAT) are hub#318, and wiring the delegated
//! certificate into the module's `build_identity` is hub#319.

use cloud_client::{Auth, CloudClient, DelegatedCertificate};
use erplora_db::DatabaseAdapter;
use erplora_runtime::certificate;

/// What came of asking the control plane for a certificate.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DelegatedCertificateOutcome {
    /// Stored in the `delegated` slot, encrypted, under `version`. `not_after` is read back from the
    /// container that was actually stored, not copied from the response.
    Installed {
        version: i64,
        not_after: Option<String>,
    },
    /// **404 `no_delegated_certificate`** — the control plane has never uploaded one (`version == 0`
    /// on its side). A normal steady state, not a failure: most hubs use their own certificate and
    /// will never be handed one. The hub keeps whatever it has.
    NotProvisioned,
}

/// Asks the control plane for this hub's delegated certificate.
///
/// `Ok(None)` is the **404**: the SaaS has nothing to hand down. Any other non-2xx, a transport
/// failure or an unparseable body is an `Err`, and none of those error strings ever carries the
/// response body.
pub async fn fetch_delegated_certificate(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
) -> Result<Option<DelegatedCertificate>, String> {
    let req = CloudClient::new(cloud_base_url).fiscal_certificate(auth);
    let mut request = http.get(&req.url);
    for (name, value) in req.headers {
        request = request.header(name, value);
    }
    let response = request.send().await.map_err(|error| error.to_string())?;
    let status = response.status();
    // 404 = `no_delegated_certificate`: the control plane has nothing for this hub. An ANSWER, not a
    // fault — most hubs sign with their own certificate and will never be delegated one, so turning
    // this into an error would put a permanent red into the majority of the fleet. Every other
    // non-2xx IS a fault the caller has to see: 403 `hub_not_entitled`, 410 `hub_not_found`, a 5xx.
    if status == reqwest::StatusCode::NOT_FOUND {
        return Ok(None);
    }
    if !status.is_success() {
        return Err(format!("{}: status {status}", req.url));
    }
    let body = response.text().await.map_err(|error| error.to_string())?;
    // ⚠️ The body is NEVER interpolated into the error. This is the branch that most invites it —
    // «it did not parse, let me show you what came back» — and the thing that came back is a private
    // key and its passphrase. `serde_json::Error` carries only a reason plus a line/column, which is
    // enough to tell a truncated response from a changed contract.
    DelegatedCertificate::parse(&body)
        .map(Some)
        .map_err(|error| format!("{}: respuesta ilegible ({error})", req.url))
}

/// Fetches the delegated certificate and stores it, encrypted, in the core's `delegated` slot.
///
/// A 404 leaves the hub exactly as it was: a hub with its own certificate keeps signing with it, and
/// one with neither stays as unable to invoice as it already was. Never an error — «ERPlora has not
/// delegated anything to you» is an answer, not a fault.
pub async fn install_delegated_certificate(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &Auth,
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<DelegatedCertificateOutcome, String> {
    let Some(cert) = fetch_delegated_certificate(http, cloud_base_url, auth).await? else {
        return Ok(DelegatedCertificateOutcome::NotProvisioned);
    };
    certificate::set_delegated(db, hub_id, &cert.pkcs12_b64, &cert.password, cert.version)
        .await
        .map_err(|error| error.to_string())?;
    let not_after = certificate::expiry(db, hub_id).await.ok().flatten();
    Ok(DelegatedCertificateOutcome::Installed {
        version: cert.version,
        not_after,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::{HeaderMap, StatusCode};
    use axum::routing::get;
    use axum::Router;
    use erplora_db::testutil::fresh_db;
    use erplora_db::PgAdapter;
    use std::sync::{Arc, Mutex};

    /// A real `.p12` is not needed to prove where the bytes go: what matters is that this exact
    /// string never shows up anywhere it should not. Base64 of "DELEGATED-PKCS12".
    const DELEGATED_B64: &str = "REVMRUdBVEVELVBLQ1MxMg==";
    const DELEGATED_PASSWORD: &str = "erplora-delegated-passphrase";
    const OWN_B64: &str = "T1dOLVBLQ1MxMg==";

    fn served_body(version: i64) -> String {
        format!(
            r#"{{"version": {version}, "pkcs12_b64": "{DELEGATED_B64}", \
                 "password": "{DELEGATED_PASSWORD}", "not_after": "2028-06-10"}}"#
        )
        .replace('\\', "")
    }

    /// A cloud stub answering the fiscal-certificate endpoint with a fixed status and body, and
    /// recording the headers it was asked with. Returns `(base_url, captured_headers, shutdown)`.
    async fn cloud_stub(
        status: StatusCode,
        body: &'static str,
    ) -> (String, Arc<Mutex<Option<HeaderMap>>>, tokio::task::JoinHandle<()>) {
        type Seen = Arc<Mutex<Option<HeaderMap>>>;
        let seen: Seen = Arc::new(Mutex::new(None));
        let app = Router::new().route(
            "/api/v1/hub/device/fiscal/certificate/",
            get({
                let seen = seen.clone();
                move |headers: HeaderMap| {
                    *seen.lock().unwrap() = Some(headers);
                    async move { (status, body) }
                }
            }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        (format!("http://{address}"), seen, server)
    }

    fn machine_auth() -> Auth {
        Auth::HubToken {
            hub_id: "hub-test".into(),
            token: "machine-tok".into(),
        }
    }

    async fn db_ready() -> PgAdapter {
        let db = fresh_db().await;
        erplora_runtime::installer::ensure_hub_module_table(&db).await.unwrap();
        erplora_runtime::identity::ensure_tables(&db).await.unwrap();
        erplora_runtime::system_migrations::apply(&db, "hub-test").await.unwrap();
        db
    }

    /// `HUB_SECRETS_KEY` for the tests that actually store something. Set for the whole process:
    /// these tests only ever read it, so unlike the runtime's fail-closed tests they do not need to
    /// serialise on a mutex.
    fn ensure_master_key() {
        // SAFETY: idempotent and only ever SET (never removed) — no test in this file asserts its
        // absence, so there is no ordering another test could observe.
        unsafe { std::env::set_var("HUB_SECRETS_KEY", "A".repeat(43) + "=") };
    }

    // ── Security first: the key must not leak into an error, a log or the response path ───────

    /// 🔒 **An unreadable response must not be quoted back.** The body of THIS endpoint is the
    /// private key: the one moment you most want to print «what did the SaaS actually send me» is
    /// the one moment you must not. The error may name the URL and the status, nothing else.
    #[tokio::test]
    async fn a_malformed_response_never_quotes_the_body_that_holds_the_key() {
        // Valid JSON, wrong shape — the tempting branch is «parse failed, here is what I got».
        let (base, _seen, server) = cloud_stub(
            StatusCode::OK,
            r#"{"pkcs12_b64": "REVMRUdBVEVELVBLQ1MxMg==", "password": "erplora-delegated-passphrase"}"#,
        )
        .await;

        let error = fetch_delegated_certificate(&reqwest::Client::new(), &base, &machine_auth())
            .await
            .unwrap_err();

        assert!(
            !error.contains(DELEGATED_B64),
            "el error arrastra el contenedor PKCS#12: {error}"
        );
        assert!(
            !error.contains(DELEGATED_PASSWORD),
            "el error arrastra la contraseña: {error}"
        );
        server.abort();
    }

    /// 🔒 Same rule on a server error, where a body is even more likely to be echoed into a log.
    #[tokio::test]
    async fn a_server_error_never_quotes_the_body_either() {
        let (base, _seen, server) = cloud_stub(
            StatusCode::INTERNAL_SERVER_ERROR,
            r#"{"detail": "boom", "pkcs12_b64": "REVMRUdBVEVELVBLQ1MxMg==", "password": "erplora-delegated-passphrase"}"#,
        )
        .await;

        let error = fetch_delegated_certificate(&reqwest::Client::new(), &base, &machine_auth())
            .await
            .unwrap_err();

        assert!(!error.contains(DELEGATED_B64), "{error}");
        assert!(!error.contains(DELEGATED_PASSWORD), "{error}");
        // Y sigue siendo diagnosticable: el status es lo que dice si reintentar.
        assert!(error.contains("500"), "el error debería nombrar el status: {error}");
        server.abort();
    }

    /// 🔒 **Nothing of the `.p12` reaches the logs**, on the happy path — the one that runs on every
    /// hub, every rotation. Captures the whole `tracing` output of a real install and greps it.
    #[tokio::test]
    async fn installing_the_certificate_writes_nothing_secret_to_the_logs() {
        ensure_master_key();
        let db = db_ready().await;
        let body: &'static str = Box::leak(served_body(4).into_boxed_str());
        let (base, _seen, server) = cloud_stub(StatusCode::OK, body).await;

        let captured = Arc::new(Mutex::new(Vec::<u8>::new()));
        let writer = CapturingWriter(captured.clone());
        let subscriber = tracing_subscriber::fmt()
            .with_writer(writer)
            .with_max_level(tracing::Level::TRACE)
            .finish();

        let outcome = {
            let _guard = tracing::subscriber::set_default(subscriber);
            install_delegated_certificate(
                &reqwest::Client::new(),
                &base,
                &machine_auth(),
                &db,
                "hub-test",
            )
            .await
            .unwrap()
        };
        assert!(matches!(
            outcome,
            DelegatedCertificateOutcome::Installed { version: 4, .. }
        ));

        let logs = String::from_utf8_lossy(&captured.lock().unwrap().clone()).into_owned();
        assert!(
            !logs.contains(DELEGATED_B64),
            "el contenedor PKCS#12 ha llegado a los logs: {logs}"
        );
        assert!(
            !logs.contains(DELEGATED_PASSWORD),
            "la contraseña ha llegado a los logs: {logs}"
        );
        // Ni un fragmento: una traza que imprimiese el principio de la clave seguiría siendo una fuga.
        for fragment in ["REVMRUdB", "erplora-delegated", "delegated-passphrase"] {
            assert!(!logs.contains(fragment), "fuga del fragmento {fragment:?}: {logs}");
        }
        server.abort();
    }

    /// A `tracing` writer that keeps everything in memory so a test can grep it.
    #[derive(Clone)]
    struct CapturingWriter(Arc<Mutex<Vec<u8>>>);

    impl std::io::Write for CapturingWriter {
        fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
            self.0.lock().unwrap().extend_from_slice(buf);
            Ok(buf.len())
        }
        fn flush(&mut self) -> std::io::Result<()> {
            Ok(())
        }
    }

    impl<'a> tracing_subscriber::fmt::MakeWriter<'a> for CapturingWriter {
        type Writer = CapturingWriter;
        fn make_writer(&'a self) -> Self::Writer {
            self.clone()
        }
    }

    /// 🔒 The MACHINE credential goes out and the user's JWT does not — the SaaS refuses anything
    /// else, and a browser-borne token must never be what asks for a private key.
    #[tokio::test]
    async fn the_request_carries_the_machine_credential_and_no_user_jwt() {
        let body: &'static str = Box::leak(served_body(2).into_boxed_str());
        let (base, seen, server) = cloud_stub(StatusCode::OK, body).await;

        fetch_delegated_certificate(&reqwest::Client::new(), &base, &machine_auth())
            .await
            .unwrap()
            .expect("el certificado servido");

        let headers = seen.lock().unwrap().clone().expect("cabeceras capturadas");
        assert_eq!(headers["x-hub-id"], "hub-test");
        assert_eq!(headers["x-hub-token"], "machine-tok");
        assert!(!headers.contains_key("authorization"));
        server.abort();
    }

    // ── A 404 is an answer, not a breakage ────────────────────────────────────────────────────

    /// **404 `no_delegated_certificate` must not break the hub.** Most hubs sign with their own
    /// certificate and will never be delegated one; turning that into an error would put a permanent
    /// red into every one of them.
    #[tokio::test]
    async fn a_404_is_reported_as_not_provisioned_and_not_as_an_error() {
        ensure_master_key();
        let db = db_ready().await;
        let (base, _seen, server) = cloud_stub(
            StatusCode::NOT_FOUND,
            r#"{"detail": "no_delegated_certificate"}"#,
        )
        .await;

        let outcome = install_delegated_certificate(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &db,
            "hub-test",
        )
        .await
        .unwrap();

        assert_eq!(outcome, DelegatedCertificateOutcome::NotProvisioned);
        server.abort();
    }

    /// …and the hub **keeps its own certificate**. This is the case that matters in production: the
    /// customer uploaded their `.p12`, the control plane has nothing to add, and the fetch must be a
    /// no-op — not something that clears a slot or blocks invoicing.
    #[tokio::test]
    async fn a_404_leaves_a_hub_that_has_its_own_certificate_untouched() {
        ensure_master_key();
        let db = db_ready().await;

        // El hub llega con SU certificado puesto (lo subió su dueño en Ajustes → Negocio).
        seed_own_certificate(&db).await;
        assert_eq!(
            certificate::status(&db, "hub-test").await.unwrap()["present"],
            serde_json::json!(true)
        );

        let (base, _seen, server) = cloud_stub(
            StatusCode::NOT_FOUND,
            r#"{"detail": "no_delegated_certificate"}"#,
        )
        .await;
        let outcome = install_delegated_certificate(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &db,
            "hub-test",
        )
        .await
        .unwrap();

        assert_eq!(outcome, DelegatedCertificateOutcome::NotProvisioned);
        assert_eq!(
            certificate::status(&db, "hub-test").await.unwrap()["present"],
            serde_json::json!(true),
            "un 404 no puede quitarle al hub el certificado que ya tenía"
        );
        assert_eq!(
            certificate::active_kind(&db, "hub-test").await.unwrap(),
            Some(certificate::CertificateKind::Own)
        );
        server.abort();
    }

    /// Seeds the own slot the way the business screen would, but without a real `.p12`.
    async fn seed_own_certificate(db: &PgAdapter) {
        use erplora_db::DatabaseAdapter as _;
        db.execute_batch(&format!(
            "INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by) \
             VALUES ('hub-test', 'own', '{OWN_B64}', 'pw-own', '2026-08-07T00:00:00Z', 'hub_user:admin');"
        ))
        .await
        .unwrap();
    }

    // ── The happy path: stored, encrypted, under the version that was served ──────────────────

    /// 🔒 What arrives over the wire lands **encrypted** in the `delegated` slot, under the version
    /// the SaaS served — and, being ERPlora's key, it still does not travel in an export.
    #[tokio::test]
    async fn the_served_certificate_is_stored_encrypted_under_the_served_version() {
        ensure_master_key();
        let db = db_ready().await;
        let body: &'static str = Box::leak(served_body(4).into_boxed_str());
        let (base, _seen, server) = cloud_stub(StatusCode::OK, body).await;

        let outcome = install_delegated_certificate(
            &reqwest::Client::new(),
            &base,
            &machine_auth(),
            &db,
            "hub-test",
        )
        .await
        .unwrap();

        assert!(matches!(
            outcome,
            DelegatedCertificateOutcome::Installed { version: 4, .. }
        ));
        assert_eq!(
            certificate::delegated_version(&db, "hub-test").await.unwrap(),
            Some(4)
        );
        assert_eq!(
            certificate::active_kind(&db, "hub-test").await.unwrap(),
            Some(certificate::CertificateKind::Delegated)
        );
        // En la BD, cifrado: un `pg_dump` no lleva la clave de ERPlora.
        let (stored_b64, stored_password) = raw_delegated_row(&db).await;
        assert!(stored_b64.starts_with("v1:"), "no está cifrado: {stored_b64}");
        assert!(stored_password.starts_with("v1:"), "no está cifrada: {stored_password}");
        assert!(!stored_b64.contains(DELEGATED_B64));
        assert!(!stored_password.contains(DELEGATED_PASSWORD));
        // Descifrado, es EXACTAMENTE lo servido y en su columna: el contenedor en `pkcs12_b64` y la
        // contraseña en `password`. Intercambiarlos guardaría un `.p12` que ya no abre nunca — y el
        // hub no lo descubriría hasta el primer envío a la AEAT.
        assert_eq!(decrypt(&stored_b64), DELEGATED_B64);
        assert_eq!(decrypt(&stored_password), DELEGATED_PASSWORD);
        // Y la guarda de hub#316 sigue en pie por esta vía nueva.
        assert_eq!(
            certificate::exportable_der_bytes(&db, "hub-test").await.unwrap(),
            None,
            "la clave privada de ERPlora no sale del hub"
        );
        server.abort();
    }

    /// `(pkcs12_b64, password)` of the delegated row exactly as they sit in the database — what
    /// somebody holding a `pg_dump` would get.
    async fn raw_delegated_row(db: &PgAdapter) -> (String, String) {
        use erplora_db::DatabaseAdapter as _;
        let res = db
            .query(
                "SELECT pkcs12_b64, password FROM _hub_certificate \
                 WHERE hub_id = 'hub-test' AND kind = 'delegated'",
                &erplora_db::Params::new(),
            )
            .await
            .unwrap();
        let row = &res.rows[0];
        (
            row["pkcs12_b64"].as_str().unwrap().to_string(),
            row["password"].as_str().unwrap().to_string(),
        )
    }

    /// Undoes the at-rest encryption with the same master key the hub used, so a test can assert
    /// WHICH value landed in which column and not merely that both look encrypted.
    fn decrypt(stored: &str) -> String {
        let key = erplora_runtime::secret_box::master_key_from_env()
            .unwrap()
            .expect("HUB_SECRETS_KEY");
        erplora_runtime::secret_box::decrypt_or_legacy(Some(&key), stored).unwrap()
    }

    /// A rotation replaces bytes AND number together, so the hub never reports a version whose bytes
    /// it does not hold (ADR-0202 §2.5 — that is what the fleet panel counts).
    #[tokio::test]
    async fn a_rotation_moves_the_bytes_and_the_version_together() {
        ensure_master_key();
        let db = db_ready().await;

        let first: &'static str = Box::leak(served_body(4).into_boxed_str());
        let (base, _seen, server) = cloud_stub(StatusCode::OK, first).await;
        install_delegated_certificate(&reqwest::Client::new(), &base, &machine_auth(), &db, "hub-test")
            .await
            .unwrap();
        assert_eq!(certificate::delegated_version(&db, "hub-test").await.unwrap(), Some(4));
        server.abort();

        let rotated: &'static str = Box::leak(
            r#"{"version": 5, "pkcs12_b64": "Uk9UQVRFRC1QS0NTMTI=", "password": "pw-5"}"#
                .to_string()
                .into_boxed_str(),
        );
        let (base, _seen, server) = cloud_stub(StatusCode::OK, rotated).await;
        install_delegated_certificate(&reqwest::Client::new(), &base, &machine_auth(), &db, "hub-test")
            .await
            .unwrap();
        assert_eq!(certificate::delegated_version(&db, "hub-test").await.unwrap(), Some(5));
        server.abort();
    }
}
