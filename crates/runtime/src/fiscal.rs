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
    /// **El TIPO sale de los bytes, y no hay nada con lo que contrastarlo** (hub#470): el
    /// certificado lo sube su dueño directamente, así que no hay frontera que cruzar ni segunda
    /// opinión que discrepe — el contenedor es la única fuente. Un negocio que suba un **sello de
    /// entidad** propio entra por `www10` sin tocar nada, que es justamente lo que la AEAT segrega.
    ///
    /// **A DEMO hub uploads its certificate too** (hub#1848, amends ADR-0197 §4): every PRE hub
    /// carries the demo flag, and that is where a business tests its own certificate. What keeps a
    /// demo away from the real AEAT is the environment pinned to `testing`, not this door.
    pub async fn set_business_certificate(
        &self,
        pkcs12_b64: &str,
        password: &str,
        by: &str,
    ) -> Result<()> {
        certificate::set(
            self.db.as_ref(),
            &self.hub_id,
            certificate::CertificateKind::Own,
            pkcs12_b64,
            password,
            by,
            certificate::derive_certificate_type(pkcs12_b64, password),
            certificate::derive_not_after(pkcs12_b64, password),
        )
        .await
    }

    /// **«Usar mi propio certificado»: on or off, keeping the certificate** (Ioan, 2026-09-15 —
    /// amends ADR-0202 §2.4 and ADR-0320 §1).
    ///
    /// The two routes to the tax authority are EXCLUSIVE and the owner PICKS one: their own `.p12`,
    /// or ERPlora's Sello on their behalf. Before this, the route was «own if uploaded» and the only
    /// way to hand filing to ERPlora was deleting the certificate.
    ///
    /// * **On** needs an uploaded certificate — otherwise [`certificate::OWN_CERTIFICATE_NOT_UPLOADED`]
    ///   and nothing changes.
    /// * **Off** in PRODUCTION needs ERPlora to be able to file for real on the taxpayer's behalf, so
    ///   the switch never leaves a live hub without a road: an approved (`vigente`) representation
    ///   grant — otherwise [`fiscal_profile::NO_REPRESENTATION`] — AND the enrolled machine identity
    ///   of the fiscal cell — otherwise [`certificate::GATEWAY_NOT_ENROLLED`]. In `testing` it is
    ///   allowed without either, so the ERPlora road can be tried before the paperwork is done
    ///   (records stay pending until it is).
    /// * Off with nothing uploaded is a no-op: there is nothing to stop using.
    pub async fn set_business_certificate_use(&self, enabled: bool) -> Result<()> {
        let db = self.db.as_ref();
        let uploaded = certificate::slot_status(db, &self.hub_id, certificate::CertificateKind::Own)
            .await?
            .get("present")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
        if enabled {
            if !uploaded {
                return Err(RuntimeError::Domain {
                    code: certificate::OWN_CERTIFICATE_NOT_UPLOADED.to_string(),
                    message: "there is no business certificate uploaded to file with: upload the \
                              .p12 first"
                        .to_string(),
                });
            }
        } else {
            if !uploaded {
                return Ok(());
            }
            let production = fiscal_profile::load(db, &self.hub_id)
                .await?
                .filter(|profile| profile.environment == fiscal_profile::ENV_PRODUCTION);
            if let Some(profile) = production {
                // The road this switch would leave behind is ERPlora's, and whether a live hub can
                // file on it is ONE rule (hub#1935) — the same one the dispatcher refuses a sale
                // with. Two copies would be how the switch and the till end up disagreeing.
                let enrolled = crate::gateway_identity::is_enrolled(db, &self.hub_id).await?;
                // `false`: the road left behind is ERPlora's, where no certificate of the business
                // signs, so its expiry (hub#1940) cannot be what is missing there.
                match fiscal_profile::filing_gap(
                    &profile,
                    certificate::ROUTE_DELEGATED,
                    enrolled,
                    false,
                ) {
                    Some(fiscal_profile::NO_REPRESENTATION) => {
                        return Err(RuntimeError::Domain {
                            code: fiscal_profile::NO_REPRESENTATION.to_string(),
                            message: "this hub files for real: ERPlora can only file on the \
                                      taxpayer's behalf once their representation grant is \
                                      approved"
                                .to_string(),
                        });
                    }
                    Some(code) => {
                        return Err(RuntimeError::Domain {
                            code: code.to_string(),
                            message: "this hub files for real and its secure connection to \
                                      ERPlora is not signed yet: switching the certificate off \
                                      would leave it with no way to file"
                                .to_string(),
                        });
                    }
                    None => {}
                }
            }
        }
        certificate::set_use_for_transmission(
            db,
            &self.hub_id,
            certificate::CertificateKind::Own,
            enabled,
        )
        .await?;
        Ok(())
    }

    /// Estado de los certificados del hub (sin bytes ni contraseña): el del negocio en la raíz —
    /// como siempre— más `slots`/`active` (ADR-0202 §2.1).
    pub async fn business_certificate_status(&self) -> Result<Json> {
        certificate::status(self.db.as_ref(), &self.hub_id).await
    }

    /// Removes the **business** certificate. The delegated one is not touched: it is not the
    /// customer's.
    pub async fn delete_business_certificate(&self) -> Result<()> {
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

    // ── A DEMO hub holds its own business certificate like any hub (hub#1848) ─────────────

    /// 🔴 Through the door that APPLIES it: `set_business_certificate` is what
    /// `PUT /api/business/certificate` calls. A demo gets exactly the refusal a real hub gets for
    /// the same bytes (here the missing master key, the guard next door) and never a demo closure.
    #[tokio::test]
    async fn a_demo_hub_uploads_a_business_certificate_like_a_real_hub() {
        let real = Runtime::new(Box::new(fresh_db().await));
        let mut demo = Runtime::new(Box::new(fresh_db().await));
        demo.set_demo_hub(true);

        let real_err = real
            .set_business_certificate("Zm9v", "s3cret", "hub_user:1")
            .await
            .unwrap_err();
        let demo_err = demo
            .set_business_certificate("Zm9v", "s3cret", "hub_user:1")
            .await
            .unwrap_err();
        assert!(
            !matches!(demo_err, RuntimeError::DemoLocked { .. }),
            "a demo admin is not refused their own certificate: {demo_err:?}"
        );
        assert_eq!(demo_err.to_string(), real_err.to_string());
    }

    /// Removing it is open too: the admin who uploaded the wrong file takes it back.
    #[tokio::test]
    async fn a_demo_hub_deletes_its_business_certificate() {
        let mut rt = Runtime::new(Box::new(fresh_db().await));
        rt.ensure_system_tables().await.expect("system tables");
        rt.set_demo_hub(true);
        rt.delete_business_certificate()
            .await
            .expect("a demo removes its own certificate like any hub");
    }

    /// 🔴 A REAL hub uploads its `.p12` as always. (It fails here on the missing master key, the
    /// guard next door: what matters is that it is NOT `DemoLocked`.)
    #[tokio::test]
    async fn a_real_hub_uploads_its_certificate_as_always() {
        let rt = Runtime::new(Box::new(fresh_db().await));
        assert!(!rt.is_demo_hub(), "a runtime defaults to a normal hub");
        let err = rt
            .set_business_certificate("Zm9v", "s3cret", "hub_user:1")
            .await
            .unwrap_err();
        assert!(
            !matches!(err, RuntimeError::DemoLocked { .. }),
            "a real hub never meets a demo closure: {err:?}"
        );
    }

    /// A demo reads its certificate status: it is half of the VeriFactu screen.
    #[tokio::test]
    async fn a_demo_hub_still_reads_its_certificate_status() {
        let mut rt = Runtime::new(Box::new(fresh_db().await));
        rt.ensure_system_tables().await.expect("system tables");
        rt.set_demo_hub(true);
        let status = rt
            .business_certificate_status()
            .await
            .expect("the certificate status is always readable");
        assert_eq!(status["present"], serde_json::json!(false));
    }
}
