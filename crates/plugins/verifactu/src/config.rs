//! Fiscal config, certificate source, environments and endpoints — split out of `lib.rs` verbatim (hub#1405).

use crate::*;

/// Lee la config VeriFactu del hub (fila singleton; `None` si no se ha guardado nunca).
///
/// **Certificado (ADR-0079/0081, ADR-0202 §2.1):** el PKCS#12 vive en el core (`_hub_certificate`),
/// NO en `verifactu_config`, y el hub tiene DOS slots — el `own` del negocio (subido en Ajustes →
/// Negocio) y el `delegated` de ERPlora, que el plano de control reparte y rota. Aquí solo se marca
/// **qué dice el core**: `certificate_source = "core"` (hay con qué firmar) y `certificate_kind`
/// (con cuál). **Los bytes del `.p12` y la contraseña NUNCA se copian a la config del módulo** —
/// ni se consultan siquiera: la firma/transmisión usa la capability opaca
/// `certificate_identity(hub_id)` (el core hace la cripto; ver `build_identity`). El acceso está
/// gateado por la capability `certificate` (el dispatcher la exige antes del handler nativo),
/// así que llegar aquí implica que el usuario la concedió.
///
/// **Quién firma lo decide el CORE, no este módulo** (hub#319). Antes se sondeaba
/// `SELECT pkcs12_b64, password FROM _hub_certificate … LIMIT 1`: sin `kind` (con dos filas, la que
/// devolviese la BD), contando filas que el core se niega a seleccionar, y arrastrando la contraseña
/// del certificado a la memoria del módulo solo para comprobar que no estaba vacía. La regla de
/// selección (`own` si está, si no `delegated`) tiene un dueño y no se reimplementa aquí.
pub(crate) async fn read_config(host: &dyn NativeHost, hub_id: &str) -> Result<Option<Json>> {
    let rows = host
        .read(
            "SELECT * FROM verifactu_config WHERE hub_id = :hub_id AND is_deleted = 0 LIMIT 1",
            &params(json!({ "hub_id": hub_id })),
        )
        .await?;
    let mut config = rows.into_iter().next();

    // Tolerante: un host sin la capacidad (o un hub sin la migración de sistema) responde `None` y
    // el módulo se queda sin marcador — que es «no puedo transmitir», el lado seguro.
    if let Some(kind) = host
        .certificate_signing_kind(hub_id)
        .await
        .unwrap_or_default()
    {
        // **Y QUÉ es**, que es otra pregunta (hub#470): el slot dice de quién es el certificado, el
        // tipo dice por qué puerta de la AEAT entra. Se lee del MISMO sitio y en la misma pasada que
        // el slot —el core— para que no haya dos lecturas de «con qué firmo» que puedan contestar
        // distinto: ese desdoblamiento es exactamente cómo se estropearon #317, #318 y #319.
        // `None` (el core no puede jurarlo, o un host sin la capacidad) deja el marcador vacío, que
        // es la puerta del titular.
        let certificate_type = host
            .certificate_signing_type(hub_id)
            .await
            .unwrap_or_default()
            .unwrap_or_default();
        let obj = config.get_or_insert_with(|| json!({}));
        if let Some(m) = obj.as_object_mut() {
            m.insert("certificate_source".into(), json!("core"));
            m.insert("certificate_kind".into(), json!(kind));
            m.insert("certificate_type".into(), json!(certificate_type));
        }
    }

    // Los hechos del productor (hub#323): identidad del fabricante + `IndicadorMultiplesOT`, que
    // el hub NO puede saber y que el plano de control sirve en el latido. Viajan pegados a la
    // config —igual que los marcadores del certificado— para que el constructor del XML lea UN
    // objeto y no sepa que existe un Cloud. Ausentes = ausentes: no hay defaults para una
    // declaración legal, y `sistema_informatico` se niega a construir el registro.
    //
    // Se ADJUNTAN a la config, nunca la CREAN: «este hub no tiene config de VeriFactu» tiene que
    // seguir contestando `None` a quien pregunta. Los hechos del productor son de la flota, no de
    // este hub, y no convierten un módulo sin configurar en uno configurado.
    if let Some(obj) = config.as_mut().and_then(Json::as_object_mut) {
        if let Some(facts) = host.producer_facts().await.unwrap_or_default() {
            obj.insert("producer_facts".into(), facts);
        }
    }
    Ok(config)
}

/// Construye la **Identity mTLS** para firmar/transmitir a la AEAT.
///
/// El certificado fiscal (.p12) es un recurso del NEGOCIO/hub (ADR-0079/0081) y desde ADR-0202 §2.1
/// hay dos: el **propio** del negocio y el **delegado** de ERPlora. `host.certificate_identity`
/// resuelve el fallback (`own` si está subido, si no `delegated`) y hace TODA la cripto PKCS#12;
/// **los bytes del `.p12` y la contraseña NUNCA entran al módulo**.
///
/// Error **solo si no hay ninguno de los dos** (hub#319): un hub cuyo único certificado es el
/// delegado transmite perfectamente — ERPlora firma en su nombre.
pub(crate) async fn build_identity(
    host: &dyn NativeHost,
    hub_id: &str,
    config: &Json,
) -> Result<reqwest::Identity> {
    if !has_certificate(config) {
        return Err(VerifactuError::Certificate(
            "no hay certificado con el que firmar: ni el del negocio (súbelo en Ajustes → Negocio) \
             ni uno delegado de ERPlora"
                .into(),
        )
        .into());
    }
    host.certificate_identity(hub_id).await
}

