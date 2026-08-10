//! Daily business-usage heartbeat (hub#199 / saas#806).
//!
//! This reuses the entitlement's 24-hour tick. The runtime reads the canonical
//! `sales_sale` table and active local device sessions, then posts one compact
//! cumulative snapshot to the SaaS. If the sales module/table is unavailable,
//! `orders_today` is omitted: the Cloud must not turn a read failure into a
//! fabricated zero.

use erplora_db::{DatabaseAdapter, Params};
use serde::Serialize;
use serde_json::{json, Value};

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct DailyUsageHeartbeat {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub orders_today: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_sale_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub terminals: Option<u64>,
    /// Última vez que alguien **entró** en el hub (ADR-0175), si la hubo desde el último latido.
    ///
    /// Es la señal con la que el Cloud apaga (60d) y acaba borrando (120d) los hubs free que nadie
    /// usa, y va aquí — y no en un job aparte — porque este heartbeat ya viaja con la credencial
    /// de máquina y la cadencia correcta. Que sea `Option` es el contrato: **ausente = nadie ha
    /// entrado**, y el Cloud debe dejar correr el reloj. Ver `crate::activity`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_user_activity_at: Option<String>,
    /// Version of the **delegated** certificate this hub holds (ADR-0202 §2.5 — hub#318).
    ///
    /// Three states, and the Cloud stores all three differently, so they must not be conflated:
    /// an explicit **`0`** is «I hold no delegated certificate» (a fresh hub, or one that was
    /// reprovisioned and lost its `HUB_SECRETS_KEY`), a positive number is the version it really
    /// holds, and **absent** is «I am not telling you» — which the Cloud leaves as `NULL`, its
    /// «never reported» state.
    ///
    /// Absent is therefore reserved for a READ FAILURE, never for «no certificate»: the same rule
    /// `orders_today` follows above. A fabricated `0` would show up in the fleet panel as a hub
    /// that lost ERPlora's certificate, and would send somebody looking for a rotation that never
    /// broke.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cert_version: Option<i64>,
    /// `notAfter` of that same delegated container, `YYYY-MM-DD`. Absent when unknown — including
    /// when `cert_version` is `0`, which is what clears a stale expiry on the Cloud side.
    ///
    /// The Cloud compares it against the `not_after` of the `.p12` IT custodies: same version and a
    /// different date means the hub is not really running our certificate (ADR-0202 §2.5).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cert_not_after: Option<String>,
    /// The hub version this container is running, e.g. `1.0.0` (hub#515).
    ///
    /// Sin ella, «¿está este hub al día?» solo se puede contestar adivinando desde un digest — y un
    /// digest no dice si el salto de delante es un parche de seguridad o una versión nueva. Viaja
    /// en ESTE request porque el latido ya lleva la credencial de máquina con la cadencia correcta:
    /// una llamada aparte sería una cosa más que se puede romper.
    ///
    /// **No es `Option`, y eso es el contrato.** En este body «ausente» significa *no pude leerlo*
    /// (`orders_today`, `cert_version`…) y el Cloud lo guarda distinto; la versión va compilada
    /// dentro del binario, así que no existe el caso de «no la sé». Va **sin** el `v`: el prefijo
    /// es para leerlo en un panel, no para que el Cloud tenga que quitarlo antes de comparar.
    pub hub_version: String,
}

/// What the control plane answered to a heartbeat (ADR-0202 §2.5 — hub#318).
///
/// The heartbeat is the **downstream** half of the convergence contract: the response carries the
/// version of the certificate the control plane currently serves, and a hub whose own version
/// differs refetches. It is the cheap trigger — the call already happens, with the credential it
/// already carries, so a rotation converges without a second scheduler or a push channel.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct HeartbeatResponse {
    /// `cert_version` announced by the control plane, when it announced one at all.
    ///
    /// **`None` is «nothing was announced», not «zero»**: an older SaaS answers `{"ok": true}` and
    /// a proxy can answer something that is not JSON at all. Reading either as `0` would be reading
    /// «the control plane has no certificate» out of silence.
    pub cert_version: Option<i64>,
}

