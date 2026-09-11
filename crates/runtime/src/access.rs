//! Users, PINs, badges, sessions, devices, policies and API keys — split out of `lib.rs` verbatim (hub#1403).

use crate::*;

impl Runtime {
    /// Crea un usuario local (`pin` vacío = sin PIN). Devuelve su id.
    pub async fn create_user(
        &self,
        name: &str,
        pin: &str,
        role: &str,
        cloud_user_id: Option<&str>,
    ) -> Result<String> {
        identity::create_user(
            self.db.as_ref(),
            &self.hub_id,
            name,
            pin,
            role,
            cloud_user_id,
        )
        .await
    }

    #[doc(hidden)]
    pub async fn ensure_dev_user(&self, id: &str, name: &str, role: &str) -> Result<()> {
        identity::ensure_dev_user(self.db.as_ref(), &self.hub_id, id, name, role).await
    }

    /// Verifica el PIN de un usuario por nombre. `Some(user)` si encaja.
    pub async fn verify_pin(&self, name: &str, pin: &str) -> Result<Option<identity::HubUser>> {
        identity::verify_pin(self.db.as_ref(), &self.hub_id, name, pin).await
    }

    /// Usuarios activos del hub con PIN (para mostrar el grid de login local). `(id, name, role)`.
    pub async fn list_pin_users(&self) -> Result<Vec<(String, String, String)>> {
        identity::list_pin_users(self.db.as_ref(), &self.hub_id).await
    }

    // ── Placa de empleado (hub#658). Hermana del PIN: ver `identity`. ───────────────────────

    /// Resuelve una **placa** a su dueño activo. La placa sustituye al par (nombre, PIN) del
    /// pinpad, nunca al PIN.
    pub async fn verify_badge(&self, badge: &str) -> Result<Option<identity::BadgeMatch>> {
        identity::verify_badge(self.db.as_ref(), &self.hub_id, badge).await
    }

    /// Fija (o **retira**, con `badge` vacío) la placa de un usuario. No toca su PIN.
    pub async fn set_user_badge(&self, user_id: &str, badge: &str) -> Result<()> {
        identity::set_badge(self.db.as_ref(), &self.hub_id, user_id, badge).await
    }

    /// `true` si esta placa ya es de **otro** usuario activo del hub.
    pub async fn badge_is_taken(&self, badge: &str, excluding_id: Option<&str>) -> Result<bool> {
        identity::badge_is_taken(self.db.as_ref(), &self.hub_id, badge, excluding_id).await
    }

    /// La clave HMAC con la que este hub indexa sus placas (se acuña en la primera llamada).
    /// Expuesta para que la capa HTTP pueda derivar el índice de una placa **sin** verla en claro
    /// más allá de la petición — p. ej. para limitar los intentos por tarjeta en el login.
    pub async fn badge_index_key(&self) -> Result<Vec<u8>> {
        identity::badge_index_key(self.db.as_ref(), &self.hub_id).await
    }