/// ¿Hay un certificado del core con el que transmitir — propio **o** delegado? Gate barato que NO
/// carga los bytes del `.p12`: basta el marcador `certificate_source` que `read_config` pone con lo
/// que respondió el core.
pub(crate) fn has_certificate(config: &Json) -> bool {
    str_field(config, "certificate_source") == "core"
}

/// The two roads of ADR-0320, resolved in ONE place (hub#1432 — the hub#319/#320 lesson: one
/// question, one owner). The core's certificate WINS: a business that uploaded its own signs
/// with its own, direct to the AEAT, exactly as today. Without one, the gateway —
/// [`crate::gateway::resolve_access`] answers when the machine identity the host lends is enrolled and
/// the control plane authorises (hub#1459: the core no longer brokers this, it only lends the
/// identity and the call). Without EITHER, the same visible error as always: the record stays pending,
/// never a panic, never a silent skip.
pub(crate) enum TransmitRoute {
    Direct(reqwest::Identity),
    Gateway(crate::gateway::GatewayAccess),
}

pub(crate) async fn resolve_route(
    host: &dyn NativeHost,
    hub_id: &str,
    config: &Json,
) -> Result<TransmitRoute> {
    if has_certificate(config) {
        return Ok(TransmitRoute::Direct(
            host.certificate_identity(hub_id).await?,
        ));
    }
    match crate::gateway::resolve_access(host, hub_id).await? {
        Some(access) => Ok(TransmitRoute::Gateway(access)),
        None => Err(VerifactuError::Certificate(
            "no hay vía de transmisión: ni certificado del negocio (súbelo en Ajustes → Negocio) \
             ni pasarela fiscal disponible (identidad de máquina sin enrolar)"
                .into(),
        )
        .into()),
    }
}

/// ¿Hay ALGUNA vía — certificado del core O pasarela? El gate de la cola de contingencia: sin
/// ninguna, los registros se quedan `pending` (comportamiento de siempre) en vez de quemar
/// reintentos que no pueden salir.
pub(crate) async fn can_transmit(
    host: &dyn NativeHost,
    hub_id: &str,
    config: &Json,
) -> Result<bool> {
    if has_certificate(config) {
        return Ok(true);
    }
    Ok(crate::gateway::resolve_access(host, hub_id).await?.is_some())
}

/// **¿Puede este motor firmar por `hub_id` ahora mismo?** — exactamente el predicado con el que
/// [`build_identity`] deja pasar o rechaza.
///
/// `pub` a propósito (hub#319): «¿puede este hub facturar?» la contestan TRES sitios —el gate fiscal
/// del dispatcher (ADR-0203), el brazo ⛔ de la checklist (hub#370) y este motor— y tienen que
/// contestar lo mismo. Un ⛔ que bloquea una pantalla mientras el runtime acepta la venta, o al
/// revés, es la checklist mintiendo. Con el predicado del motor accesible, esa coherencia se
/// comprueba en UN test junto a los otros dos, en vez de confiarla a tres tests separados que
/// pueden separarse sin que nada avise.
pub async fn can_sign(host: &dyn NativeHost, hub_id: &str) -> Result<bool> {
    Ok(read_config(host, hub_id)
        .await?
        .as_ref()
        .is_some_and(has_certificate))
}

/// Con **cuál** de los dos se firma: `"own"`, `"delegated"`, o `""` si no hay ninguno
/// (ADR-0202 §2.1 — hub#319).
///
/// ⚠️ **Esta es la respuesta que lee el endpoint AEAT (`www1` vs `www10`, hub#320) y la que tiene
/// que leer [hub#321] (bloque `Representante`), NO una segunda consulta a `_hub_certificate`.** La
/// selección arrastra el endpoint y el `Representante`, así que resolverla otra vez por su cuenta
/// es cómo vuelve el defecto que hub#317 y hub#318 ya arreglaron dos veces: dos lecturas de la
/// misma pregunta que pueden contestar distinto. Hasta que hub#321 aterrice, un hub que firme con
/// el delegado transmite por el endpoint correcto pero **sin `Representante`**.
///
/// [hub#321]: https://github.com/ERPlora/hub/issues/321
pub(crate) fn signing_kind(config: &Json) -> String {
    str_field(config, "certificate_kind")
}

/// **QUÉ es** el certificado que firma: `"seal"`, `"representative"`, o `""` si el core no puede
/// jurarlo (ADR-0202 §2.1 — hub#470).
///
/// El gemelo de [`signing_kind`], y la distinción es el fondo de hub#470: el slot dice **de quién**
/// es el certificado —lo que decide el fallback y lo que necesitará el bloque `Representante` de
/// hub#321— y el tipo dice **qué** es, que es lo único por lo que la AEAT segrega la puerta. Leer
/// el slot como si fuera el tipo mandaba a `www10` a cualquier certificado repartido por el plano
/// de control, fuese un sello o no.
///
/// Lo pone [`read_config`] con lo que contestó el core. El motor no vuelve a preguntar a
/// `_hub_certificate`: una sola lectura, un solo dueño.
pub(crate) fn signing_type(config: &Json) -> String {
    str_field(config, "certificate_type")
}

