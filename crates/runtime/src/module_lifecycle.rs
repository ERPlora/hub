//! Module install / update / activate / deactivate / uninstall — split out of `lib.rs` verbatim (hub#1403).

use crate::*;

impl Runtime {
    /// Instala un módulo ya extraído en `dir` (lee `module.json`, migra, registra, activa).
    pub async fn install_from_dir(&mut self, dir: &Path) -> Result<String> {
        installer::install(self.db.as_ref(), &mut self.registry, &self.hub_id, dir).await
    }

    /// Actualiza a la versión ya extraída en `dir` un módulo que **ya está instalado** (hub#516).
    ///
    /// Es la misma puerta que [`install_from_dir`](Self::install_from_dir) —el paquete llega
    /// verificado (SHA256 + firma ed25519) y su manifest se valida igual—, con dos diferencias que
    /// solo existen aquí:
    ///
    /// - **Se exige que el módulo esté instalado.** Actualizar lo que no hay no es actualizar; sin
    ///   esto, un id mal escrito instalaría un módulo nuevo en silencio.
    /// - **Devuelve la transición `from → to`**, que es lo que el dueño ve (ADR-0269 §3.5) y lo que
    ///   la incidencia pregunta primero: qué cambió y desde dónde.
    ///
    /// Solo se aplican las migraciones que la versión nueva **añade** (`_hub_migrations` dedupe por
    /// fichero), y si el intento falla **sigue corriendo la versión anterior** — lo garantiza
    /// `installer::install`, no este método.
    pub async fn update_from_dir(&mut self, dir: &Path) -> Result<ModuleUpdate> {
        let manifest = crate::manifest::Manifest::load(dir)?;
        let from = self
            .registry
            .installed
            .iter()
            .find(|m| m.id == manifest.id)
            .map(|m| m.version.clone())
            .ok_or_else(|| {
                RuntimeError::CommandNotFound(format!("módulo no instalado: {}", manifest.id))
            })?;

        let module_id =
            installer::install(self.db.as_ref(), &mut self.registry, &self.hub_id, dir).await?;
        Ok(ModuleUpdate {
            module_id,
            from,
            to: manifest.version,
        })
    }

    /// Dependencias declaradas en el `module.json` de `dir` que aún NO están instaladas en este
    /// runtime (en el orden del manifest). Base de la **instalación anidada**: el flujo de
    /// instalación desde el Cloud (`server::install::install_from_cloud`) descarga e instala estas
    /// deps ANTES del módulo que las declara, replicando para el camino "descarga marketplace" el
    /// topo-orden que `install_all_from_dir` ya hace para los módulos horneados (hub#16). No
    /// modifica estado; solo lee el manifest y consulta el registro.
    pub fn missing_dependencies(&self, dir: &Path) -> Result<Vec<String>> {
        let manifest = crate::manifest::Manifest::load(dir)?;
        Ok(manifest
            .depends_on
            .into_iter()
            .filter(|dep| !self.registry.is_installed(&dep.id))
            .map(|dep| dep.id)
            .collect())
    }