    /// **The manager approves one action** (hub#361, PLAN paso 2b rules 2 and 4).
    ///
    /// `requester` is the cashier whose command was refused with
    /// [`RuntimeError::RequiresElevation`]; `req` carries the approver's name + PIN and the exact
    /// action being approved. On success the caller gets an opaque token to present on **one**
    /// retry of that same action ([`elevation`] explains the window).
    ///
    /// The PIN is verified **here**, against `hub_user` — rule 2: the client is never the
    /// authority, and the browser never learns whether four digits were right except through this
    /// answer. Five refusals in a row lock the approver at the HTTP door (the same
    /// `LoginThrottle` the pinpad uses): without a limit, ten thousand combinations typed by a
    /// script make the approval decorative.
    ///
    /// Order of the checks is deliberate — everything that is a fact about the **command** is
    /// answered before the digits are looked at, so an action that could never be approved never
    /// costs a throttle slot and never turns this door into an oracle:
    ///
    /// 1. **A machine principal has nobody to approve for** (`machine_principal`). An API key is
    ///    the hole hub#360 left open; now that an approval grants, it closes here too.
    /// 2. The command exists (`CommandNotFound`) and is not **internal** (`InternalCommand`):
    ///    minting an approval for a door the dispatcher refuses before the permission would hand
    ///    out a token that can never be spent.
    /// 3. The requester **does not already hold** the permission (`not_required`): an approval
    ///    nobody needed is a spendable credential left lying around.
    /// 4. The permission is **elevable** (`not_elevable`, [`permissions::is_elevable`]): rule 5,
    ///    `admin` territory is not approved at the counter — default-deny.
    /// 5. The PIN opens an **active** user (`rejected`).
    /// 6. That user **could have done it themselves** (`approver_cannot`): you cannot approve what
    ///    you have no right to do, so the approval never manufactures authority that did not
    ///    already exist in the hub.
    pub async fn approve_elevation(
        &self,
        requester: &RequestContext,
        req: elevation::ElevationRequest<'_>,
    ) -> Result<elevation::ElevationApproval> {
        let reject = |code: &str, message: &str| RuntimeError::Domain {
            code: format!("{}elevation.{code}", hub_users::CORE_NAMESPACE),
            message: message.to_string(),
        };

        if requester.principal == Principal::Machine {
            return Err(reject(
                "machine_principal",
                "an automated integration cannot be approved: a PIN says who is standing at the \
                 till, and nobody is. Give the key the permission it needs instead.",
            ));
        }

        let cmd = self
            .registry
            .get_command(req.command)
            .ok_or_else(|| RuntimeError::CommandNotFound(req.command.to_string()))?;
        if cmd.def.is_internal(req.command) {
            return Err(RuntimeError::InternalCommand(req.command.to_string()));
        }
        let permission = cmd.def.permission.clone();

        if permissions::has(requester, &permission) {
            return Err(reject(
                "not_required",
                "this action needs no approval: whoever asked for it can already do it.",
            ));
        }
        if !permissions::is_elevable(&self.registry, &permission) {
            return Err(reject(
                "not_elevable",
                "this action is not approved with a PIN: it belongs to whoever administers the \
                 hub, who signs in with their own account.",
            ));
        }

        // **Two presentations of one identity** (hub#658). The PIN resolves NAME + digits; a badge
        // resolves the person on its own. Both land on the same `hub_user`, and everything below
        // this point — including the `approver_cannot` check, which is what rule 5 actually is —
        // reads the ROLE, never how the person proved they were standing there.
        //
        // One answer for all the ways this can fail — an unknown name, a wrong PIN, a card nobody
        // carries, a deactivated user: a dialog at the counter must not become a way to find out
        // who works here, nor which cards this shop has issued.
        let rejected = || {
            reject(
                "rejected",
                "those details do not approve this action. Check the name and the PIN.",
            )
        };
        let (approver, credential) = match req.credential {
            elevation::ApproverCredential::Pin { name, pin } => (
                identity::verify_pin(self.db.as_ref(), &self.hub_id, name, pin)
                    .await?
                    .ok_or_else(rejected)?,
                identity::Credential::pin(),
            ),
            elevation::ApproverCredential::Badge { badge } => {
                let matched = identity::verify_badge(self.db.as_ref(), &self.hub_id, badge)
                    .await?
                    .ok_or_else(rejected)?;
                let credential = identity::Credential::badge(&matched.badge_index);
                (matched.user, credential)
            }
        };

        if !permissions::has(
            &RequestContext::new(
                &requester.hub_id,
                &approver.id,
                identity::session_permissions(&self.registry, &approver.role),
            ),
            &permission,
        ) {
            return Err(reject(
                "approver_cannot",
                "that person cannot approve this action: they do not have the right to do it \
                 themselves.",
            ));
        }

        let token = self.elevation.mint(
            elevation::Binding {
                hub_id: requester.hub_id.clone(),
                requester: requester.user_id.clone(),
                command: req.command.to_string(),
                fingerprint: elevation::fingerprint(req.payload),
                permission: permission.clone(),
            },
            &approver.id,
            credential,
        );
        Ok(elevation::ElevationApproval {
            token,
            permission,
            approved_by: approver.id,
            approver_name: approver.name,
            expires_in_seconds: elevation::GRANT_TTL.as_secs(),
        })
    }

    // ── Personal (core): gestión de TODOS los usuarios del hub. Ver [`hub_users`]. ──────────

    /// Todos los usuarios del hub — incluido el owner cloud sin PIN y los desactivados.
    pub async fn list_hub_users(&self) -> Result<Vec<hub_users::HubUserRow>> {
        hub_users::list(self.db.as_ref(), &self.hub_id).await
    }