impl HeartbeatResponse {
    /// Reads the response body **best-effort**: anything unexpected means «nothing announced».
    ///
    /// Deliberately forgiving, and it is not laziness. A 2xx heartbeat already did its real job
    /// (ADR-0175's activity clock, which is what decides whether a free hub gets switched off), so
    /// a body this hub cannot understand must not turn into an error that stops the clock. The
    /// certificate announcement is an extra that rides along, and it degrades to «no news».
    pub fn parse(body: &str) -> Self {
        let announced = serde_json::from_str::<Value>(body)
            .ok()
            .and_then(|value| value.get("cert_version").and_then(Value::as_i64))
            // A negative version cannot exist (`DelegatedCertificate.version` starts at 0 and only
            // grows). Treating it as an announcement would make the hub chase a version nobody can
            // serve, once per heartbeat, against a budgeted endpoint.
            .filter(|version| *version >= 0);
        Self {
            cert_version: announced,
        }
    }
}

/// Collect today's completed, non-deleted sales and the latest sale timestamp.
/// The SQL intentionally mirrors the module's canonical `sales.today` query.
pub async fn collect_daily_usage(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    now: &str,
) -> DailyUsageHeartbeat {
    let mut params = Params::new();
    params.insert("hub_id".into(), json!(hub_id));
    params.insert("now".into(), json!(now));

    let sales = db
        .query(
            "SELECT COUNT(*) AS orders_today, MAX(created_at) AS last_sale_at \
             FROM sales_sale \
             WHERE hub_id = :hub_id AND is_deleted = 0 AND status = 'completed' \
             AND erp_date(created_at) = erp_date(:now)",
            &params,
        )
        .await
        .ok()
        .and_then(|result| result.rows.into_iter().next());

    let orders_today = sales
        .as_ref()
        .and_then(|row| value_as_u64(&row["orders_today"]));
    let last_sale_at = sales
        .as_ref()
        .and_then(|row| row["last_sale_at"].as_str().map(str::to_owned));

    let terminals = db
        .query(
            "SELECT COUNT(DISTINCT device_id) AS terminals FROM hub_session \
             WHERE expires_at > :now AND device_id IS NOT NULL",
            &params,
        )
        .await
        .ok()
        .and_then(|result| result.rows.into_iter().next())
        .and_then(|row| value_as_u64(&row["terminals"]));

    DailyUsageHeartbeat {
        orders_today,
        last_sale_at,
        terminals,
        // La actividad de usuario no se lee AQUÍ: la sirve el `ActivityState`, que la mantiene en
        // un atómico y la respalda en `_hub_activity` (hub#670). La rellena el llamador (`serve`)
        // y solo si hay algo nuevo que reportar.
        last_user_activity_at: None,
        // El certificado delegado tampoco sale de aquí: lo rellena el llamador (`serve`) con
        // `fiscal_certificate::delegated_certificate_report`, que sabe distinguir «no tengo» de
        // «no he podido leerlo».
        cert_version: None,
        cert_not_after: None,
        // No sale de la BD ni la rellena el llamador: va compilada en el binario, así que el
        // único sitio honesto para leerla es aquí.
        hub_version: crate::version::HUB_VERSION.to_string(),
    }
}

/// Send a best-effort heartbeat with the existing machine credential, and return what the control
/// plane announced back (ADR-0202 §2.5 — hub#318).
pub async fn send_heartbeat(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &cloud_client::Auth,
    body: &DailyUsageHeartbeat,
) -> Result<HeartbeatResponse, String> {
    let req = cloud_client::CloudClient::new(cloud_base_url).heartbeat(auth);
    let mut request = http.post(&req.url).json(body);
    for (name, value) in req.headers {
        request = request.header(name, value);
    }
    let response = request.send().await.map_err(|error| error.to_string())?;
    if !response.status().is_success() {
        return Err(format!("{}: status {}", req.url, response.status()));
    }
    // A 2xx IS the success: the heartbeat's own job (ADR-0175's activity clock) is done, and the
    // caller may confirm it. The body is a bonus, so a truncated read degrades to «nothing
    // announced» rather than undoing a heartbeat that the Cloud already recorded.
    let body = response.text().await.unwrap_or_default();
    Ok(HeartbeatResponse::parse(&body))
}