/// **El endpoint AEAT de este hub AHORA MISMO** — los dos ejes (`environment` y certificado que
/// firma) resueltos de la MISMA lectura de la config (ADR-0202 §2.1 — hub#320).
///
/// Existe para que ningún sitio los multiplique por su cuenta. Son dos ejes y fallan distinto: un
/// certificado en la puerta equivocada se rechaza (ruidoso, recuperable a mano); un entorno
/// equivocado se **acepta** en el sistema que no era, y un registro remitido no se reenvía ni se
/// borra (ADR-0189). ⚠️ El eje del **entorno** sale de la config, no del registro, así que un
/// registro encolado en `testing` y drenado tras un go-live sale hacia la AEAT real:
/// [hub#471](https://github.com/ERPlora/hub/issues/471) (pendiente, va con la guarda R1).
///
/// **El endpoint acompaña al CERTIFICADO, no al XML.** La AEAT segrega la puerta por el certificado
/// que se presenta en el handshake TLS, así que un registro que lleva días en contingencia se
/// transmite por la puerta del certificado que firma **hoy**, no por la del que firmaba cuando se
/// generó: presentar el sello de ERPlora en `www1` falla siempre, diga lo que diga el XML
/// archivado. ⚠️ La otra mitad de esa pareja —el `Representante`, que sí viaja DENTRO del
/// `xml_content` congelado del reintento— es de [hub#321](https://github.com/ERPlora/hub/issues/321):
/// si el hub cambió de certificado mientras el registro esperaba en la cola, ese XML describe al
/// firmante anterior y habrá que reconstruirlo.
pub(crate) fn transmission_endpoint(config: &Json) -> &'static str {
    aeat::endpoint(&environment_of(config), &signing_type(config))
}

/// **Por qué puerta de la AEAT transmite este hub AHORA MISMO**, resuelto desde el host — los dos
/// ejes de la MISMA lectura de la config, sin que el llamante los multiplique por su cuenta.
///
/// `pub` a propósito, por el mismo motivo que [`can_sign`] (hub#319): la cadena core → `read_config`
/// → tipo de certificado → URL cruza dos crates, y la familia de defectos de #317/#318/#319/#470 es
/// justamente la de un dato de certificado que se lee distinto a cada lado. Con la cadena entera
/// accesible se comprueba en UN test de punta a punta, en vez de en dos tests que pueden
/// separarse sin que nada avise.
pub async fn transmission_endpoint_for(
    host: &dyn NativeHost,
    hub_id: &str,
) -> Result<&'static str> {
    let config = read_config(host, hub_id)
        .await?
        .unwrap_or_else(|| json!({}));
    Ok(transmission_endpoint(&config))
}

/// El endpoint de **consulta** de este hub ahora mismo. Es el mismo que el de alta (el WSDL publica
/// las dos operaciones en `VerifactuSOAP`, hub#287) y por eso se deriva igual, con los dos ejes de
/// la misma lectura: recuperar la cadena tiene que hablar con la misma puerta que la emitió.
pub(crate) fn consult_endpoint_of(config: &Json) -> &'static str {
    aeat::consult_endpoint(&environment_of(config), &signing_type(config))
}

/// **Where ONE record's transmission is going** — resolved once and then shared by the POST, by
/// the audit event and by the drift warning, so the wire and the paper trail cannot say
/// different things about the same send (hub#471).
#[derive(Debug)]
pub(crate) struct Destination {
    /// The AEAT environment that must receive this record: the one its CHAIN lives in.
    pub(crate) environment: String,
    /// `environment` × the certificate signing TODAY. Still ONE multiplication (hub#320).
    pub(crate) endpoint: &'static str,
    /// The hub's CURRENT environment, and only when it is NOT the record's.
    pub(crate) hub_environment: Option<String>,
}

impl Destination {
    /// What the owner reads in the fiscal event log when a record left for an environment that
    /// is no longer the hub's — the visible half of hub#471. Nothing is wrong here, but nothing
    /// about it is routine either: it means the contingency queue outlived a go-live.
    pub(crate) fn drift_note(&self) -> Option<String> {
        self.hub_environment.as_ref().map(|hub_environment| {
            format!(
                "remitido a «{}» —el entorno de la CADENA de este registro— aunque el hub está \
                 ahora en «{hub_environment}»: las dos cadenas no se mezclan (ADR-0202 §3)",
                self.environment
            )
        })
    }
}

/// The AEAT environment stamped on the record when it was created (guard R4, hub#313) — the one
/// its hash chain lives in, and never re-derived from the config afterwards.
///
/// `None` is NOT «testing». A row that does not carry the column predates migration 008 and its
/// chain could belong to either system; both guesses are unrecoverable — a practice record
/// **accepted** by the real AEAT, or a real invoice the real AEAT never receives — so the caller
/// refuses instead of picking one.
pub(crate) fn record_environment(record: &Json) -> Option<String> {
    let environment = str_field(record, "environment");
    (!environment.is_empty()).then_some(environment)
}