    /// Instala todos los módulos de las subcarpetas de `root` (las que tienen `module.json`),
    /// **resolviendo el orden de `depends_on` por topo-sort** (hub#16): una dependencia se instala
    /// antes que quien la declara, sin depender del orden del sistema de ficheros. Devuelve los ids
    /// instalados en el orden aplicado.
    ///
    /// **Tolerante** (como el arranque original): un módulo cuyo manifest no carga o cuya
    /// instalación falla se **omite con log** y NO tumba a los demás (un módulo de terceros roto no
    /// debe brickear el hub al arrancar). Un `root` **ausente** se trata como lote vacío (no hay
    /// módulos horneados que instalar) — el caso del contenedor stateless con `HUB_MODULES_DIR`
    /// apuntando a una ruta que el despliegue no crea (ERPlora/saas#616). Solo abortan: un
    /// `read_dir` que falla por OTRA razón (permisos, etc.) o un **ciclo** de `depends_on` (error
    /// estructural del conjunto, se reporta y no se instala nada del lote).
    pub async fn install_all_from_dir(&mut self, root: &Path) -> Result<Vec<String>> {
        // hub#1477: lo que no entre se ANOTA, además de loguearse. El veredicto describe ESTE
        // intento, así que lo primero es retirar el anterior: si acumulase, un módulo ya arreglado
        // seguiría denunciado para siempre y `/readyz` no volvería a ponerse verde nunca.
        self.registry.failed_installs.clear();
        let mut failures: Vec<crate::registry::FailedInstall> = Vec::new();

        // 1) Carga manifests; un manifest inválido se omite (log), no aborta el lote.
        let mut found: Vec<(std::path::PathBuf, crate::manifest::Manifest)> = Vec::new();
        // Un dir de módulos ausente NO es un error: significa "no hay módulos que instalar" (lote
        // vacío), igual que un dir presente pero vacío. Sin esto, un `HUB_MODULES_DIR` inexistente
        // (contenedor stateless) propagaba `io: No such file or directory (os error 2)` en TODOS los
        // arranques (#616). Otros errores de IO (permisos, etc.) sí se propagan.
        let entries = match std::fs::read_dir(root) {
            Ok(entries) => entries,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
            Err(e) => return Err(e.into()),
        };
        for entry in entries {
            let path = entry?.path();
            if !path.join("module.json").exists() {
                continue;
            }
            match crate::manifest::Manifest::load(&path) {
                Ok(manifest) => found.push((path, manifest)),
                // Sin manifest no hay id que leer: el nombre de la carpeta es lo único que hay, y
                // es justo lo que quien mire el disco va a ver (hub#1477).
                Err(e) => record_failed_install(
                    &mut failures,
                    path.file_name()
                        .map(|name| name.to_string_lossy().into_owned())
                        .unwrap_or_else(|| path.display().to_string()),
                    &path,
                    &e,
                ),
            }
        }
        // 2) Estado persistido por hub ANTES de instalar (hub#31): `install` reactiva todo al
        // re-registrar desde disco, así que capturamos aquí el activo/inactivo previo **de este
        // hub** (filtrado por `hub_id`; en BD compartida no toma el estado de otro hub) para
        // reponerlo tras instalar. Lo leemos antes porque el upsert de `install` lo sobreescribiría.
        let persisted = installer::installed_status(self.db.as_ref(), &self.hub_id).await?;

        // 3) Orden topológico por depends_on (un ciclo sí aborta: error de diseño del conjunto).
        let pairs: Vec<(String, Vec<String>)> = found
            .iter()
            .map(|(_, m)| {
                (
                    m.id.clone(),
                    m.depends_on.iter().map(|d| d.id.clone()).collect(),
                )
            })
            .collect();
        let order = installer::install_order(&pairs)?;
        // 4) Instala en orden; un módulo que falle se omite (log) sin tumbar a los demás.
        let mut installed = Vec::with_capacity(order.len());
        for i in order {
            match self.install_from_dir(&found[i].0).await {
                Ok(id) => {
                    eprintln!("✓ módulo instalado: {id}");
                    installed.push(id);
                }
                Err(e) => {
                    record_failed_install(&mut failures, found[i].1.id.clone(), &found[i].0, &e)
                }
            }
        }

        // Deja el veredicto donde la sonda de readiness lo va a mirar (hub#1477). Va ANTES del
        // paso 5 porque ese paso puede propagar un error: si se colocara después, un fallo al
        // reponer estados dejaría el hub incompleto Y sin la anotación que lo explica.
        self.registry.failed_installs = failures;

        // 5) Repón el estado inactivo previo de este hub sobre el registro recién reconstruido y
        // persístelo (el upsert del install lo había dejado `active`). Solo módulos presentes en
        // disco; un estado huérfano de un módulo ya borrado se ignora. Basta con reponer los
        // MANUALES: `deactivate` re-deriva la cascada (ADR-0128), así que los `inactive_auto`
        // persistidos renacen solos de su raíz — y si su raíz ya no existe, quedan activos, que
        // es lo coherente (sin causa no hay caída).
        for (id, status) in persisted {
            if status == ModuleStatus::Inactive && self.registry.is_installed(&id) {
                // `_unchecked`: reponer un estado ya persistido no es una decisión nueva, así que
                // no pasa por el retention gate (hub#314) — si lo hiciera, un módulo con registros
                // sin remitir tumbaría el arranque o resucitaría apagado por el admin.
                self.deactivate_unchecked(&id).await?;
            }
        }
        Ok(installed)
    }

