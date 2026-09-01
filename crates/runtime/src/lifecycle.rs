//! Runtime construction, host configuration and shell accessors — split out of `lib.rs` verbatim (hub#1403).

use crate::*;

impl Runtime {
    pub fn new(db: Box<dyn DatabaseAdapter>) -> Self {
        Self {
            db,
            registry: Registry::new(),
            hub_id: DEV_HUB_ID.to_string(),
            elevation: elevation::Grants::new(),
        }
    }

    /// Igual que [`Runtime::new`] pero fijando el `hub_id` del despliegue (lo usa el host real;
    /// el `hub_id` viene de `HubConfig.hub_id`, inyectado por el despliegue y no spoofable).
    pub fn with_hub_id(db: Box<dyn DatabaseAdapter>, hub_id: impl Into<String>) -> Self {
        Self {
            db,
            registry: Registry::new(),
            hub_id: hub_id.into(),
            elevation: elevation::Grants::new(),
        }
    }

    /// `hub_id` del despliegue de este runtime.
    pub fn hub_id(&self) -> &str {
        &self.hub_id
    }

    /// Adopta el `hub_id` real devuelto por el Cloud durante el bootstrap de la máquina.
    ///
    /// El shell Tauri arranca antes de que exista una vinculación y, por tanto, construye el
    /// runtime con [`DEV_HUB_ID`]. En cuanto el login Cloud registra el dispositivo, el host
    /// actualiza la identidad viva y llama a este método **antes de abrir la sesión local**. Desde
    /// ese instante instalaciones, ajustes, perfiles y comandos quedan scopeados por el UUID real
    /// sin exigir un reinicio de la aplicación.
    ///
    /// Esta operación pertenece exclusivamente al bootstrap: una máquina ya vinculada carga el
    /// UUID persistido antes de construir el runtime y no vuelve a cambiarlo durante su vida útil.
    pub fn adopt_hub_id(&mut self, hub_id: impl Into<String>) {
        self.hub_id = hub_id.into();
    }

    /// Acceso al adaptador de BD subyacente. Pensado para que el **gateway multi-tenant**
    /// (`erplora-server::tenant`, hub#24) y sus tests puedan verificar el **aislamiento entre
    /// pools por org** a nivel de almacenamiento (cada org tiene su propio adaptador). En
    /// producción el camino normal sigue siendo `execute_query`/`execute_command` (gate +
    /// scoping `hub_id`); esto NO salta el gate, solo expone el adaptador ya scopeado por org.
    #[doc(hidden)]
    pub fn db_for_test(&self) -> &dyn DatabaseAdapter {
        self.db.as_ref()
    }

    /// Acceso de **solo lectura** al adaptador de BD para introspección de sistema
    /// (`/api/system`: dialecto, tamaño SQLite, conexiones Postgres). No salta el gate de
    /// permisos/scoping de `execute_query`/`execute_command` — es para métricas, no datos de negocio.
    pub fn db(&self) -> &dyn DatabaseAdapter {
        self.db.as_ref()
    }

    /// Registra un observador de eventos (el server lo usa para reenviar por WS).
    pub fn set_event_sink(&mut self, sink: Arc<dyn EventSink>) {
        self.registry.event_sink = Some(sink);
    }

    /// Registra el **transporte de `host.notify`** (ADR-0012): el cliente real de email/sms/
    /// whatsapp. Lo pone el host (server/Tauri) al arrancar. Sin él, los eventos `*.reminder.due`
    /// se entregan a sus listeners de módulo pero el envío externo es no-op.
    pub fn set_notify_transport(&mut self, transport: Arc<dyn host_notify::NotifyTransport>) {
        self.registry.notify_transport = Some(transport);
    }

    /// Sella que este despliegue es un hub de **DEMO efímera** (ADR-0197, hub#376). Lo llama el
    /// host UNA vez al arrancar con `HubConfig.demo` (env `HUB_DEMO`, que solo escribe el
    /// provisioning del SaaS), igual que sella el `event_sink` o el `notify_transport`.
    ///
    /// Es `&mut self` a propósito: se pone mientras se construye el runtime, antes de servir. No
    /// hay endpoint, comando ni setting que lo cambie después — ni para encenderlo (un hub real que
    /// se declarase demo dejaría de remitir sus ventas) ni para apagarlo (una demo que se declarase
    /// real remitiría a la AEAT de verdad).
    pub fn set_demo_hub(&mut self, demo: bool) {
        self.registry.demo_hub = demo;
    }

    /// ¿Es este despliegue un hub de demo efímera? (ADR-0197). Lectura del marcador que selló el
    /// host; el server la expone en `/api/hub/context` para que la UI se explique.
    pub fn is_demo_hub(&self) -> bool {
        self.registry.demo_hub
    }