    /// Rechaza admitir **una persona más** si el plan ya está lleno (hub#1685). `max_users = 0` =
    /// ilimitado. Lo llama la capa HTTP —que es quien conoce el plan— justo antes de cada puerta
    /// que suma un usuario activo, igual que [`Self::enforce_device_limit`] antes de abrir sesión.
    pub async fn enforce_user_limit(&self, max_users: u32) -> Result<()> {
        hub_users::enforce_user_limit(self.db.as_ref(), &self.hub_id, max_users).await
    }

    /// Cuántas personas ocupan hoy una plaza del plan (usuarios **activos** de este hub).
    pub async fn count_active_users(&self) -> Result<i64> {
        hub_users::count_active_users(self.db.as_ref(), &self.hub_id).await
    }

    /// Alta de un usuario del hub (nombre, rol, email y PIN opcionales). Devuelve su id.
    pub async fn create_hub_user(&self, input: &hub_users::NewHubUser) -> Result<String> {
        hub_users::create(self.db.as_ref(), &self.registry, &self.hub_id, input).await
    }

    /// Cuántos dígitos pide el PIN de este hub (hub#974): 4 o 6, igual para todo el mundo.
    pub async fn pin_length(&self) -> Result<i64> {
        Ok(settings::pin_length_of(self.db.as_ref(), &self.hub_id).await)
    }

    /// Fija la longitud del PIN del hub. Puerta de admin (`PUT /api/settings` la revalida).
    pub async fn set_pin_length(&self, length: i64) -> Result<()> {
        let mut updates = serde_json::Map::new();
        updates.insert(
            pin_policy::PIN_LENGTH_SETTING.to_string(),
            serde_json::json!(length),
        );
        self.set_settings(&updates, "system").await.map(|_| ())
    }

    /// Edición parcial de un usuario del hub; `is_active: Some(false)` es la baja.
    pub async fn update_hub_user(
        &self,
        user_id: &str,
        input: &hub_users::UpdateHubUser,
    ) -> Result<hub_users::HubUserRow> {
        hub_users::update(
            self.db.as_ref(),
            &self.registry,
            &self.hub_id,
            user_id,
            input,
        )
        .await
    }

    /// Roles del hub (catálogo base ∪ módulos activos ∪ en uso) con permisos y miembros.
    pub async fn list_hub_roles(&self) -> Result<Vec<hub_users::HubRole>> {
        hub_users::list_roles(self.db.as_ref(), &self.registry, &self.hub_id).await
    }

    /// Catálogo de roles del hub (paso 2b, hub#352).
    pub async fn role_catalog(&self) -> Result<Vec<roles::CatalogRole>> {
        roles::catalog(self.db.as_ref(), &self.registry, &self.hub_id).await
    }

    /// Activa o desactiva en ESTE hub un rol declarado por un módulo (paso 2b, hub#352).
    pub async fn set_role_active(&self, role_key: &str, active: bool, actor: &str) -> Result<()> {
        roles::set_active(
            self.db.as_ref(),
            &self.registry,
            &self.hub_id,
            role_key,
            active,
            actor,
        )
        .await
    }

    /// **Siembra el owner del hub** desde el env del provisioning (`HUB_OWNER_EMAIL`, ADR-0157): el
    /// owner es el CREADOR del hub. Idempotente (no duplica ni cambia si ya existe). `true` si sembró.
    pub async fn seed_owner(&self, email: &str) -> Result<bool> {
        identity::seed_owner(self.db.as_ref(), &self.hub_id, email).await
    }

    /// Resuelve (o enlaza/provisiona) el `hub_user` de una identidad cloud (mapeo del JWT). Enlaza
    /// por `cloud_user_id`, si no por `email` (owner sembrado / invitado), si no crea con el rol dado.
    ///
    /// `role_floor` es el **suelo** que impone el rol de la cuenta en el Cloud, reevaluado en cada
    /// login (paso 2b regla C, hub#347): sube el rol de una fila existente si se ha quedado corto,
    /// nunca lo baja y nunca concede `owner`. `None` = sin suelo, la fila se devuelve intacta.
    pub async fn get_or_link_cloud_user(
        &self,
        cloud_user_id: &str,
        default_name: &str,
        default_role: &str,
        email: Option<&str>,
        role_floor: Option<&str>,
    ) -> Result<identity::HubUser> {
        identity::get_or_link_cloud_user(
            self.db.as_ref(),
            &self.hub_id,
            cloud_user_id,
            default_name,
            default_role,
            email,
            role_floor,
        )
        .await
    }