    /// Re-hidrata el Registry tras un REINICIO: re-registra los módulos ya instalados de ESTE hub
    /// leyéndolos de la caché de descargas (`cache_root/<id>/<version>/`). Necesario para el caso
    /// "descarga desde marketplace" (`modules_dir: None`): el estado persiste en `hub_module` + las
    /// tablas del módulo + la caché, pero el Registry en memoria arranca vacío, así que sin esto un
    /// módulo instalado "desaparece" del runtime al reiniciar (no expone queries/commands/nav).
    ///
    /// Idempotente y tolerante: salta los ya registrados (p. ej. los de `modules_dir`); un módulo
    /// cuya carpeta falte o cuyo install falle se omite con log (no tumba el arranque). `install_from_dir`
    /// reaplica migraciones sin efecto (registradas en `_hub_migrations`). Respeta el estado inactivo
    /// persistido. Devuelve los ids re-hidratados.
    pub async fn rehydrate_installed(&mut self, cache_root: &Path) -> Result<Vec<String>> {
        let persisted =
            installer::installed_status_versioned(self.db.as_ref(), &self.hub_id).await?;
        let mut out = Vec::new();
        for (id, version, status) in persisted {
            if self.registry.is_installed(&id) {
                continue; // ya re-registrado (p. ej. por modules_dir): no dupliques
            }
            let dir = cache_root.join(&id).join(&version);
            if !dir.join("module.json").exists() {
                eprintln!(
                    "✗ rehidratación {id}@{version}: sin module.json en caché ({})",
                    dir.display()
                );
                continue;
            }
            match self.install_from_dir(&dir).await {
                Ok(rid) => {
                    if status == ModuleStatus::Inactive {
                        // `_unchecked`: repón inactivo (install lo dejó active). Es estado ya
                        // persistido, no una decisión nueva → sin retention gate (hub#314).
                        let _ = self.deactivate_unchecked(&rid).await;
                    }
                    eprintln!("✓ módulo re-hidratado: {rid}@{version}");
                    out.push(rid);
                }
                Err(e) => eprintln!("✗ rehidratación {id}@{version}: {e}"),
            }
        }
        Ok(out)
    }

    /// Módulos que `hub_module` dice **instalados** para este hub pero que **NO** quedaron
    /// registrados tras [`rehydrate_installed`] — típicamente porque su carpeta de caché no existía
    /// (contrato **stateless** de Hub Cloud: `module_cache` efímero en `/tmp`, se vacía en cada
    /// redeploy/reschedule). Devuelve `(id, version)` para que el host los **re-descargue** del
    /// marketplace (`server::install::install_from_cloud`) y el hub se auto-cure tras un reinicio
    /// sin depender de un volumen persistente. No modifica estado.
    pub async fn installed_but_unregistered(&self) -> Result<Vec<(String, String)>> {
        let persisted =
            installer::installed_status_versioned(self.db.as_ref(), &self.hub_id).await?;
        Ok(persisted
            .into_iter()
            .filter(|(id, _version, _status)| !self.registry.is_installed(id))
            .map(|(id, version, _status)| (id, version))
            .collect())
    }

    /// Activa un módulo instalado — con CASCADA en las dos direcciones (ADR-0128).
    ///
    /// El invariante es «activo ⇒ todas tus `depends_on` activas», y lo mantiene el runtime, no
    /// el admin: activar `sales` enciende también sus dependencias (el admin pidió sales; sales
    /// no existe sin ellas). Después, un barrido a punto fijo revive todo lo que cayó EN CASCADA
    /// (`InactiveAuto`) y ya tiene sus dependencias activas — lo apagado A MANO no se toca.
    pub async fn activate(&mut self, module_id: &str) -> Result<()> {
        // Cascada hacia ARRIBA: el módulo pedido + sus dependencias transitivas.
        let mut pending = vec![module_id.to_string()];
        let mut to_enable: Vec<String> = Vec::new();
        while let Some(id) = pending.pop() {
            if to_enable.contains(&id) {
                continue;
            }
            to_enable.push(id.clone());
            if let Some(m) = self.registry.installed.iter().find(|m| m.id == id) {
                pending.extend(m.depends_on.iter().map(|d| d.id.clone()));
            }
        }
        for id in &to_enable {
            installer::set_status(
                self.db.as_ref(),
                &mut self.registry,
                &self.hub_id,
                id,
                ModuleStatus::Active,
            )
            .await?;
        }
        // Barrido a punto fijo: lo caído en cascada vuelve en cuanto puede.
        loop {
            let revivable: Vec<String> = self
                .registry
                .installed
                .iter()
                .filter(|m| {
                    matches!(
                        self.registry.status.get(&m.id),
                        Some(ModuleStatus::InactiveAuto)
                    ) && m.depends_on.iter().all(|d| self.registry.is_active(&d.id))
                })
                .map(|m| m.id.clone())
                .collect();
            if revivable.is_empty() {
                break;
            }
            for id in revivable {
                installer::set_status(
                    self.db.as_ref(),
                    &mut self.registry,
                    &self.hub_id,
                    &id,
                    ModuleStatus::Active,
                )
                .await?;
            }
        }
        Ok(())
    }