    /// Fills in the fiscal identity of a **DEMO** hub at boot (hub#684), and does nothing at all in
    /// a real one. See [`settings::ensure_demo_fiscal_identity`] for why the demo needs the data
    /// written rather than the checklist taught to look away.
    ///
    /// The `demo_hub` guard lives HERE, next to the marker the host seals, and not inside the
    /// settings function: a real hub that woke up with a tax id it never typed would invoice under
    /// it, and ADR-0273 freezes that id at the first record — the mistake would be permanent.
    pub async fn ensure_demo_fiscal_identity(&self) -> Result<bool> {
        if !self.registry.demo_hub {
            return Ok(false);
        }
        settings::ensure_demo_fiscal_identity(self.db.as_ref(), &self.hub_id).await
    }

    /// Seeds `country_code` with the country the SaaS acuñó at provisioning (`HUB_COUNTRY`,
    /// ADR-0207). Never overwrites an answer this hub already has — see
    /// [`settings::ensure_provisioned_country`].
    pub async fn ensure_provisioned_country(&self, country: &str) -> Result<bool> {
        settings::ensure_provisioned_country(self.db.as_ref(), &self.hub_id, country).await
    }

    /// **Where this hub is** (ADR-0062, hub#69): `(country_code, region_code)` from `hub_settings`,
    /// which is what the marketplace catalogue has to be asked about.
    ///
    /// Tolerant on purpose — a hub whose settings cannot be read answers `("", "")`, which the
    /// caller turns into "no filter". A failure here must not empty the shelf: not being able to
    /// tell where a hub is is a reason to show everything, never to show nothing.
    pub async fn country_and_region(&self) -> (String, String) {
        let Ok(settings) = settings::get_all(self.db.as_ref(), &self.hub_id).await else {
            return (String::new(), String::new());
        };
        let read = |key: &str| {
            settings
                .get(key)
                .and_then(|v| v.as_str())
                .unwrap_or_default()
                .to_string()
        };
        (read("country_code"), read("region_code"))
    }

    /// **Which language this hub reads in** (hub#1003), from `hub_settings.language`.
    ///
    /// Read here and not taken from the request for the same reason the country is: the browser is
    /// not in the conversation. `Accept-Language` describes the *device* — and the device is a till
    /// in a back room whose locale says nothing about who is standing at it.
    ///
    /// Tolerant on purpose, like its neighbour: unreadable settings answer `""`, which the caller
    /// turns into "ask in the source language". Not knowing which language to ask in is a reason to
    /// show the catalogue in English, never a reason not to show it.
    pub async fn language(&self) -> String {
        let Ok(settings) = settings::get_all(self.db.as_ref(), &self.hub_id).await else {
            return String::new();
        };
        settings
            .get("language")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string()
    }

    /// Cierra una puerta en un hub de demo (ADR-0197 §4). Devuelve el error con el SUJETO del
    /// cierre, para que el cliente sepa cuál de los tres se negó.
    pub(crate) fn refuse_if_demo(&self, lock: DemoLock) -> Result<()> {
        if self.registry.demo_hub {
            return Err(RuntimeError::DemoLocked { lock });
        }
        Ok(())
    }

    /// Registra el backend persistente de módulos. El server lo resuelve a disco (Local) o al
    /// proxy Cloud→S3 (Cloud); el runtime y los módulos solo ven rutas bajo `media/modules/`.
    pub fn set_module_storage(&mut self, storage: Arc<dyn module_storage::ModuleStorage>) {
        self.registry.module_storage = Some(storage);
    }

    /// Marca un módulo como **WhatsApp premium de ERPlora** (su canal WhatsApp sale por el proxy
    /// de Cloud con `check_quota`, ADR-0006/ADR-0012). El `tier` vive en Cloud; el host lo siembra.
    pub fn mark_premium_whatsapp(&mut self, module_id: &str) {
        self.registry
            .premium_whatsapp_modules
            .insert(module_id.to_string());
    }

    /// Registra un **plugin nativo first-party** (ADR-0009) para `module_id`. Los commands
    /// del módulo con `handler.type == "native"` se resuelven contra este motor. Lo llama
    /// el host (server / shell Tauri) al arrancar; no forma parte de la instalación.
    pub fn register_native(&mut self, module_id: &str, handler: Arc<dyn native::NativeHandler>) {
        self.registry.native.insert(module_id.to_string(), handler);
    }

    /// What every INSTALLED native engine still owes an external authority — how much and
    /// since when (hub#1406). One entry per installed engine that ANSWERED:
    /// `Some(obligation)` = it owes work; `None` = it owes nothing and SAYS so (the caller
    /// can report an honest zero). An engine whose queue cannot be read is skipped — «I
    /// don't know» must reach the caller as an absence, never as a fabricated zero.
    ///
    /// Per engine this is the SAME question the retention gate asks before an uninstall
    /// ([`NativeHandler::pending_obligations`], hub#314): one source, so the fleet alert
    /// and the refusal can never disagree. Sorted by module id: the report is wire-bound.
    pub async fn pending_obligations(&self) -> Vec<(String, Option<native::PendingObligation>)> {
        let mut report = Vec::new();
        for (module_id, engine) in &self.registry.native {
            if !self.registry.is_installed(module_id) {
                continue;
            }
            let host = native::DbHost {
                db: self.db.as_ref(),
                storage: None,
                hub_id: &self.hub_id,
                module_id,
                static_folder: None,
            };
            match engine.pending_obligations(&self.hub_id, &host).await {
                Ok(answer) => report.push((module_id.clone(), answer)),
                Err(_) => {}
            }
        }
        report.sort_by(|a, b| a.0.cmp(&b.0));
        report
    }