    /// **Cierra el acceso local** de una identidad cloud cuyo membresía ha revocado el SaaS (paso 2b
    /// regla D, hub#348): desactiva su `hub_user` (sesión abierta, PIN y pinpad caen con él) y borra
    /// sus sesiones. Idempotente; devuelve cuántas filas cerró.
    pub async fn revoke_cloud_access(
        &self,
        cloud_user_id: &str,
        email: Option<&str>,
    ) -> Result<usize> {
        identity::revoke_cloud_access(self.db.as_ref(), &self.hub_id, cloud_user_id, email).await
    }

    /// **Alta** de un usuario-login por email + rol (flujo admin, ADR-0157 §7). Upsert por email.
    pub async fn create_login_user(&self, email: &str, role: &str) -> Result<identity::HubUser> {
        identity::create_login_user(self.db.as_ref(), &self.hub_id, email, role).await
    }

    /// **Baja** de un usuario-login por email (flujo admin, ADR-0157 §7). Desactiva; `true` si afectó.
    pub async fn deactivate_login_user(&self, email: &str) -> Result<bool> {
        identity::deactivate_login_user(self.db.as_ref(), &self.hub_id, email).await
    }

    /// Lista los usuarios-login del hub (los `hub_user` con email) para el panel admin.
    pub async fn list_login_users(&self) -> Result<Vec<identity::LoginUser>> {
        identity::list_login_users(self.db.as_ref(), &self.hub_id).await
    }

    /// Personas cuyo email **solo** está en su perfil y no se pudo llevar a donde se administra el
    /// acceso (hub#436): su baja NO revoca su membresía hasta que alguien decida qué fila es quién.
    /// Vacío es la respuesta normal. Ver [`access_email`].
    pub async fn unresolved_access_emails(
        &self,
    ) -> Result<Vec<access_email::UnresolvedAccessEmail>> {
        access_email::unresolved(self.db.as_ref(), &self.hub_id).await
    }

    /// Fija (o cambia) el PIN de un usuario existente por id. Dos llamadores, la misma puerta:
    /// la alta de PIN tras el primer login cloud (§2.9, `current_pin: None`, nada que confirmar
    /// todavía) y «Mi perfil» → cambiar mi PIN (hub#1430, self-service, sin pasar por la puerta de
    /// Personal ni su permiso).
    ///
    /// Si el usuario YA tiene un PIN, `current_pin` es OBLIGATORIO y tiene que coincidir con el de
    /// hoy — igual que cambiar cualquier otra contraseña propia. Sin esta comprobación, quien
    /// encuentra la sesión desatendida (el mostrador, «Mi perfil» abierto) podría expulsar al
    /// dueño reescribiéndole el PIN sin saberlo. Decisión de mercado (Zettle, el módulo
    /// `pos_change_pin` de Odoo): piden el PIN actual antes del nuevo en el mismo gesto.
    pub async fn set_pin(&self, user_id: &str, current_pin: Option<&str>, pin: &str) -> Result<()> {
        let candidate = current_pin.unwrap_or_default();
        if let Some(matches) =
            identity::own_pin_matches(self.db.as_ref(), &self.hub_id, user_id, candidate).await?
        {
            if !matches {
                return Err(RuntimeError::Domain {
                    code: format!("{}users.pin_current_mismatch", hub_users::CORE_NAMESPACE),
                    message: "the current PIN does not match".into(),
                });
            }
        }
        // Same rules as Personal (hub#974): length, digits only, not guessable. This is the
        // self-service door and it used to hash whatever arrived.
        let pin = hub_users::clean_pin(pin, self.pin_length().await?)?;
        // And the SAME duplicate guard as Personal (hub#355): a PIN two people share misattributes
        // the till, not just clashes. `ensure_pin_is_free` documents itself as running "on every PIN
        // change" — this door skipped it; reachable any time now (not just once, at cloud login),
        // that gap was worth closing alongside the current-PIN check above.
        hub_users::ensure_pin_is_free(self.db.as_ref(), &self.hub_id, &pin, Some(user_id)).await?;
        identity::set_pin(self.db.as_ref(), &self.hub_id, user_id, &pin).await
    }

