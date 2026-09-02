//! Fiscal profile, business certificate and regime declaration — split out of `lib.rs` verbatim (hub#1403).

use crate::*;

impl Runtime {
    /// The hub's **fiscal profile** (ADR-0273, hub#549): what this hub owes, who it owes it as, and
    /// how far along it is. `None` only before [`Runtime::ensure_system_tables`] has ever run —
    /// booting resolves it. The authority on the obligation lives here, in the core, so that no
    /// module can take it away by being uninstalled.
    pub async fn fiscal_profile(&self) -> Result<Option<fiscal_profile::FiscalProfile>> {
        fiscal_profile::load(self.db.as_ref(), &self.hub_id).await
    }

    /// **What this hub owes right now** (ADR-0273 D2, hub#550): the stored status resolved against
    /// what is actually mounted. This is where `BLOCKED` comes from — derived on every read, never
    /// stored, so it is fixed by fixing the fact and cannot outlive the bug that caused it.
    ///
    /// Read-only: it never writes. The write side is [`Runtime::refresh_fiscal_profile`].
    pub async fn fiscal_mode(&self) -> Result<fiscal_profile::FiscalMode> {
        let profile = fiscal_profile::ensure(self.db.as_ref(), &self.hub_id).await?;
        Ok(fiscal_profile::determine_fiscal_mode(
            &profile,
            &self.registry,
            &self.hub_id,
        ))
    }

    /// Resolves the fiscal profile against the world and returns the effective mode (ADR-0273
    /// D2/D4, hub#550). The host calls it at boot **after re-hydrating the registry** — that is the
    /// first instant both halves of the answer exist: what the hub owes, and who is mounted to
    /// comply. Idempotent, so every restart and every redeploy runs it.
    pub async fn refresh_fiscal_profile(&self) -> Result<fiscal_profile::FiscalMode> {
        fiscal_profile::refresh(self.db.as_ref(), &self.registry, &self.hub_id).await
    }

    /// **El go-live** (ADR-0273 D3, hub#551): `READY → ACTIVE`, que ES `testing → production`.
    /// Una sola transición y un solo sitio donde se guarda. Exige que el perfil esté `READY` —la
    /// misma condición que enseña la checklist— y que el hub pueda hacerlo (una demo no).
    pub async fn fiscal_go_live(&self) -> Result<fiscal_profile::FiscalProfile> {
        fiscal_profile::go_live(self.db.as_ref(), &self.hub_id).await
    }

    /// **Apaga el go-live**, y solo mientras no haya salido ni un registro hacia la Hacienda real
    /// (ADR-0273 D3). Lo irreversible es el primer ENVÍO, no el clic: quien activa por error y se
    /// da cuenta antes de facturar puede volver.
    pub async fn fiscal_stand_down(&self) -> Result<fiscal_profile::FiscalProfile> {
        fiscal_profile::stand_down(self.db.as_ref(), &self.hub_id).await
    }

    /// **Cese de actividad** (ADR-0273 D2, hub#557): el negocio cierra y deja de facturar, pero
    /// sigue consultando y exportando sus libros. `actor` = quién lo decidió, y sin él no se
    /// cierra: una acción irreversible sin nadie detrás en el registro no es una traza.
    ///
    /// **Es función de producto, no compliance** — siendo VERI\*FACTU-only no hay registro de
    /// eventos que remitir, y el cese que existe es la baja censal (036/037) del obligado, que
    /// presenta él o su gestoría. Lo que compra es que quien cesó no siga facturando por error.
    ///
    /// No tiene vuelta: no hay `CLOSED → ACTIVE`. La **sesión admin y la confirmación** las pone
    /// la puerta que llama, igual que en el go-live.
    pub async fn fiscal_close(&self, actor: &str) -> Result<fiscal_profile::FiscalProfile> {
        fiscal_profile::close(self.db.as_ref(), &self.hub_id, actor).await
    }