/// Resolves the [`Destination`] of one record, or says why it cannot.
///
/// The two axes answer to different owners **on purpose** (hub#471, hub#320):
///
/// - the **environment** belongs to the RECORD. `production` and `testing` are two parallel
///   chains that never mix (guard R4), and the previous link, the frozen `xml_content` and the
///   QR host of a queued record already all say the same one. Reading the URL from the config
///   made those four disagree the moment the operator went live with a non-empty queue;
/// - the **certificate** belongs to TODAY'S config. The AEAT segregates the door by the
///   certificate presented in the TLS handshake, so a record that waited days in contingency
///   goes through the door of whatever signs now.
///
/// And they fail in opposite ways, which is why one is worth refusing over: the wrong door is
/// REJECTED — loud, and recoverable one record at a time — while the wrong environment is
/// ACCEPTED by a tax agency that was never meant to receive it, and an accepted record is
/// neither resent nor deleted (ADR-0189).
///
/// ⚠️ The certificate axis is [`signing_type`], **not** [`signing_kind`] (hub#470): the AEAT
/// segregates by what the certificate IS, and the slot only says whose it is. This function is the
/// second place in the engine that multiplies the two axes, so it is also the second place that has
/// to read the same value as [`transmission_endpoint`] — reading one from the type and the other
/// from the slot is exactly the shape of defect this whole chain keeps producing.
pub(crate) fn destination_of(
    record: &Json,
    config: &Json,
) -> std::result::Result<Destination, String> {
    let hub_environment = environment_of(config);
    let Some(environment) = record_environment(record) else {
        return Err(format!(
            "el registro no dice a qué entorno de la AEAT pertenece (fila anterior a la \
             migración 008) y el hub está en «{hub_environment}»: no se transmite a ciegas"
        ));
    };
    Ok(Destination {
        endpoint: aeat::endpoint(&environment, &signing_type(config)),
        // Only when they differ: `Some` IS the drift, so nothing downstream has to compare.
        hub_environment: (environment != hub_environment).then_some(hub_environment),
        environment,
    })
}

/// **Tercer disparador de refetch del certificado** (ADR-0202 §2 punto 4 — hub#318): un fallo del
/// canal TLS contra la AEAT pide al plano de control el certificado vigente.
///
/// El motor **no descarga nada**. No tiene la credencial de máquina del hub y no debe tenerla: la
/// clave privada delegada es de ERPlora y su única puerta de entrada vive en el server
/// (`erplora-server::fiscal_certificate`). Aquí solo se levanta la señal; quién la sirve, cuándo, y
/// con cuánto presupuesto, es decisión del server.
///
/// Solo el TLS. Un timeout o un DNS caído se reintentan por la cola de contingencia (5/10/20/40/60
/// min) y **no** se arreglan bajando otra vez una clave privada: pedirla en cada registro varado
/// agotaría el presupuesto de 20/h del endpoint justo cuando el hub más lo necesita.
///
/// **Y solo si quien se identificó fue el certificado DELEGADO** (`signing_kind`, hub#319). El
/// refetch baja el de ERPlora; si el handshake lo rompió el certificado **propio** del negocio
/// —caducado, revocado, contraseña cambiada—, bajar el delegado no arregla nada, porque el propio
/// sigue ganando el fallback (ADR-0202 §2.1) y el intento siguiente falla igual. Lo único que
/// lograría es gastar el cupo del hub en algo que no puede funcionar, y dejar sin él al disparador
/// del latido —el que sí instala una rotación real— justo cuando llegue.
///
/// El `signal` es un parámetro —y no el global directamente— para que esto sea comprobable sin
/// tocar estado de proceso compartido entre tests.
pub(crate) fn request_certificate_refetch_on_tls(
    error: &VerifactuError,
    signing_kind: &str,
    signal: &RefetchSignal,
) {
    if matches!(error, VerifactuError::Tls(_)) && signing_kind == DELEGATED_SLOT {
        signal.request();
    }
}

/// Nombre del slot delegado tal y como lo devuelve el core
/// (`certificate::CertificateKind::as_str`). Constante para que la comparación no se escriba a mano
/// en cada sitio y pueda equivocarse en uno.
pub(crate) const DELEGATED_SLOT: &str = "delegated";

/// Nombre del tipo **sello de entidad** tal y como lo devuelve el core
/// (`certificate::CertificateType::as_str`). El ÚNICO valor que abre la puerta `www10` de la AEAT
/// (`aeat::endpoint`); todo lo demás cae a la del titular.
///
/// ⚠️ Es una constante distinta de [`DELEGATED_SLOT`] a propósito, y no un alias suyo: son las dos
/// palabras que hub#470 separó —de quién es el certificado vs. qué es— y colapsarlas otra vez
/// devuelve el defecto.
pub(crate) const SEAL_TYPE: &str = "seal";

// ── create_record (issue verifactu#2) ────────────────────────────────────────

#[cfg(test)]
mod cert_source_tests {
    use super::*;