    /// Abre una sesión server-side para `user_id`; devuelve el token opaco. `device_id` = identidad
    /// del dispositivo del login (o `None`); se persiste para el límite de dispositivos (ADR-0154).
    pub async fn create_session(
        &self,
        user_id: &str,
        ttl_secs: i64,
        device_id: Option<&str>,
    ) -> Result<String> {
        identity::create_session(self.db.as_ref(), &self.hub_id, user_id, ttl_secs, device_id).await
    }

    /// [`Runtime::create_session`] dejando escrito **con qué se probó la identidad** (hub#658):
    /// es la mitad de la traza que vive en el login. Lo usa la capa HTTP en cada puerta de login.
    pub async fn create_session_with_credential(
        &self,
        user_id: &str,
        ttl_secs: i64,
        device_id: Option<&str>,
        credential: &identity::Credential,
    ) -> Result<String> {
        identity::create_session_with_credential(
            self.db.as_ref(),
            &self.hub_id,
            user_id,
            ttl_secs,
            device_id,
            credential,
        )
        .await
    }

    /// Aplica el límite de dispositivos del plan ANTES de abrir sesión (ADR-0154): con
    /// `max_devices == 1` y `device_id` presente, desaloja las sesiones de otros dispositivos
    /// (*single active device session* con takeover). `0` = ilimitado / sin `device_id` = no-op.
    pub async fn enforce_device_limit(
        &self,
        max_devices: u32,
        device_id: Option<&str>,
    ) -> Result<()> {
        identity::enforce_device_limit(self.db.as_ref(), &self.hub_id, max_devices, device_id).await
    }

    /// Resuelve una sesión válida a su `hub_user` activo (o `None`).
    pub async fn resolve_session(&self, token: &str) -> Result<Option<identity::HubUser>> {
        identity::resolve_session(self.db.as_ref(), &self.hub_id, token).await
    }

    /// Resolves a valid session to its `hub_user` **and to the credential it was opened with**.
    ///
    /// Used by the browser handoff door (pm#196): "can administer" and "typed their password" are
    /// two different questions, and only the second one is answered by this column.
    pub async fn resolve_session_with_credential(
        &self,
        token: &str,
    ) -> Result<Option<(identity::HubUser, identity::Credential)>> {
        identity::resolve_session_with_credential(self.db.as_ref(), &self.hub_id, token).await
    }

    /// Cierra una sesión (logout).
    pub async fn delete_session(&self, token: &str) -> Result<()> {
        identity::delete_session(self.db.as_ref(), &self.hub_id, token).await
    }

    /// Perfil y preferencias del usuario actual, aislados por `(hub_id, user_id)`.
    pub async fn user_profile(&self, user_id: &str) -> Result<user_profile::UserProfile> {
        user_profile::get(self.db.as_ref(), &self.hub_id, user_id).await
    }

    /// Actualiza únicamente el perfil del propio `user_id` resuelto por la sesión HTTP.
    pub async fn update_user_profile(
        &self,
        user_id: &str,
        input: &user_profile::UpdateUserProfile,
    ) -> Result<user_profile::UserProfile> {
        user_profile::update(self.db.as_ref(), &self.hub_id, user_id, input).await
    }

    /// Guarda la ruta relativa de la foto del usuario dentro de `media_dir`.
    pub async fn set_user_avatar(
        &self,
        user_id: &str,
        avatar_path: &str,
    ) -> Result<user_profile::UserProfile> {
        user_profile::set_avatar(self.db.as_ref(), &self.hub_id, user_id, avatar_path).await
    }

