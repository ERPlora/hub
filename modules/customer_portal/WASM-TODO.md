# customer_portal — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_customer_portal/{models.py,services.py}`. El CRUD plano y
las transiciones de estado simples ya están en SQL declarativo Tier 0 (`commands/*.sql`):
suspend / reactivate / close (con guarda de estado en el `WHERE`) y session revoke.
Lo que sigue es lógica de cripto / tokens / comparación temporal / batch que **no** cabe
en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar) que el runtime
> valida y persiste en una transacción. El reloj (`now`), la generación de tokens
> aleatorios y el hashing son **capacidades del host** invocadas desde el WASM
> (el WASM es determinista: pide aleatoriedad/tiempo al host, no los genera él).

## Capacidades del host requeridas
- `now()` → datetime UTC ISO actual (usado por todos los handlers para fechas y comparación de expiración).
- `random_token(n_bytes)` → `secrets.token_urlsafe(n)` equivalente (tokens de invitación y de sesión).
- `hash_password(password)` → produce `"{salt}${sha256(salt||password)}"` (salt = `token_urlsafe(16)`).
  - **Nota de seguridad** (heredada de services.py): el legacy usa sha256+salt por ser
    dependency-free; en hub-next debería migrarse a **argon2/bcrypt** como capacidad del host.
- `verify_password(password, stored)` → compara en tiempo constante contra `salt$hash`
  (split por `$`, recomputar, `compare_digest`). Solo necesario si se reimplementa el login.

---

## 1. `create_invitation`  (command `customer_portal.invitations.create`)
Origen: `PortalService.create_invitation`.
- Validar `customer_email` no vacío (ya cubierto por schema `required`).
- Generar `invitation_token = random_token(32)`.
- `expires_at = now() + 7 días`.
- Emitir intención de INSERT en `customer_portal_invitation`
  (`customer_email`, `customer_name`, `invitation_token`, `invited_by_ref`, `expires_at`).
- Devolver `{id, customer_email, invitation_token, expires_at}`.
- Emite evento `customer_portal.invitation.created`.

## 2. `accept_invitation`  (command `customer_portal.invitations.accept`)
Origen: `PortalService.accept_invitation` (flujo público multi-paso, NO se puede expresar en una UPDATE).
- Leer la invitación por `invitation_token` (lectura que pide el runtime al handler).
- Guardas (cada una → error tipado):
  - invitación inexistente → `not_found`.
  - `used_at IS NOT NULL` → `already_used`.
  - `expires_at < now()` (normalizar tz: tratar naive como UTC) → `expired`.
  - ya existe `customer_portal_account` con ese `customer_email` en el hub → `email_taken`.
- Intenciones (atómicas):
  - INSERT `customer_portal_account` con
    `customer_name = invitation.customer_name or customer_email`,
    `customer_email`, `password_hash = hash_password(password)`,
    `status='active'`, `email_verified=1`,
    `invited_at = invitation.created_at`, `activated_at = now()`.
  - UPDATE invitación: `used_at = now()`.
- Devolver `{id, customer_email, status}`.
- Emite evento `customer_portal.account.activated`.
- **Permiso**: en legacy NO estaba decorado con `@action` (endpoint público para el cliente
  que redime el token). En hub-next se mapea al permiso mínimo `view_portal`; un flujo
  realmente público (sin usuario) requeriría una capacidad de runtime aparte — decisión de producto.

## 3. `create_session`  (command `customer_portal.sessions.create`)
Origen: `PortalService.create_session`.
- Leer la cuenta por `account_id`.
- Guarda: `status != 'active'` → error `invalid_state` (solo cuentas activas reciben sesión).
- `token = random_token(32)`; `now = now()`; `expires_at = now + 24h`.
- Intenciones (atómicas):
  - INSERT `customer_portal_session` (`account_id`, `session_token`, `expires_at`,
    `is_active=1`, `ip_address`, `user_agent`).
  - UPDATE cuenta: `last_login_at = now`.
- Devolver `{id, account_id, session_token, expires_at}`.
- Emite evento `customer_portal.session.created`.

## 4. `cleanup_expired_sessions`  (command `customer_portal.sessions.cleanup_expired`, tarea programada / admin)
Origen: `PortalService.cleanup_expired_sessions`.
- Leer todas las sesiones con `is_active = 1` del hub.
- Para cada una: normalizar tz de `expires_at` (naive → UTC) y, si `expires_at < now()`,
  emitir intención UPDATE `is_active = 0`.
- Operación batch sobre N filas con comparación temporal por fila → no es una sola UPDATE
  trivial (la comparación de expiración con normalización tz vive en el handler).
- Devolver `{updated: N}`.
- Emite evento `customer_portal.sessions.cleaned`.

## 5. Append de motivo a `notes` en suspend / close (Tier 1, no crítico)
Origen: `suspend_account(reason=...)` y `close_account(reason=...)`.
- Hoy `account_suspend.sql` / `account_close.sql` NO escriben el rastro
  `\n[SUSPENDED] reason` / `\n[CLOSED] reason` en `notes` (el SQL solo cambia `status`).
- Si se quiere conservar ese audit-trail textual, moverlo a un handler WASM que componga el
  nuevo `notes` (lectura de la cuenta + append con prefijo) — capacidad de string del host.
- También aplica la guarda fina de estado del legacy (`already_suspended`, `invalid_state` al
  suspender una cuenta `closed`): en SQL se aproxima con el `WHERE status NOT IN (...)`
  (la fila no se toca), pero el **error tipado** explícito requeriría un handler. No bloqueante.

## 6. `verify_password`  (helper interno, no command)
Origen: `PortalService.verify_password` (no era `@action`, lo usa el flujo de login).
- Comprueba `password` contra `password_hash` de una cuenta `active`.
- No se expone como command (no devuelve datos relevantes por sí mismo); se integraría en
  un futuro flujo de login del portal como capacidad `verify_password` del host. Documentado
  por completitud — sin command asociado en este manifest.