    /// **Adopta una instalación AJENA** (ADR-0273 D8, hub#558): el hub se movió de despliegue —o se
    /// restauró en otro sitio—, el `hub_id` cambió y estas filas las escribió otra instalación.
    /// Como `NumeroInstalacion = hub_id` (ADR-0202), otro `hub_id` es **otro SIF y otra cadena**,
    /// que arranca con `PrimerRegistro=S`.
    ///
    /// **Jamás automático**: el arranque solo lo **marca** (`needs_review` + `BLOCKED` derivado) y
    /// el gate solo **rechaza**. Adoptar en silencio la instalación de otro es exactamente cómo se
    /// mezclan dos cadenas, y un registro ya remitido ni se reenvía ni se borra (ADR-0189). Sesión
    /// admin y confirmación las pone la puerta que llama; `actor` es la traza.
    pub async fn fiscal_adopt_installation(
        &self,
        actor: &str,
    ) -> Result<fiscal_profile::FiscalProfile> {
        fiscal_profile::adopt_installation(self.db.as_ref(), &self.hub_id, actor).await
    }

    /// Sube/reemplaza el certificado fiscal **del negocio** (ADR-0079). `by` = `hub_user:<id>` admin.
    ///
    /// Ata el slot [`certificate::CertificateKind::Own`] en el ÚNICO punto por el que entra un `.p12`
    /// del cliente (`PUT /api/business/certificate`): el certificado delegado de ERPlora lo escribe
    /// el plano de control por su propia vía (hub#317), nunca esta.
    ///
    /// **El TIPO sale de los bytes, y aquí no hay nada con lo que contrastarlo** (hub#470). Al
    /// certificado delegado lo acompaña una declaración del plano de control que
    /// [`certificate::set_delegated`] comprueba; este lo sube su dueño directamente, así que no hay
    /// frontera que cruzar ni segunda opinión que discrepe: el contenedor es la única fuente. Un
    /// negocio que suba un **sello de entidad** propio entra por `www10` sin tocar nada, que es
    /// justamente lo que la AEAT segrega.
    /// **Un hub de DEMO no sube certificado** (ADR-0197 §4, hub#376). El cierre va aquí, en la
    /// puerta del `own`, y NO en [`certificate::set`]: el certificado **delegado** de ERPlora sigue
    /// llegando por su vía (`set_delegated`, hub#317) — es la distribución normal de la flota y una
    /// demo la recibe como cualquier otro hub. Lo que no puede es tener identidad fiscal PROPIA.
    pub async fn set_business_certificate(
        &self,
        pkcs12_b64: &str,
        password: &str,
        by: &str,
    ) -> Result<()> {
        self.refuse_if_demo(DemoLock::BusinessCertificate)?;
        certificate::set(
            self.db.as_ref(),
            &self.hub_id,
            certificate::CertificateKind::Own,
            pkcs12_b64,
            password,
            by,
            // Sin versión: la del plano de control describe la ROTACIÓN CENTRAL del certificado
            // delegado (ADR-0202 §2.5). El del negocio lo sube y lo renueva su dueño, así que no hay
            // número de flota que le corresponda y ponerle uno haría que este hub reportase como
            // instalada una versión de ERPlora que no tiene.
            None,
            certificate::derive_certificate_type(pkcs12_b64, password),
        )
        .await
    }

    /// Estado de los certificados del hub (sin bytes ni contraseña): el del negocio en la raíz —
    /// como siempre— más `slots`/`active` (ADR-0202 §2.1).
    pub async fn business_certificate_status(&self) -> Result<Json> {
        certificate::status(self.db.as_ref(), &self.hub_id).await
    }

    /// Elimina el certificado **del negocio**. El delegado no se toca: no es del cliente.
    ///
    /// Cerrado también en una demo (hub#376): «no reemplazable» sin «no borrable» sería un
    /// reemplazo en dos pasos.
    pub async fn delete_business_certificate(&self) -> Result<()> {
        self.refuse_if_demo(DemoLock::BusinessCertificate)?;
        certificate::delete(
            self.db.as_ref(),
            &self.hub_id,
            certificate::CertificateKind::Own,
        )
        .await
    }