    /// The device an id names, or `None` when it names none (hub#454).
    ///
    /// The one id it refuses is **this hub's own**. A device id is a string the client chooses, so
    /// it can only ever NAME a device — but the `hub_id` was worse than an arbitrary string: the
    /// web presented it as its `X-Device-Id`, making every browser one device, and
    /// `GET /api/hub/context` publishes it without a session. Refusing it here is what stops a
    /// browser still running a cached build from writing that shared row back, and what makes a
    /// row restored from an old backup inert.
    ///
    /// Every caller fails closed on `None`, each in its own direction: nothing to trust, not
    /// trusted, the strict mode, no write.
    fn device_named<'a>(&self, device_id: &'a str) -> Option<&'a str> {
        (device_id != self.hub_id).then_some(device_id)
    }

    /// El **hub** al que pertenecen las filas de device-trust, o `None` si este despliegue no dice
    /// cuál es (hub#489).
    ///
    /// `hub_id = ''` es el valor que la migración v23 reserva para «esta fila no nombra hub»: son
    /// las filas anteriores a la columna, y se borran en vez de regalárselas a quien arranque
    /// primero. Devolver `None` aquí es lo que impide que el runtime vuelva a escribirlas —
    /// un hub arrancado sin `HUB_ID` re-crearía justo lo que la migración quita, y una
    /// re-aplicación de la migración borraría entonces confianza viva.
    fn hub_scope(&self) -> Option<&str> {
        (!self.hub_id.is_empty()).then_some(self.hub_id.as_str())
    }

    /// El par `(hub, dispositivo)` que nombra una llamada, o `None` si no nombra un dispositivo
    /// **de este hub**. Falla cerrado por los dos lados: sin hub no hay confianza que conceder, y
    /// el `hub_id` no es un dispositivo (hub#454).
    fn device_of_this_hub<'a>(&'a self, device_id: &'a str) -> Option<(&'a str, &'a str)> {
        Some((self.hub_scope()?, self.device_named(device_id)?))
    }

    /// Marca un dispositivo como de confianza (tras el primer login online). Idempotente (§2.9).
    /// La confianza es **de este hub** (hub#489): la misma tablet puede serlo en dos negocios.
    ///
    /// El dispositivo queda **sin nombre** (hub#494): quien sepa con qué nombre debería nacer usa
    /// [`Self::trust_device_with_default_name`].
    pub async fn trust_device(&self, device_id: &str, label: &str) -> Result<()> {
        self.trust_device_with_default_name(device_id, label, "")
            .await
    }

    /// Igual que [`Self::trust_device`], más el nombre con el que nace el dispositivo la **primera**
    /// vez que este hub lo ve (hub#494).
    ///
    /// `default_name` se escribe **solo en el INSERT**: en un dispositivo ya conocido no toca nada,
    /// porque para entonces el nombre o lo eligió el dueño o es el que se le puso al nacer, y las
    /// dos cosas valen más que lo que traiga el login de turno. Lo que sí sigue reescribiéndose en
    /// cada entrada es `label`, que es otra cosa: quién entró la última vez.
    pub async fn trust_device_with_default_name(
        &self,
        device_id: &str,
        label: &str,
        default_name: &str,
    ) -> Result<()> {
        match self.device_of_this_hub(device_id) {
            Some((hub_id, id)) => {
                identity::trust_device(self.db.as_ref(), hub_id, id, label, default_name).await
            }
            None => Ok(()), // nothing to trust: naming the hub names no device.
        }
    }

    /// `true` si el dispositivo es de confianza **de este hub** (gate del login por PIN, §2.9).
    pub async fn is_device_trusted(&self, device_id: &str) -> Result<bool> {
        match self.device_of_this_hub(device_id) {
            Some((hub_id, id)) => identity::is_device_trusted(self.db.as_ref(), hub_id, id).await,
            None => Ok(false),
        }
    }

    /// Revoca la confianza de un dispositivo (perdido/robado). Idempotente (§2.9). Se lleva con
    /// ella el **modo** del dispositivo (hub#357): la fila borrada es donde vivía.
    pub async fn untrust_device(&self, device_id: &str) -> Result<()> {
        identity::untrust_device(self.db.as_ref(), &self.hub_id, device_id).await
    }

    /// Los dispositivos que este hub conoce, con lo que permite reconocerlos a ojo (hub#455).
    ///
    /// Ojo con lo que se puede creer: el `device_id` y la `label` los elige el **propio
    /// dispositivo** (cabecera `X-Device-Id` y campo `name` del login cloud); el resto —cuándo se
    /// confió, el modo y su auditoría, las sesiones abiertas— lo escribió el hub. Ver
    /// [`devices::TrustedDevice`].
    pub async fn list_devices(&self) -> Result<Vec<devices::TrustedDevice>> {
        devices::list(self.db.as_ref(), &self.hub_id).await
    }

    /// **Corta** un dispositivo perdido (hub#455): cierra sus sesiones abiertas y le retira la
    /// confianza —y con ella el modo `personal` y el login por PIN—. Idempotente.
    ///
    /// Es la pieza que faltaba: [`Self::untrust_device`] ya borraba la fila, pero dejaba viva la
    /// sesión que el dispositivo tuviera abierta (hasta **30 días** en un `personal`, hub#358), que
    /// es justo lo que sigue usando quien se llevó la tablet. Se ejecuta sobre **cualquier** id que
    /// se le nombre —revocar solo quita privilegio—, incluida una fila heredada cuyo id fuese el
    /// del propio hub (hub#454).
    pub async fn revoke_device(&self, device_id: &str) -> Result<devices::Revocation> {
        devices::revoke(self.db.as_ref(), &self.hub_id, device_id).await
    }

    /// **Nombra** un dispositivo que este hub ya conoce (hub#494): «Barra», «Cocina», «Portátil
    /// despacho». Es lo único de la fila que decide el negocio, y por eso es lo único de fiar al
    /// señalar cuál cortar. No crea filas: un dispositivo se lista porque se confió en él, nunca
    /// porque alguien escribió su id.
    pub async fn rename_device(&self, device_id: &str, name: &str) -> Result<devices::Renamed> {
        devices::rename(self.db.as_ref(), &self.hub_id, device_id, name).await
    }

    /// Cómo llama el **negocio** a este dispositivo (hub#494), o `""` si no le puso nombre.
    ///
    /// Es lo mismo que muestra la lista de dispositivos, leído de una fila y no de todas: quien
    /// necesita el nombre del dispositivo que tiene delante —el registro de impresión al darlo de
    /// alta, hub#1560— no tiene por qué enumerar los de todo el negocio, que es una puerta de
    /// administrador a propósito ([`Self::list_devices`]).
    pub async fn device_name(&self, device_id: &str) -> Result<String> {
        match self.device_of_this_hub(device_id) {
            Some((hub_id, id)) => devices::name_of(self.db.as_ref(), hub_id, id).await,
            None => Ok(String::new()), // nombrar al hub no nombra a ningún dispositivo (hub#454).
        }
    }

    /// Qué clase de dispositivo es este: `shared` (mostrador) o `personal` (equipo propio),
    /// paso 2b / hub#357. Un dispositivo que el hub no conoce es **`shared`** — el modo estricto.
    pub async fn device_mode(&self, device_id: &str) -> Result<device_mode::DeviceMode> {
        match self.device_of_this_hub(device_id) {
            Some((hub_id, id)) => device_mode::mode(self.db.as_ref(), hub_id, id).await,
            None => Ok(device_mode::DeviceMode::default()),
        }
    }

    /// Cuánto dura una sesión abierta **en este dispositivo** (segundos), hub#358 + hub#359.
    ///
    /// Lo deciden los **dos** controles a la vez, y gana **el más restrictivo**
    /// ([`pin_policy::effective_session_ttl_secs`], un `min`): el modo del dispositivo dice cuánto
    /// aguanta esta terminal (mostrador = el turno, equipo propio = «recordarme») y el dial del
    /// negocio dice cada cuánto se pregunta quién está en la caja. Ninguno puede **alargar** lo que
    /// el otro acortó: «nunca» no le compra al mostrador la sesión larga de un equipo personal, y
    /// marcar un equipo como personal no lo saca de la política estricta que eligió el negocio.
    ///
    /// Fail-closed igual que el modo: un dispositivo que el hub no conoce —o un cliente que no dice
    /// cuál es— recibe la sesión **corta**, nunca la larga.
    pub async fn session_ttl_for_device(&self, device_id: &str) -> Result<i64> {
        Ok(pin_policy::effective_session_ttl_secs(
            self.device_mode(device_id).await?,
            self.pin_policy().await?,
        ))
    }

    /// Cada cuánto pregunta este hub QUIÉN está en la caja (`always` | `per_shift` | `never`,
    /// hub#359). Un hub que no eligió —o cuyo valor almacenado no se puede leer— **sigue
    /// preguntando**: el default nunca es `never`.
    pub async fn pin_policy(&self) -> Result<pin_policy::PinPolicy> {
        pin_policy::policy(self.db.as_ref(), &self.hub_id).await
    }

    /// Fija el dial del hub. `actor` = quién lo decidió (auditoría); la puerta HTTP
    /// (`PUT /api/settings`) exige sesión **admin**. Escribe por el store de settings, que es la
    /// única puerta de escritura de esta clave.
    pub async fn set_pin_policy(&self, policy: pin_policy::PinPolicy, actor: &str) -> Result<()> {
        pin_policy::set_policy(self.db.as_ref(), &self.hub_id, policy, actor).await
    }

    /// Fija el modo de un dispositivo **ya conocido** (hub#357). `actor` = el `hub_user.id` que lo
    /// decidió; la puerta HTTP exige sesión **admin**. Rechaza un `device_id` que el hub nunca vio:
    /// esto registra una decisión sobre un dispositivo, no lo da de alta.
    pub async fn set_device_mode(
        &self,
        device_id: &str,
        mode: device_mode::DeviceMode,
        actor: &str,
    ) -> Result<()> {
        match self.device_of_this_hub(device_id) {
            Some((hub_id, id)) => {
                device_mode::set_mode(self.db.as_ref(), hub_id, id, mode, actor).await
            }
            None => Err(device_mode::unknown_device(device_id)),
        }
    }

    /// Permisos de una **sesión** con ese rol: los de los módulos + el permiso del core
    /// (`hub.users.view`, ADR-0192). Es lo que debe usar el gate de auth al abrir sesión.
    pub fn session_permissions(&self, role: &str) -> std::collections::HashSet<String> {
        identity::session_permissions(&self.registry, role)
    }

    /// Permisos efectivos del `role` (unión de `role_permissions` de los módulos activos).
    pub fn permissions_for_role(&self, role: &str) -> std::collections::HashSet<String> {
        identity::permissions_for_role(&self.registry, role)
    }

    // ── API pública por módulo: API keys (ADR-0057, public-api.md) ──────────────────────────

    /// Crea una API key para el `hub_id` del despliegue con `scope` (matriz módulo×{r,w}). Devuelve
    /// el token en claro **una sola vez**. `created_by` = identidad del admin que la crea.
    pub async fn create_api_key(
        &self,
        name: &str,
        scope: &api_keys::ApiKeyScope,
        rate_limit_per_minute: i64,
        created_by: &str,
    ) -> Result<api_keys::ApiKeySecret> {
        api_keys::create(
            self.db.as_ref(),
            &self.hub_id,
            name,
            scope,
            rate_limit_per_minute,
            created_by,
        )
        .await
    }

    /// The read-only key the hub issues to **itself** so our own app reads the event stream
    /// through the same door as any integration (hub#504). Idempotent; re-issued after a restore.
    pub async fn ensure_app_api_key(&self) -> Result<String> {
        api_keys::ensure_app_key(self.db.as_ref(), &self.hub_id).await
    }

    /// Resolves a key by **id** (no secret) — the redemption end of a stream ticket (hub#504).
    /// Same refusals as [`Self::resolve_api_key`]: revoked, unknown or another hub's key → `None`.
    pub async fn resolve_api_key_id(
        &self,
        key_id: &str,
    ) -> Result<Option<api_keys::ApiKeyPrincipal>> {
        api_keys::resolve_key_id(self.db.as_ref(), &self.registry, &self.hub_id, key_id).await
    }

    /// Lista las API keys del hub (sin secreto), recientes primero.
    pub async fn list_api_keys(&self) -> Result<Vec<api_keys::ApiKeyInfo>> {
        api_keys::list(self.db.as_ref(), &self.hub_id).await
    }

    /// Rota el secreto de una key (nuevo secreto, invalida el anterior). `None` si no existe.
    pub async fn rotate_api_key(&self, id: &str) -> Result<Option<api_keys::ApiKeySecret>> {
        api_keys::rotate(self.db.as_ref(), &self.hub_id, id).await
    }

    /// Revoca una key (kill-switch inmediato). `false` si no existía.
    pub async fn revoke_api_key(&self, id: &str) -> Result<bool> {
        api_keys::revoke(self.db.as_ref(), &self.hub_id, id).await
    }

    /// Verifica un token `erpl_live_…` y lo resuelve al `RequestContext` (con los permisos del
    /// scope expandido contra el Registry). `None` = token inválido/revocado (el server → 401).
    pub async fn resolve_api_key(&self, token: &str) -> Result<Option<api_keys::ApiKeyPrincipal>> {
        api_keys::verify_and_resolve(self.db.as_ref(), &self.registry, &self.hub_id, token).await
    }

    /// Consume una petición de la cuota durable de una API key autenticada.
    pub async fn consume_api_key_rate_limit(
        &self,
        principal: &api_keys::ApiKeyPrincipal,
    ) -> Result<api_keys::RateLimitDecision> {
        api_keys::consume_rate_limit(
            self.db.as_ref(),
            &principal.key_id,
            principal.rate_limit_per_minute,
        )
        .await
    }

    // ── Settings del hub (store key/value de sistema, scoped por hub_id) ────────────────────────
}