fn value_as_u64(value: &Value) -> Option<u64> {
    match value {
        Value::Number(number) => number
            .as_u64()
            .or_else(|| number.as_i64().and_then(|n| u64::try_from(n).ok())),
        Value::String(text) => text.trim().parse().ok(),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::extract::State;
    use axum::http::{HeaderMap, StatusCode};
    use axum::routing::post;
    use axum::{Json, Router};
    use erplora_db::testutil::fresh_db;
    use std::sync::{Arc, Mutex};
    use tokio::sync::oneshot;

    #[tokio::test]
    async fn collects_only_completed_sales_for_this_hub_and_day() {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE sales_sale (\
               id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, status TEXT NOT NULL, \
               is_deleted BIGINT NOT NULL DEFAULT 0, created_at TEXT NOT NULL\
             );\
             CREATE TABLE hub_session (\
               token TEXT PRIMARY KEY, device_id TEXT, expires_at TEXT NOT NULL\
             );\
             INSERT INTO sales_sale VALUES\
               ('s1', 'hub-a', 'completed', 0, '2026-07-27T09:00:00Z'),\
               ('s2', 'hub-a', 'completed', 0, '2026-07-27T11:30:00Z'),\
               ('old', 'hub-a', 'completed', 0, '2026-07-26T23:59:59Z'),\
               ('void', 'hub-a', 'voided', 0, '2026-07-27T12:00:00Z'),\
               ('deleted', 'hub-a', 'completed', 1, '2026-07-27T13:00:00Z'),\
               ('other', 'hub-b', 'completed', 0, '2026-07-27T14:00:00Z');\
             INSERT INTO hub_session VALUES\
               ('a1', 'device-a', '2026-07-28T00:00:00Z'),\
               ('a2', 'device-a', '2026-07-28T00:00:00Z'),\
               ('b1', 'device-b', '2026-07-28T00:00:00Z'),\
               ('expired', 'device-c', '2026-07-27T00:00:00Z'),\
               ('unknown', NULL, '2026-07-28T00:00:00Z');",
        )
        .await
        .unwrap();

        let usage = collect_daily_usage(&db, "hub-a", "2026-07-27T15:00:00Z").await;
        assert_eq!(usage.orders_today, Some(2));
        assert_eq!(usage.last_sale_at.as_deref(), Some("2026-07-27T11:30:00Z"));
        assert_eq!(usage.terminals, Some(2));
    }

    #[tokio::test]
    async fn missing_sales_table_omits_usage_instead_of_inventing_zero() {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE hub_session (\
               token TEXT PRIMARY KEY, device_id TEXT, expires_at TEXT NOT NULL\
             );",
        )
        .await
        .unwrap();

        let usage = collect_daily_usage(&db, "hub-a", "2026-07-27T15:00:00Z").await;
        assert_eq!(usage.orders_today, None);
        assert_eq!(usage.last_sale_at, None);
        assert_eq!(usage.terminals, Some(0));
        assert_eq!(
            serde_json::to_value(usage).unwrap(),
            json!({"terminals": 0, "hub_version": crate::version::HUB_VERSION})
        );
    }

    #[tokio::test]
    async fn sends_expected_json_and_machine_headers() {
        type Captured = Arc<Mutex<Option<oneshot::Sender<(HeaderMap, Value)>>>>;

        async fn capture(
            State(sender): State<Captured>,
            headers: HeaderMap,
            Json(body): Json<Value>,
        ) -> StatusCode {
            if let Some(sender) = sender.lock().unwrap().take() {
                let _ = sender.send((headers, body));
            }
            StatusCode::OK
        }

        let (sender, receiver) = oneshot::channel();
        let app = Router::new()
            .route("/api/v1/hub/device/heartbeat/", post(capture))
            .with_state(Arc::new(Mutex::new(Some(sender))));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });

        let auth = cloud_client::Auth::HubToken {
            hub_id: "hub-a".into(),
            token: "machine-token".into(),
        };
        let body = DailyUsageHeartbeat {
            orders_today: Some(12),
            last_sale_at: Some("2026-07-27T11:30:00Z".into()),
            terminals: Some(3),
            last_user_activity_at: Some("2026-07-27T11:45:00Z".into()),
            cert_version: Some(4),
            cert_not_after: Some("2028-06-10".into()),
        hub_version: crate::version::HUB_VERSION.to_string(),
    };
        send_heartbeat(
            &reqwest::Client::new(),
            &format!("http://{address}"),
            &auth,
            &body,
        )
        .await
        .unwrap();

        let (headers, received) = receiver.await.unwrap();
        assert_eq!(headers["x-hub-id"], "hub-a");
        assert_eq!(headers["x-hub-token"], "machine-token");
        assert_eq!(
            received,
            json!({
                "orders_today": 12,
                "last_sale_at": "2026-07-27T11:30:00Z",
                "terminals": 3,
                "last_user_activity_at": "2026-07-27T11:45:00Z",
                "cert_version": 4,
                "cert_not_after": "2028-06-10",
                "hub_version": crate::version::HUB_VERSION,
            })
        );
        server.abort();
    }

    /// ADR-0175: sin actividad de usuario el campo NO viaja. El silencio es la señal — si el
    /// Cloud recibiese una marca en cada latido, un hub encendido que nadie usa parecería usado
    /// y no vencería nunca.
    #[tokio::test]
    async fn a_hub_nobody_uses_reports_no_user_activity() {
        let usage = DailyUsageHeartbeat {
            orders_today: Some(0),
            last_sale_at: None,
            terminals: Some(0),
            last_user_activity_at: None,
            cert_version: None,
            cert_not_after: None,
        hub_version: crate::version::HUB_VERSION.to_string(),
    };
        let body = serde_json::to_value(&usage).unwrap();
        assert!(body.get("last_user_activity_at").is_none());
        assert_eq!(body, json!({"orders_today": 0, "terminals": 0, "hub_version": crate::version::HUB_VERSION}));
    }

    // ── The certificate the hub REPORTS (ADR-0202 §2.5 — hub#318) ─────────────────────────────

    /// **`0` travels, silence does not.** The Cloud stores `NULL` (never reported) and `0` (holds
    /// no delegated certificate) in different states, so a hub that genuinely has none must SAY
    /// `0` — omitting it would leave the fleet panel showing a hub that never spoke, forever.
    #[test]
    fn a_hub_with_no_delegated_certificate_reports_an_explicit_zero() {
        let usage = DailyUsageHeartbeat {
            orders_today: None,
            last_sale_at: None,
            terminals: None,
            last_user_activity_at: None,
            cert_version: Some(0),
            cert_not_after: None,
        hub_version: crate::version::HUB_VERSION.to_string(),
    };
        let body = serde_json::to_value(&usage).unwrap();
        assert_eq!(body, json!({"cert_version": 0, "hub_version": crate::version::HUB_VERSION}));
        // Y la caducidad NO viaja: es justo lo que borra en el Cloud la fecha vieja de un hub
        // reprovisionado (§2.5, «el par se escribe entero»).
        assert!(body.get("cert_not_after").is_none());
    }

    /// **A read failure is silence, never a zero.** Same rule `orders_today` already follows: the
    /// Cloud must not turn a failure of ours into a fact about the fleet. A fabricated `0` would
    /// paint a healthy hub as one that lost ERPlora's certificate.
    #[test]
    fn a_hub_that_could_not_read_its_certificate_says_nothing_instead_of_zero() {
        let usage = DailyUsageHeartbeat {
            orders_today: Some(3),
            last_sale_at: None,
            terminals: Some(1),
            last_user_activity_at: None,
            cert_version: None,
            cert_not_after: None,
        hub_version: crate::version::HUB_VERSION.to_string(),
    };
        let body = serde_json::to_value(&usage).unwrap();
        assert!(body.get("cert_version").is_none());
        assert_eq!(body, json!({"orders_today": 3, "terminals": 1, "hub_version": crate::version::HUB_VERSION}));
    }

    // ── What the control plane announces back (ADR-0202 §2.5) ─────────────────────────────────

    #[test]
    fn the_announced_version_is_read_from_the_response() {
        assert_eq!(
            HeartbeatResponse::parse(r#"{"ok": true, "cert_version": 4}"#),
            HeartbeatResponse {
                cert_version: Some(4)
            }
        );
        // `0` es un anuncio de pleno derecho: «no he subido nada» (y el hub NO debe pedir el GET).
        assert_eq!(
            HeartbeatResponse::parse(r#"{"ok": true, "cert_version": 0}"#).cert_version,
            Some(0)
        );
    }

    /// **Silence is not zero.** A SaaS from before saas#1126 answers `{"ok": true}`; reading that
    /// as «the control plane has no certificate» would be inventing news out of an old deployment.
    #[test]
    fn an_older_control_plane_that_announces_nothing_is_not_read_as_zero() {
        assert_eq!(HeartbeatResponse::parse(r#"{"ok": true}"#).cert_version, None);
        assert_eq!(
            HeartbeatResponse::parse(r#"{"cert_version": null}"#).cert_version,
            None
        );
    }

    /// **A body this hub cannot parse must not become an error.** The heartbeat already succeeded
    /// (2xx) and its real job is ADR-0175's activity clock: if an edge that answers HTML turned the
    /// call into a failure, the hub would stop confirming activity and the Cloud would count it
    /// idle — and eventually switch a hub off that people are using every day.
    #[test]
    fn a_body_that_is_not_json_degrades_to_no_news() {
        assert_eq!(HeartbeatResponse::parse("<html>502</html>").cert_version, None);
        assert_eq!(HeartbeatResponse::parse("").cert_version, None);
        assert_eq!(HeartbeatResponse::parse("[]").cert_version, None);
    }

    /// A version that cannot exist is not an announcement. `DelegatedCertificate.version` starts at
    /// `0` and only grows, so a negative would just make the hub chase a certificate nobody can
    /// serve — once per heartbeat, against an endpoint that is budgeted at 20/h.
    #[test]
    fn a_negative_version_is_not_an_announcement() {
        assert_eq!(
            HeartbeatResponse::parse(r#"{"cert_version": -1}"#).cert_version,
            None
        );
    }

    /// A 2xx whose body is unreadable is still a heartbeat that ARRIVED: it must come back `Ok`,
    /// because the caller confirms ADR-0175's activity mark on `Ok` and only on `Ok`.
    #[tokio::test]
    async fn an_unparseable_body_still_counts_as_a_delivered_heartbeat() {
        let app = Router::new().route(
            "/api/v1/hub/device/heartbeat/",
            post(|| async { (StatusCode::OK, "<html>hola</html>") }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });

        let auth = cloud_client::Auth::HubToken {
            hub_id: "hub-a".into(),
            token: "machine-token".into(),
        };
        let response = send_heartbeat(
            &reqwest::Client::new(),
            &format!("http://{address}"),
            &auth,
            &DailyUsageHeartbeat {
                orders_today: None,
                last_sale_at: None,
                terminals: None,
                last_user_activity_at: None,
                cert_version: Some(0),
                cert_not_after: None,
            hub_version: crate::version::HUB_VERSION.to_string(),
        },
        )
        .await
        .expect("un 2xx es un latido entregado, lo que traiga el cuerpo o no");
        assert_eq!(response.cert_version, None);
        server.abort();
    }

    /// 🔒 …y lo mismo cuando el cuerpo **no se puede ni leer**: la respuesta promete 64 bytes y la
    /// conexión se corta a los 2.
    ///
    /// Es el caso que un stub HTTP normal no puede montar, y es justo el que aparece de verdad —
    /// un reset a mitad de respuesta, un edge que se rinde. Si eso convirtiera el latido en un
    /// error, el hub dejaría de confirmar la marca de actividad de ADR-0175 y el Cloud acabaría
    /// **apagando un hub que se usa a diario**. El anuncio del certificado es un extra que viaja
    /// encima; el latido ya llegó.
    #[tokio::test]
    async fn a_body_that_cannot_even_be_read_still_counts_as_a_delivered_heartbeat() {
        use tokio::io::{AsyncReadExt, AsyncWriteExt};

        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            if let Ok((mut socket, _)) = listener.accept().await {
                // Basta con drenar algo de la petición para que el cliente termine de enviarla.
                let mut buffer = [0u8; 4096];
                let _ = socket.read(&mut buffer).await;
                let _ = socket
                    .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 64\r\n\r\nok")
                    .await;
                let _ = socket.shutdown().await;
            }
        });

        let auth = cloud_client::Auth::HubToken {
            hub_id: "hub-a".into(),
            token: "machine-token".into(),
        };
        let response = send_heartbeat(
            &reqwest::Client::new(),
            &format!("http://{address}"),
            &auth,
            &DailyUsageHeartbeat {
                orders_today: None,
                last_sale_at: None,
                terminals: None,
                last_user_activity_at: None,
                cert_version: Some(4),
                cert_not_after: None,
            hub_version: crate::version::HUB_VERSION.to_string(),
        },
        )
        .await
        .expect("un 2xx entregado no puede deshacerse porque el cuerpo se corte");
        assert_eq!(response.cert_version, None, "sin cuerpo legible, sin noticias");
        server.abort();
    }

    /// The hub tells the control plane which version is running (hub#515).
    ///
    /// Without it, «is this hub up to date?» has no answer that does not involve guessing from a
    /// digest — and a digest cannot say whether the jump ahead is a security patch or a new
    /// version. It rides THIS request because the heartbeat is already the beat that carries the
    /// machine credential at the right cadence; a second call would be a second thing to break.
    ///
    /// It is the same number `/system` shows and `error_sink` stamps on every reported error
    /// ([`crate::version::HUB_VERSION`]), and it goes on the wire WITHOUT the `v` — the prefix is
    /// for humans reading a panel, not for something the Cloud will compare.
    #[test]
    fn the_heartbeat_carries_the_running_hub_version() {
        let body = DailyUsageHeartbeat {
            orders_today: Some(3),
            last_sale_at: None,
            terminals: None,
            last_user_activity_at: None,
            cert_version: None,
            cert_not_after: None,
            hub_version: crate::version::HUB_VERSION.to_string(),
        };

        let wire = serde_json::to_value(&body).expect("el latido tiene que serializar");

        assert_eq!(wire["hub_version"], crate::version::HUB_VERSION);
        assert!(
            !wire["hub_version"].as_str().unwrap().starts_with('v'),
            "el `v` es para la pantalla, no para el cable"
        );
    }

    /// It is always there — never «absent because I could not read it».
    ///
    /// Every other optional field on this body means a READ FAILURE when missing (`orders_today`,
    /// `cert_version`…), and the Cloud stores that difference. The version is compiled in, so
    /// there is no failure mode where it is unknown: making it optional would invent a third
    /// state nobody can produce.
    #[tokio::test]
    async fn the_collected_heartbeat_already_knows_its_version() {
        let db = fresh_db().await;
        db.execute_batch(
            "CREATE TABLE sales_sale (\
               id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, status TEXT NOT NULL, \
               is_deleted BIGINT NOT NULL DEFAULT 0, created_at TEXT NOT NULL\
             );\
             CREATE TABLE hub_session (\
               token TEXT PRIMARY KEY, device_id TEXT, expires_at TEXT NOT NULL\
             );",
        )
        .await
        .unwrap();

        let usage = collect_daily_usage(&db, "hub-1", "2026-08-08T10:00:00Z").await;

        assert_eq!(usage.hub_version, crate::version::HUB_VERSION);
    }
}