    /// Escribe el techo de la simplificada que declara un módulo fiscal (hub#1010). Lo llama el
    /// instalador con el bloque `fiscal_regime` del manifest; expuesto para poder probar la puerta
    /// sin montar un zip.
    pub async fn apply_fiscal_regime_declaration(
        &self,
        country_code: &str,
        regime_key: &str,
        max_cents: Option<i64>,
    ) -> Result<()> {
        fiscal_profile::apply_regime_declaration(
            self.db.as_ref(),
            country_code,
            regime_key,
            max_cents,
        )
        .await
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::testutil::fresh_db;

    // ── Certificado del negocio CERRADO en una demo (ADR-0197 §4 · hub#376) ────────────────

    /// 🔴 Por la puerta que la APLICA: `set_business_certificate` es lo que llama
    /// `PUT /api/business/certificate`. Y falla ANTES de la clave maestra: la demo no llega
    /// siquiera a intentar cifrar (`HUB_SECRETS_KEY` ni hace falta).
    #[tokio::test]
    async fn a_demo_hub_cannot_upload_a_business_certificate() {
        let mut rt = Runtime::new(Box::new(fresh_db().await));
        rt.set_demo_hub(true);
        let err = rt
            .set_business_certificate("Zm9v", "s3cret", "hub_user:1")
            .await
            .unwrap_err();
        assert!(
            matches!(
                err,
                RuntimeError::DemoLocked {
                    lock: DemoLock::BusinessCertificate
                }
            ),
            "got {err:?}"
        );
    }

    /// «No reemplazable» sin «no borrable» sería un reemplazo en dos pasos: borrar y subir.
    #[tokio::test]
    async fn a_demo_hub_cannot_delete_the_business_certificate_either() {
        let mut rt = Runtime::new(Box::new(fresh_db().await));
        rt.set_demo_hub(true);
        let err = rt.delete_business_certificate().await.unwrap_err();
        assert!(
            matches!(
                err,
                RuntimeError::DemoLocked {
                    lock: DemoLock::BusinessCertificate
                }
            ),
            "got {err:?}"
        );
    }

    /// 🔴 La otra dirección: un hub REAL sube su `.p12` como siempre. Si esta guarda se escapase a
    /// un hub de pago, el negocio no podría remitir a la AEAT — el peor fallo posible, y mudo.
    /// (Aquí falla por la clave maestra ausente, que es la guarda de al lado: lo que importa es
    /// que NO es `DemoLocked`, o sea que la puerta está abierta para él.)
    #[tokio::test]
    async fn a_real_hub_uploads_its_certificate_as_always() {
        let rt = Runtime::new(Box::new(fresh_db().await));
        assert!(!rt.is_demo_hub(), "el default de un runtime es hub normal");
        let err = rt
            .set_business_certificate("Zm9v", "s3cret", "hub_user:1")
            .await
            .unwrap_err();
        assert!(
            !matches!(err, RuntimeError::DemoLocked { .. }),
            "un hub real no puede toparse con el cierre de la demo: {err:?}"
        );
    }

    /// Leer el estado del certificado NO se cierra: la demo tiene que poder EXPLICAR que no tiene
    /// uno (es media pantalla de VeriFactu). El cierre es de escritura, no un modo ciego.
    #[tokio::test]
    async fn a_demo_hub_still_reads_its_certificate_status() {
        let mut rt = Runtime::new(Box::new(fresh_db().await));
        rt.ensure_system_tables().await.expect("system tables");
        rt.set_demo_hub(true);
        let status = rt
            .business_certificate_status()
            .await
            .expect("el estado del certificado se lee siempre");
        assert_eq!(status["present"], serde_json::json!(false));
    }
}