    /// Menú dinámico de los módulos **activos** (lo consume el shell). ARQUITECTURA.md §7.7.
    pub fn navigation(&self) -> Vec<NavEntry> {
        self.registry
            .active_navigation()
            .into_iter()
            .cloned()
            .collect()
    }

    /// Acceso de solo lectura al registro (introspección / tests).
    pub fn registry(&self) -> &Registry {
        &self.registry
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::testutil::fresh_db;

    /// El marcador lo sella el host y no lo mueve nadie más: el default es hub normal.
    #[tokio::test]
    async fn the_demo_marker_is_off_until_the_host_seals_it() {
        let mut rt = Runtime::new(Box::new(fresh_db().await));
        assert!(!rt.is_demo_hub());
        rt.set_demo_hub(true);
        assert!(rt.is_demo_hub());
    }

    #[derive(Debug)]
    struct OwingEngine;

    #[async_trait::async_trait]
    impl native::NativeHandler for OwingEngine {
        async fn call(
            &self,
            _function: &str,
            _input: &Json,
            _host: &dyn native::NativeHost,
        ) -> Result<erplora_wasm_host::Output> {
            Err(RuntimeError::Native("not exercised by this test".into()))
        }
        async fn pending_obligations(
            &self,
            _hub_id: &str,
            _host: &dyn native::NativeHost,
        ) -> Result<Option<native::PendingObligation>> {
            Ok(Some(native::PendingObligation {
                count: 3,
                oldest_pending_at: Some("2026-08-30T08:00:00Z".to_string()),
                code: "testregime.unsent_records".to_string(),
                message: "3 record(s) still owed to the authority".to_string(),
            }))
        }
    }

    #[derive(Debug)]
    struct SettledEngine;

    #[async_trait::async_trait]
    impl native::NativeHandler for SettledEngine {
        async fn call(
            &self,
            _function: &str,
            _input: &Json,
            _host: &dyn native::NativeHost,
        ) -> Result<erplora_wasm_host::Output> {
            Err(RuntimeError::Native("not exercised by this test".into()))
        }
        // Default `pending_obligations` → Ok(None): owes nothing, and SAYS so.
    }

    fn installed(id: &str) -> manifest::Manifest {
        serde_json::from_str(&format!(
            r#"{{"id":"{id}","name":"{id}","version":"1.0.0"}}"#
        ))
        .expect("minimal manifest parses")
    }

    /// hub#1406: the heartbeat asks the REGISTRY, not a concrete engine — «which
    /// installed engines owe work to an external authority, how much and since
    /// when?». Same per-engine question as the uninstall gate (hub#314): one
    /// source, so the alert and the refusal can never disagree.
    ///
    /// Three engines pin the three answers: one owes (count + since-when), one
    /// answers an honest «nothing» (`Ok(None)` — reported, so the caller can send
    /// a real 0 instead of an absence), and one is registered but NOT installed
    /// (the host bakes engines in even when this hub lacks the module) — silent.
    #[tokio::test]
    async fn hub1406_pending_obligations_are_asked_generically_to_the_registry() {
        let mut rt = Runtime::new(Box::new(fresh_db().await));
        rt.register_native("testregime", Arc::new(OwingEngine));
        rt.register_native("quietregime", Arc::new(SettledEngine));
        rt.register_native("ghostregime", Arc::new(OwingEngine));
        rt.registry.installed.push(installed("testregime"));
        rt.registry.installed.push(installed("quietregime"));

        let report = rt.pending_obligations().await;

        assert_eq!(
            report.len(),
            2,
            "exactly the two INSTALLED engines answer: {report:?}"
        );
        let owing = report
            .iter()
            .find(|(id, _)| id == "testregime")
            .expect("the owing engine is reported");
        let obligation = owing.1.as_ref().expect("it owes work");
        assert_eq!(obligation.count, 3);
        assert_eq!(
            obligation.oldest_pending_at.as_deref(),
            Some("2026-08-30T08:00:00Z"),
            "since-when travels with the count (hub#326)"
        );
        let quiet = report
            .iter()
            .find(|(id, _)| id == "quietregime")
            .expect("an installed engine that owes nothing is still REPORTED");
        assert!(
            quiet.1.is_none(),
            "owing nothing is an honest answer, not an absence"
        );
    }
}