    /// Módulos que caerían al desactivar `module_id`: él mismo + todo dependiente transitivo hoy
    /// activo (ADR-0128). Puro (no muta): es el conjunto que la cascada de [`Self::deactivate`]
    /// apagaría, calculado ANTES para poder revisarlo entero (hub#314).
    fn deactivation_cascade(&self, module_id: &str) -> Vec<String> {
        let mut fallen = vec![module_id.to_string()];
        loop {
            let wave: Vec<String> = self
                .registry
                .installed
                .iter()
                .filter(|m| {
                    self.registry.is_active(&m.id)
                        && !fallen.contains(&m.id)
                        && m.depends_on.iter().any(|d| fallen.contains(&d.id))
                })
                .map(|m| m.id.clone())
                .collect();
            if wave.is_empty() {
                return fallen;
            }
            fallen.extend(wave);
        }
    }

    /// Retention gate (hub#314, ADR-0202 R2) sobre un módulo: pregunta a su motor nativo qué debe
    /// todavía a una autoridad externa y falla si queda algo. Ver
    /// [`installer::ensure_no_pending_obligations`].
    async fn ensure_module_can_go(&self, module_id: &str) -> Result<()> {
        // El host deja los motores nativos registrados aunque este hub no tenga el módulo. La
        // gate protege a un módulo que SE VA: si no está, no hay nada que proteger y quien llama
        // debe seguir viendo su «módulo no instalado» de siempre, no un rechazo de retención.
        if !self.registry.is_installed(module_id) {
            return Ok(());
        }
        let host = native::DbHost {
            db: self.db.as_ref(),
            storage: None,
            hub_id: &self.hub_id,
            module_id,
            static_folder: None,
        };
        installer::ensure_no_pending_obligations(&host, &self.registry, &self.hub_id, module_id)
            .await
    }

    /// Desactiva un módulo instalado — y ARRASTRA a todo dependiente transitivo activo (ADR-0128).
    ///
    /// El objetivo cae como `Inactive` (decisión MANUAL: se respeta hasta que el admin lo pida de
    /// vuelta). Los arrastrados caen como `InactiveAuto`: volverán solos en cuanto sus
    /// dependencias vuelvan a estar activas.
    ///
    /// hub#314: antes de tocar nada se revisa el conjunto ENTERO que caería. Apagar `invoice`
    /// arrastra a `verifactu`, así que gatear solo el objetivo dejaría la puerta de atrás abierta:
    /// si CUALQUIERA de los que caen aún debe registros sin remitir, no cae ninguno.
    pub async fn deactivate(&mut self, module_id: &str) -> Result<()> {
        let cascade = self.deactivation_cascade(module_id);
        // ADR-0273 D5 (hub#553): **el candado del CORE va PRIMERO**, y sobre el conjunto entero.
        // R2 le pregunta al motor cuánto debe; éste no pregunta a nadie, porque un módulo no puede
        // tener voto sobre si se le puede quitar. Y con la cola vacía R2 deja marchar al último
        // proveedor: la cola vacía protege el pasado, el daño lo hacen las ventas siguientes.
        self.ensure_fiscal_provider_remains(&cascade).await?;
        for id in cascade {
            self.ensure_module_can_go(&id).await?;
        }
        self.deactivate_unchecked(module_id).await
    }