    /// Host que simula un hub con certificado del negocio en el core (`_hub_certificate`). El core
    /// responde el slot que firma; las filas de la tabla siguen ahí para que el test compruebe que
    /// el módulo NO las lee (ADR-0079).
    struct CoreCertHost;
    #[async_trait::async_trait]
    impl NativeHost for CoreCertHost {
        async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
            if sql.contains("_hub_certificate") {
                Ok(vec![json!({ "pkcs12_b64": "QUJD", "password": "secret" })])
            } else if sql.contains("verifactu_config") {
                Ok(vec![json!({ "hub_id": "h1", "environment": "testing" })])
            } else {
                Ok(vec![])
            }
        }
        async fn certificate_signing_kind(&self, _hub_id: &str) -> Result<Option<String>> {
            Ok(Some("own".to_string()))
        }
    }

    /// ADR-0079/0081: el `.p12` del negocio es del CORE. `read_config` debe **marcar** su presencia
    /// (`certificate_source = "core"`) pero NUNCA copiar los bytes del `.p12` ni la contraseña a la
    /// config del módulo — se quedan en el core; la firma usa la capability opaca
    /// `certificate_identity(hub_id)` (ver `build_identity`), no `certificate_identity_from`.
    #[tokio::test]
    async fn read_config_marks_core_cert_without_leaking_bytes() {
        let cfg = read_config(&CoreCertHost, "h1").await.unwrap().unwrap();
        assert_eq!(
            cfg.get("certificate_source").and_then(|v| v.as_str()),
            Some("core"),
            "debe marcar que el cert es del core"
        );
        assert!(
            cfg.get("certificate_pkcs12").is_none(),
            "los bytes del .p12 NO deben entrar en la config del módulo (ADR-0079)"
        );
        assert!(
            cfg.get("certificate_password").is_none(),
            "la contraseña del cert NO debe entrar en la config del módulo (ADR-0079)"
        );
    }

    // ── hub#319: which slot signs is the CORE's answer, never the module's guess ──────────────

    /// A host that answers the certificate question the way the CORE does — with the slot that
    /// signs — and that RECORDS every SQL the engine runs, so a test can assert what the module did
    /// **not** ask the database for.
    struct SlotHost {
        signing: Option<&'static str>,
        /// What the core says the signing certificate IS (hub#470) — independent of the slot, which
        /// is the whole point: `new` leaves it `None` («cannot tell»), and the tests that care set
        /// it explicitly.
        signing_type: Option<&'static str>,
        /// Rows `_hub_certificate` would return to a module that went behind the core's back.
        stored_rows: Vec<Json>,
        seen_sql: std::sync::Mutex<Vec<String>>,
    }

    impl SlotHost {
        fn new(signing: Option<&'static str>, stored_rows: Vec<Json>) -> Self {
            Self {
                signing,
                signing_type: None,
                stored_rows,
                seen_sql: std::sync::Mutex::new(Vec::new()),
            }
        }

        /// The core also knows what the container IS. Chained so a test reads as «this slot, holding
        /// this kind of certificate».
        fn holding(mut self, certificate_type: &'static str) -> Self {
            self.signing_type = Some(certificate_type);
            self
        }
        fn sql_touching_the_certificate_table(&self) -> Vec<String> {
            self.seen_sql
                .lock()
                .unwrap()
                .iter()
                .filter(|s| s.contains("_hub_certificate"))
                .cloned()
                .collect()
        }
    }

    #[async_trait::async_trait]
    impl NativeHost for SlotHost {
        async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
            self.seen_sql.lock().unwrap().push(sql.to_string());
            if sql.contains("_hub_certificate") {
                Ok(self.stored_rows.clone())
            } else if sql.contains("verifactu_config") {
                Ok(vec![json!({ "hub_id": "h1", "environment": "testing" })])
            } else {
                Ok(vec![])
            }
        }
        async fn certificate_signing_kind(&self, _hub_id: &str) -> Result<Option<String>> {
            Ok(self.signing.map(str::to_string))
        }
        async fn certificate_signing_type(&self, _hub_id: &str) -> Result<Option<String>> {
            Ok(self.signing_type.map(str::to_string))
        }
    }

    /// **A hub whose only certificate is the DELEGATED one can transmit** (ADR-0202 §2.1 — hub#319).
    ///
    /// `build_identity` used to demand the business's own certificate and send the user to
    /// «Ajustes → Negocio». ERPlora's certificate signs on their behalf, so the engine has to accept
    /// it — and it learns that from the core, which owns the fallback.
    #[tokio::test]
    async fn a_delegated_only_hub_can_transmit() {
        let host = SlotHost::new(Some("delegated"), vec![]);
        let cfg = read_config(&host, "h1").await.unwrap().unwrap();
        assert!(
            has_certificate(&cfg),
            "con el delegado el motor SÍ puede transmitir"
        );
        assert_eq!(signing_kind(&cfg), "delegated");
    }

    /// The own certificate wins — the fallback is an ORDER, not a preference, and the engine reports
    /// the slot the core actually picked.
    #[tokio::test]
    async fn the_own_certificate_is_the_one_reported_when_both_slots_are_full() {
        let host = SlotHost::new(Some("own"), vec![]);
        let cfg = read_config(&host, "h1").await.unwrap().unwrap();
        assert!(has_certificate(&cfg));
        assert_eq!(signing_kind(&cfg), "own");
    }

    /// No slot at all ⇒ nothing to sign with. The engine keeps failing CLOSED.
    #[tokio::test]
    async fn a_hub_with_neither_slot_cannot_transmit() {
        let host = SlotHost::new(None, vec![]);
        let cfg = read_config(&host, "h1").await.unwrap().unwrap();
        assert!(!has_certificate(&cfg));
        assert_eq!(signing_kind(&cfg), "");
    }

    /// **The AEAT entry point follows what the certificate IS, as the CORE read it**
    /// (ADR-0202 §2.1 — hub#320, corrected by hub#470).
    ///
    /// The whole chain in one assertion — core → `read_config` → `certificate_type` → URL — because
    /// that is the seam #317/#318/#319 kept having to repair: the answer is fetched ONCE and
    /// travels, instead of being re-derived from `_hub_certificate` by whoever needs it next. A hub
    /// POSTing to the wrong door has every record rejected, and a rejection is not a link in the
    /// chain (ADR-0189).
    #[tokio::test]
    async fn the_entry_point_follows_what_the_certificate_is() {
        let seal = read_config(
            &SlotHost::new(Some("delegated"), vec![]).holding("seal"),
            "h1",
        )
        .await
        .unwrap()
        .unwrap();
        assert_eq!(
            transmission_endpoint(&seal),
            "https://prewww10.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );

        let representative = read_config(
            &SlotHost::new(Some("own"), vec![]).holding("representative"),
            "h1",
        )
        .await
        .unwrap()
        .unwrap();
        assert_eq!(
            transmission_endpoint(&representative),
            "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
    }

    /// 🔴 **The bug hub#470 closes, through the whole seam.** A hub whose DELEGATED slot holds a
    /// *representative* container — which is exactly what would happen the day ERPlora's own
    /// `.p12` (`…_R_…`) were uploaded to the control plane — must transmit through the holder's
    /// door. Routing on the slot sent it to `www10`, where the AEAT would have rejected every
    /// record of every delegated hub, one at a time and with nothing to warn anybody.
    ///
    /// And the mirror: a business that uploads its OWN entity seal reaches the seal's door. The
    /// slot no longer decides in either direction.
    #[tokio::test]
    async fn the_slot_does_not_decide_the_entry_point_in_either_direction() {
        let delegated_representative = read_config(
            &SlotHost::new(Some("delegated"), vec![]).holding("representative"),
            "h1",
        )
        .await
        .unwrap()
        .unwrap();
        assert_eq!(
            signing_kind(&delegated_representative),
            "delegated",
            "the slot is still reported — it is what picks the fallback and the `Representante`"
        );
        assert_eq!(
            transmission_endpoint(&delegated_representative),
            "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP",
            "a representative certificate goes to the holder's door even from the delegated slot"
        );

        let own_seal = read_config(&SlotHost::new(Some("own"), vec![]).holding("seal"), "h1")
            .await
            .unwrap()
            .unwrap();
        assert_eq!(
            transmission_endpoint(&own_seal),
            "https://prewww10.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP",
            "a business's own entity seal goes to the seal's door"
        );
    }

    /// **A core that cannot vouch for the type routes to the holder's door**, and it still reports
    /// that it can sign. That is the state of every hub deployed before hub#470 whose row has no
    /// type stored and whose container the classifier cannot read — and `prewww1` is where all of
    /// them already went.
    #[tokio::test]
    async fn a_certificate_the_core_cannot_classify_keeps_the_holder_entry_point() {
        let cfg = read_config(&SlotHost::new(Some("delegated"), vec![]), "h1")
            .await
            .unwrap()
            .unwrap();
        assert!(
            has_certificate(&cfg),
            "not knowing the type does not stop it signing"
        );
        assert_eq!(signing_type(&cfg), "");
        assert_eq!(
            transmission_endpoint(&cfg),
            "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
    }

    /// **The seam multiplies the two axes, and neither one is allowed to swallow the other.** The
    /// certificate decides the door; the environment decides the tax agency that is actually
    /// listening. Getting the door wrong is a rejection; getting the environment wrong is a real
    /// invoice accepted where it does not belong, and a remitted record is never re-sent (ADR-0189).
    #[test]
    fn the_seam_resolves_the_environment_and_the_certificate_from_the_same_config() {
        let config = |environment: &str, certificate_type: &str| {
            json!({
                "environment": environment,
                "certificate_source": "core",
                "certificate_type": certificate_type,
            })
        };
        assert_eq!(
            transmission_endpoint(&config("production", "seal")),
            "https://www10.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
        assert_eq!(
            transmission_endpoint(&config("production", "representative")),
            "https://www1.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
        assert_eq!(
            transmission_endpoint(&config("testing", "seal")),
            "https://prewww10.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
        assert_eq!(
            transmission_endpoint(&config("testing", "representative")),
            "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
        // An unconfigured `environment` is preproduction, on BOTH doors (`environment_of`).
        assert_eq!(
            transmission_endpoint(&json!({ "certificate_type": "seal" })),
            "https://prewww10.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
        assert_eq!(
            transmission_endpoint(&json!({})),
            "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
        // And the SLOT is not the axis: a config carrying only `certificate_kind` says nothing
        // about the door, which is the confusion hub#470 removed.
        assert_eq!(
            transmission_endpoint(&json!({ "certificate_kind": "delegated" })),
            "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        );
    }

    /// Recovering the chain has to talk to the door that issued it: the consult resolves its entry
    /// point from the same two axes as the alta, so a hub signing with a seal can also re-anchor
    /// (hub#287).
    #[test]
    fn the_consult_and_the_transmission_share_the_entry_point() {
        for environment in ["testing", "production"] {
            for certificate_type in ["representative", "seal", "", "delegated"] {
                let cfg = json!({
                    "environment": environment,
                    "certificate_type": certificate_type,
                });
                assert_eq!(
                    consult_endpoint_of(&cfg),
                    transmission_endpoint(&cfg),
                    "({environment}, {certificate_type})"
                );
            }
        }
    }

    /// **`transmission_endpoint_for` is the same answer, from the host** — the public entry the
    /// cross-crate e2e uses (`crates/runtime/tests/certificate_type_e2e.rs`). If it ever stopped
    /// agreeing with the internal one, that e2e would be pinning a second implementation instead of
    /// the real path.
    #[tokio::test]
    async fn the_public_entry_point_helper_agrees_with_the_internal_one() {
        for certificate_type in ["seal", "representative"] {
            let host = SlotHost::new(Some("delegated"), vec![]).holding(certificate_type);
            let cfg = read_config(&host, "h1").await.unwrap().unwrap();
            assert_eq!(
                transmission_endpoint_for(&host, "h1").await.unwrap(),
                transmission_endpoint(&cfg),
                "{certificate_type}"
            );
        }
    }

    /// **The engine asks the CORE which certificate signs; it does not read the table.**
    ///
    /// `read_config` used to probe `_hub_certificate` with `SELECT … LIMIT 1` and no `kind`, which
    /// re-derived a core rule from raw SQL: with two rows it picked whichever the database handed
    /// back first, and it counted rows the core deliberately refuses to select (hub#316:
    /// «a `kind` this runtime does not know is not guessed at»). Here the table holds such a row and
    /// the core says there is nothing to sign with — the engine must believe the core, or it would
    /// try to transmit with a certificate that cannot be loaded.
    #[tokio::test]
    async fn a_slot_the_core_refuses_to_select_does_not_count_as_a_certificate() {
        let host = SlotHost::new(
            None,
            vec![json!({ "kind": "some_future_slot", "pkcs12_b64": "QUJD", "password": "secret" })],
        );
        let cfg = read_config(&host, "h1").await.unwrap().unwrap();
        assert!(
            !has_certificate(&cfg),
            "la fila existe en la tabla pero el core NO firma con ella: manda el core"
        );
    }

    /// **The `.p12` and its password are never even SELECTed by the module** (ADR-0079).
    ///
    /// The old probe read `pkcs12_b64, password` just to test them for emptiness. Those columns are
    /// encrypted at rest since hub#114, but legacy rows are still plaintext — so the module was
    /// pulling the business's certificate password into its own memory to answer a yes/no question
    /// the core can answer without decrypting anything.
    #[tokio::test]
    async fn the_engine_never_selects_the_certificate_bytes_or_its_password() {
        let host = SlotHost::new(Some("own"), vec![]);
        read_config(&host, "h1").await.unwrap();
        assert!(
            host.sql_touching_the_certificate_table().is_empty(),
            "el módulo no consulta `_hub_certificate`: pregunta al core. SQL visto: {:?}",
            host.sql_touching_the_certificate_table()
        );
    }

    /// **Un host que no implementa la capacidad NO puede firmar — falla CERRADO.**
    ///
    /// El default de `NativeHost::certificate_signing_kind` es `None` a propósito, y esa decisión es
    /// de seguridad, no de comodidad: `read_config` marca `certificate_source = "core"` ante
    /// **cualquier** `Some`, así que un default con nombre —vacío o inventado— le diría al motor que
    /// puede transmitir a la AEAT sobre un host que ni siquiera sabe entregarle una identidad. Lo
    /// encontró la corrida de mutación: sustituir el default por `Ok(Some(""))` o `Ok(Some("xyzzy"))`
    /// no rompía nada.
    #[tokio::test]
    async fn a_host_without_the_certificate_capability_cannot_sign() {
        /// Lo mínimo que exige el trait: `read` y nada más.
        struct BareHost;
        #[async_trait::async_trait]
        impl NativeHost for BareHost {
            async fn read(&self, sql: &str, _p: &Params) -> Result<Vec<Json>> {
                if sql.contains("verifactu_config") {
                    Ok(vec![json!({ "hub_id": "h1", "environment": "testing" })])
                } else {
                    Ok(vec![])
                }
            }
        }

        assert!(
            !can_sign(&BareHost, "h1").await.unwrap(),
            "sin la capacidad no hay con qué firmar: el motor NO transmite"
        );
        let cfg = read_config(&BareHost, "h1").await.unwrap().unwrap();
        assert!(
            cfg.get("certificate_source").is_none(),
            "y no se marca un certificado que no hay"
        );
        assert!(build_identity(&BareHost, "h1", &cfg).await.is_err());
    }

    /// **`can_sign` IS `build_identity`'s gate, and it is pinned here too.**
    ///
    /// Its only consumer is the coherence e2e of hub#319, which lives in the `erplora-runtime`
    /// package — so a mutation run scoped to THIS package leaves it alive with nothing to say. That
    /// is a hole in the evidence, not in the code: a `pub` predicate that decides whether a hub
    /// transmits to the AEAT has to be pinned where it is defined, so it survives whatever the
    /// cross-package test does later.
    #[tokio::test]
    async fn can_sign_answers_exactly_what_build_identity_gates_on() {
        for (signing, expected) in [
            (Some("delegated"), true),
            (Some("own"), true),
            (None, false),
        ] {
            let host = SlotHost::new(signing, vec![]);
            assert_eq!(
                can_sign(&host, "h1").await.unwrap(),
                expected,
                "can_sign con el slot {signing:?}"
            );
            // Y es literalmente el predicado del gate sobre la misma config: si los dos pudieran
            // diferir, el motor rechazaría lo que el runtime ya dio por bueno.
            let cfg = read_config(&host, "h1").await.unwrap().unwrap();
            assert_eq!(
                can_sign(&host, "h1").await.unwrap(),
                has_certificate(&cfg),
                "can_sign y el gate de build_identity tienen que ser la MISMA respuesta ({signing:?})"
            );
        }
    }

    /// **The error names the real cause.** «Súbelo en Ajustes → Negocio» is only half the story once
    /// a delegated certificate exists: reaching here means the business uploaded none **and** the
    /// control plane never handed one down. Telling the user only about their half sends them to a
    /// screen that cannot fix an ERPlora-side gap.
    #[tokio::test]
    async fn the_error_without_any_certificate_names_both_halves() {
        let host = SlotHost::new(None, vec![]);
        let cfg = read_config(&host, "h1").await.unwrap().unwrap();
        let err = build_identity(&host, "h1", &cfg)
            .await
            .unwrap_err()
            .to_string();
        assert!(
            err.contains("Ajustes → Negocio"),
            "sigue diciendo dónde subir el propio: {err}"
        );
        assert!(
            err.to_lowercase().contains("erplora"),
            "y que ERPlora tampoco entregó uno delegado: {err}"
        );
    }
}

#[cfg(test)]
mod certificate_refetch_trigger_tests {
    use super::{request_certificate_refetch_on_tls, VerifactuError};
    use erplora_runtime::certificate_refetch::RefetchSignal;

    /// El slot que firmaba cuando falló el handshake (ver `signing_kind`).
    const DELEGATED: &str = "delegated";
    const OWN: &str = "own";

    /// 🔒 The failure IS the trigger (ADR-0202 §2 point 4). A rejected client certificate is the
    /// one transport failure that a retry cannot fix and a refetch can.
    #[test]
    fn a_tls_failure_asks_for_the_certificate_to_be_refetched() {
        let signal = RefetchSignal::new();
        request_certificate_refetch_on_tls(
            &VerifactuError::Tls("conexión AEAT: invalid peer certificate".into()),
            DELEGATED,
            &signal,
        );
        assert!(
            signal.take(),
            "un rechazo del certificado tiene que pedir el vigente"
        );
    }

    /// 🔒 **El certificado que falló tiene que ser el DELEGADO** (hub#319).
    ///
    /// El refetch baja el certificado de ERPlora. Si quien se identificó ante la AEAT fue el
    /// certificado **propio** del negocio —caducado, revocado, con la contraseña cambiada—, pedir el
    /// delegado no arregla nada: el propio sigue ganando el fallback (ADR-0202 §2.1) y el siguiente
    /// intento vuelve a fallar igual. Lo único que consigue es **gastar el presupuesto**: la cola de
    /// contingencia reintenta cada 5/10/20/40/60 min, así que un certificado propio roto se comería
    /// las 6/h del hub y dejaría sin cupo al disparador que sí sirve —el del latido— justo cuando el
    /// plano de control rote de verdad.
    ///
    /// Mismo defecto de frontera que hub#317 y hub#318 arreglaron dos veces: una señal que describe
    /// el slot delegado levantada desde un contexto que podía estar hablando del propio.
    #[test]
    fn a_tls_failure_of_the_businesss_own_certificate_asks_for_nothing() {
        let signal = RefetchSignal::new();
        request_certificate_refetch_on_tls(
            &VerifactuError::Tls("conexión AEAT: received fatal alert: CertificateExpired".into()),
            OWN,
            &signal,
        );
        assert!(
            !signal.take(),
            "el certificado del negocio no se arregla bajando el de ERPlora — y gastaría el cupo"
        );
    }

    /// Sin certificado no se llega a abrir el canal, pero si se llegase tampoco se pide nada: el
    /// cupo no se gasta en una pregunta cuya respuesta ya se sabe que no se está usando.
    #[test]
    fn a_tls_failure_without_a_known_signer_asks_for_nothing() {
        let signal = RefetchSignal::new();
        request_certificate_refetch_on_tls(
            &VerifactuError::Tls("conexión AEAT: invalid peer certificate".into()),
            "",
            &signal,
        );
        assert!(!signal.take());
    }

    /// 🔒 **The AEAT being down does not make the hub ask for a private key.** These arrive once
    /// per record the contingency queue drains, and asking on each one would spend the control
    /// plane's 20/h allowance on an outage that a refetch cannot fix.
    #[test]
    fn a_network_failure_does_not() {
        let signal = RefetchSignal::new();
        for error in [
            VerifactuError::Transmission("conexión AEAT: operation timed out".into()),
            VerifactuError::Transmission("AEAT HTTP 503: servicio no disponible".into()),
            VerifactuError::Certificate("certificado del negocio no configurado".into()),
            VerifactuError::Consult("SOAP Fault".into()),
        ] {
            request_certificate_refetch_on_tls(&error, DELEGATED, &signal);
        }
        assert!(
            !signal.take(),
            "solo el fallo del canal TLS dispara el refetch; los demás se reintentan por la cola \
             de contingencia"
        );
    }

    /// Many stranded records, one broken certificate, ONE refetch: the signal coalesces, which is
    /// what keeps a queue drain from emptying the hourly allowance in a single pass.
    #[test]
    fn a_whole_queue_drain_failing_the_same_handshake_asks_once() {
        let signal = RefetchSignal::new();
        for _ in 0..200 {
            request_certificate_refetch_on_tls(
                &VerifactuError::Tls(
                    "conexión AEAT: received fatal alert: CertificateRevoked".into(),
                ),
                DELEGATED,
                &signal,
            );
        }
        assert!(signal.take());
        assert!(
            !signal.take(),
            "200 registros varados piden UN refetch, no 200"
        );
    }
}