    /// Comprueba el candado de proveedor fiscal (ADR-0273 D5) contra el conjunto que se va.
    ///
    /// Sin perfil todavía —un hub que nunca arrancó del todo— no hay nada que proteger: leer no
    /// puede ser la razón de que no se pueda desinstalar un módulo.
    async fn ensure_fiscal_provider_remains(&self, leaving: &[String]) -> Result<()> {
        let Some(profile) = fiscal_profile::load(self.db.as_ref(), &self.hub_id).await? else {
            return Ok(());
        };
        fiscal_profile::ensure_provider_remains(&profile, &self.registry, leaving)
    }

    /// Puts back a status that is ALREADY persisted, after the module was registered again
    /// (hub#1875: another task of this hub installed or updated it). Registering always leaves a
    /// module active, so without this a module the admin switched off would come back on just
    /// because it was reloaded. Same rule as the rehydration at boot: restoring a persisted state is
    /// not a new decision, so it does not go through the retention gate (hub#314).
    pub async fn restore_persisted_status(
        &mut self,
        module_id: &str,
        status: ModuleStatus,
    ) -> Result<()> {
        match status {
            ModuleStatus::Active => Ok(()),
            ModuleStatus::Inactive => self.deactivate_unchecked(module_id).await,
            ModuleStatus::InactiveAuto => {
                installer::set_status(
                    self.db.as_ref(),
                    &mut self.registry,
                    &self.hub_id,
                    module_id,
                    ModuleStatus::InactiveAuto,
                )
                .await
            }
        }
    }

    /// Drops from THIS task's registry a module another task of the hub already uninstalled
    /// (hub#2039). Memory only, on purpose: the other task went through every guard of
    /// [`Self::uninstall`] and did all the writing — the `hub_module` row, the roles, the scheduled
    /// tasks and the stored package are gone. Doing it again here would be a second decision.
    /// Returns `false` if the module was not registered.
    pub fn forget_uninstalled_elsewhere(&mut self, module_id: &str) -> bool {
        self.registry.remove_module(module_id)
    }

    /// Applies to THIS task's registry the status another task recorded for a module (hub#2039).
    /// Memory only, and without cascading: the other task already ran the cascade (ADR-0128) and
    /// recorded every module it touched, so each row arrives here as it was decided. Returns
    /// `false` if the module is not registered.
    pub fn adopt_recorded_status(&mut self, module_id: &str, status: ModuleStatus) -> bool {
        self.registry.set_status(module_id, status)
    }

    /// [`Self::deactivate`] SIN el retention gate: repone un estado inactivo YA persistido
    /// (arranque/rehidratación), que no es una decisión nueva del admin. Gatearlo aquí solo podría
    /// tumbar el arranque o resucitar un módulo que el admin había apagado (hub#314).
    async fn deactivate_unchecked(&mut self, module_id: &str) -> Result<()> {
        installer::set_status(
            self.db.as_ref(),
            &mut self.registry,
            &self.hub_id,
            module_id,
            ModuleStatus::Inactive,
        )
        .await?;
        // Cascada hacia ABAJO por el grafo inverso de depends_on, en oleadas.
        let mut fallen = vec![module_id.to_string()];
        loop {
            let wave: Vec<String> = self
                .registry
                .installed
                .iter()
                .filter(|m| {
                    self.registry.is_active(&m.id)
                        && m.depends_on.iter().any(|d| fallen.contains(&d.id))
                })
                .map(|m| m.id.clone())
                .collect();
            if wave.is_empty() {
                break;
            }
            for id in wave {
                installer::set_status(
                    self.db.as_ref(),
                    &mut self.registry,
                    &self.hub_id,
                    &id,
                    ModuleStatus::InactiveAuto,
                )
                .await?;
                fallen.push(id);
            }
        }
        Ok(())
    }

    /// Desinstala un módulo (quita sus capacidades; no borra sus datos).
    ///
    /// hub#314: se rechaza mientras su motor deba trabajo a una autoridad externa — borrar la fila
    /// de `hub_module` con registros sin remitir los dejaba huérfanos (VeriFactu FAQ §5).
    ///
    /// hub#1101: y se rechaza si otros módulos instalados lo declaran en `depends_on`, nombrándolos
    /// ([`Self::dependents_of`]). Para saltárselo hace falta [`Self::uninstall_forced`].
    pub async fn uninstall(&mut self, module_id: &str) -> Result<()> {
        self.uninstall_with(module_id, false).await
    }

    /// [`Self::uninstall`] **saltándose el gate de dependientes** (hub#1101) — y solo ese.
    ///
    /// Es la respuesta a UNA pregunta: «otras apps necesitan esta, ¿la quito igualmente?». La
    /// contesta el dueño, al que la pantalla le ha nombrado antes lo que se rompe (hub#773), o
    /// soporte por API. Lo que NO abre es el lado fiscal: si el motor aún debe registros a una
    /// autoridad, o si el módulo es el último proveedor fiscal del hub, esto sigue rechazando —
    /// esas dos no son preguntas del dueño (ADR-0202 R2, ADR-0273 D5).
    pub async fn uninstall_forced(&mut self, module_id: &str) -> Result<()> {
        self.uninstall_with(module_id, true).await
    }

    async fn uninstall_with(&mut self, module_id: &str, force: bool) -> Result<()> {
        // ADR-0273 D5 (hub#553): antes que R2, y por la misma razón — con la cola vacía R2 deja
        // marchar al último proveedor, y desde ese momento el hub vende sin que nadie registre.
        self.ensure_fiscal_provider_remains(&[module_id.to_string()])
            .await?;
        self.ensure_module_can_go(module_id).await?;
        // El último, y a propósito: es el ÚNICO forzable, así que va detrás de los candados que no
        // lo son. Ponerlo delante haría que un `force` los saltara por el orden de las guardas.
        if !force {
            self.ensure_nobody_depends_on(module_id)?;
        }
        installer::uninstall(
            self.db.as_ref(),
            &mut self.registry,
            &self.hub_id,
            module_id,
        )
        .await
    }

    /// Rechaza si algún módulo instalado depende de `module_id` (hub#1101).
    ///
    /// Un módulo que no está instalado no tiene nada que proteger: quien llama debe seguir viendo
    /// su «módulo no instalado» de siempre, no un rechazo de dependencias.
    fn ensure_nobody_depends_on(&self, module_id: &str) -> Result<()> {
        if !self.registry.is_installed(module_id) {
            return Ok(());
        }
        let dependents = self.dependents_of(module_id);
        if dependents.is_empty() {
            return Ok(());
        }
        Err(RuntimeError::HasDependents {
            module: module_id.to_string(),
            dependents,
        })
    }

    /// Los módulos instalados que dejarían de funcionar si `module_id` se fuera — **transitivos y
    /// sea cual sea su estado** (hub#1101).
    ///
    /// A propósito NO es el mismo conjunto que la cascada de desactivación
    /// ([`Self::deactivation_cascade`]), que solo mira a los ACTIVOS porque apagar lo que ya está
    /// apagado no cambia nada. Desinstalar se lleva el paquete: un dependiente apagado ya no se
    /// podrá volver a encender nunca, así que cuenta igual. Es la misma regla que la pantalla ya
    /// aplica al pintar el aviso (hub#773, `dependentsOf`).
    ///
    /// Recorrido en oleadas sobre lo ya caído, así que un manifest con un ciclo termina en vez de
    /// colgar al que pregunta.
    pub fn dependents_of(&self, module_id: &str) -> Vec<String> {
        let mut fallen = vec![module_id.to_string()];
        let mut out: Vec<String> = Vec::new();
        loop {
            let wave: Vec<String> = self
                .registry
                .installed
                .iter()
                .filter(|m| {
                    !fallen.contains(&m.id) && m.depends_on.iter().any(|d| fallen.contains(&d.id))
                })
                .map(|m| m.id.clone())
                .collect();
            if wave.is_empty() {
                return out;
            }
            fallen.extend(wave.iter().cloned());
            out.extend(wave);
        }
    }

    /// Lista de módulos instalados con su estado (para el dashboard / `/api/modules`).
    pub fn modules(&self) -> Vec<ModuleInfo> {
        self.registry
            .installed
            .iter()
            .map(|m| ModuleInfo {
                id: m.id.clone(),
                name: m.name.clone(),
                version: m.version.clone(),
                status: *self
                    .registry
                    .status
                    .get(&m.id)
                    .unwrap_or(&ModuleStatus::Inactive),
                depends_on: m.depends_on.iter().map(|d| d.id.clone()).collect(),
                manifest_warnings: m.warnings.clone(),
                errors: m
                    .errors
                    .iter()
                    .flatten()
                    .map(|(code, decl)| ErrorInfo {
                        code: code.clone(),
                        deprecated: decl.deprecated.clone(),
                    })
                    .collect(),
            })
            .collect()
    }
}

/// Anota —y denuncia— un módulo que se pidió instalar y no entró (hub#1477).
///
/// Las tres salidas son deliberadamente la misma llamada, porque separarlas es como se llegó al
/// bug: el `eprintln!` estaba, y con eso se dio el caso por cubierto. Un log dentro de un
/// contenedor no lo mira nadie.
///
/// - **Log**, para quien ya esté leyendo el arranque.
/// - **ErrorRegistry**, que es lo que sale del hub y llega a un humano.
/// - **La lista del Registry**, que es lo que consulta `/readyz` — el único de los tres que
///   impide dar por buena una versión incompleta.
fn record_failed_install(
    failures: &mut Vec<crate::registry::FailedInstall>,
    module_id: String,
    source: &Path,
    error: &RuntimeError,
) {
    let failure = crate::registry::FailedInstall {
        module_id,
        source: source.display().to_string(),
        reason: error.to_string(),
    };
    eprintln!("✗ módulo {}: {}", failure.source, failure.reason);
    crate::error_registry::ErrorRegistry::global().report(failed_install_event(&failure));
    failures.push(failure);
}

/// El informe de un módulo que no se pudo instalar, sin mandarlo todavía.
///
/// Aparte para poder fijarlo con un test, igual que `server::boot::incomplete_boot_event`: lo que
/// importa es el **contenido** —el código estable contra el que se programa y el módulo al que se
/// atribuye—, no que se haya llamado a un sink global.
///
/// Aquí el fallo **sí** tiene dueño: a diferencia de un arranque incompleto (donde lo que se cayó
/// es el arranque entero), aquí se sabe exactamente qué paquete no entró, así que se le cuelga.
pub(crate) fn failed_install_event(
    failure: &crate::registry::FailedInstall,
) -> crate::error_registry::ErrorEvent {
    use crate::error_registry::{severity, source, ErrorEvent};

    ErrorEvent::new(
        source::HUB,
        "module_install_failed",
        format!(
            "el módulo `{}` no se pudo instalar y el hub sigue sin él: {}",
            failure.module_id, failure.reason
        ),
        severity::UNEXPECTED,
    )
    .with_module(failure.module_id.clone())
    .with_context(serde_json::json!({
        "module_id": failure.module_id,
        "source": failure.source,
        "reason": failure.reason,
    }))
}

#[cfg(test)]
mod failed_install_report_tests {
    //! hub#1477: un módulo que no se instaló no puede morir en el log de un contenedor.
    use super::failed_install_event;
    use crate::registry::FailedInstall;

    fn failure() -> FailedInstall {
        FailedInstall {
            module_id: "verifactu".to_string(),
            source: "/tmp/modules/verifactu".to_string(),
            reason: "host.module_storage: Hub Cloud sin token de máquina".to_string(),
        }
    }

    /// El código es el contrato: contra él se programan la alerta y el filtro, no contra la prosa
    /// (ADR-0055).
    #[test]
    fn the_report_carries_a_stable_code_and_the_reason_that_explains_it() {
        let event = failed_install_event(&failure());

        assert_eq!(event.error_code, "module_install_failed");
        assert_eq!(event.severity, crate::error_registry::severity::UNEXPECTED);
        assert_eq!(event.context["module_id"], "verifactu");
        assert_eq!(event.context["source"], "/tmp/modules/verifactu");
        assert!(
            event.context["reason"]
                .as_str()
                .unwrap_or_default()
                .contains("sin token de máquina"),
            "sin el motivo, saber que falta no dice qué arreglar: {}",
            event.context["reason"]
        );
    }

    /// **Aquí sí hay culpable.** Un arranque incompleto es del hub (`module_boot_incomplete`, no
    /// lleva `module_id`); esto es un paquete concreto que no entró, y atribuirlo es lo que permite
    /// filtrar por módulo en vez de leerse el mensaje.
    #[test]
    fn the_failure_is_attributed_to_the_module_that_did_not_make_it_in() {
        let event = failed_install_event(&failure());

        assert_eq!(event.source, crate::error_registry::source::HUB);
        assert_eq!(event.module_id.as_deref(), Some("verifactu"));
        assert!(event.message.contains("verifactu"), "{}", event.message);
    }
}
