// Personal (core) — cliente REST del runtime del Hub: `/api/hub/users` + `/api/hub/roles`.
//
// El personal del Hub son sus USUARIOS reales (tabla `hub_user` del core): el owner/administrador
// que entra por Cloud, los admins, y el personal solo-local que entra con PIN. NO es el módulo
// `staff` — ese es un módulo de negocio (profesional reservable, comisiones, horarios) con su
// propia navegación, y en la mayoría de hubs ni está instalado; pedirle la lista era la causa del
// «No se pudo cargar el personal».
//
// Contrato (ver `crates/server/src/hub_users.rs`):
//   GET    /api/hub/users        → HubUser[]   (cualquier sesión de usuario)
//   POST   /api/hub/users        → HubUser     (sesión owner/admin)
//   PUT    /api/hub/users/{id}   → HubUser     (sesión owner/admin; parcial)
//   DELETE /api/hub/users/{id}   → HubUser     (sesión owner/admin; baja = desactivar)
//   GET    /api/hub/roles        → HubRole[]   (cualquier sesión de usuario)
//   PUT    /api/hub/roles/{key}  → HubRole[]   (sesión owner/admin; `{active}` — hub#352)
//
// Mismo transporte que el resto del shell (`runtime.ts`): mismo origen + `runtimeHeaders()`.

import { lockRefusal, type Refusal } from './lock-refusal';
import { hubPinLength } from './pin-length';
import { RUNTIME_URL, runtimeHeaders } from './runtime';

/** Un usuario del hub tal y como lo lista el runtime. */
export interface HubUser {
  id: string;
  name: string;
  /**
   * The address shown: the access email or, without one, the one typed in «My profile»; empty if
   * there is neither. It is not proof of an account — that is `has_account`.
   */
  email: string;
  /**
   * `true` if this person signs in with an erplora.com account (invited by email or already
   * linked). `false` = a PIN (or a badge) is all they have, so administration is not for them
   * (hub#2500). Absent in a runtime older than hub#2500.
   */
  has_account?: boolean;
  role: string;
  /** Id en el Cloud si la identidad está vinculada al portal; `null` en el personal solo-local. */
  cloud_user_id: string | null;
  /** `false` = dado de baja. Sigue listado (histórico y auditoría apuntan a su id). */
  is_active: boolean;
  /**
   * `true` en la ficha del **dueño de la cuenta** (hub#1429). No es un rol —lo que puede hacer sigue
   * saliendo de `role`—: es la marca que el hub deriva del `HUB_OWNER_EMAIL` del aprovisionamiento,
   * y lo único que cambia es que esa ficha solo la edita esa misma persona. Ausente en un runtime
   * anterior a hub#1429, que no manda el campo.
   */
  is_account_owner?: boolean;
  /** `true` si puede entrar con PIN local; el owner normalmente entra por Cloud. */
  has_pin: boolean;
  /**
   * `true` si lleva una **placa** enrolada (hub#658). Se enseña aparte de `has_pin` porque son
   * credenciales hermanas e independientes: revocar la tarjeta no toca el PIN, y volver a solo-PIN
   * tiene que ser siempre posible. Ausente en un runtime anterior a hub#658.
   */
  has_badge?: boolean;
  created_at: string;
  /**
   * Por qué el backfill v19 no pudo llevar el email de esta persona a donde se administra el acceso
   * (hub#436/#463). Ausente —lo normal— si no hay nada que resolver, y también en un runtime
   * anterior a hub#463, que no manda el campo.
   */
  access_email_conflict?: AccessEmailConflict;
}

/**
 * Las dos razones por las que una fila puede quedarse sin email de ACCESO, y son **decisiones
 * distintas** para quien administra:
 *
 * * `another_row_answers_for_it` — otra identidad ya responde por esa dirección: la salida es
 *   editar el email de una de las dos.
 * * `two_profiles_claim_it` — dos perfiles la reclaman y nada dice cuál es la persona: la salida es
 *   dar de baja la duplicada. Fusionarlas es irreversible, y por eso la migración no lo hizo.
 */
export type AccessEmailConflict = 'another_row_answers_for_it' | 'two_profiles_claim_it';

const ACCESS_EMAIL_CONFLICTS: readonly string[] = [
  'another_row_answers_for_it',
  'two_profiles_claim_it',
];

/**
 * El motivo por el que el email de esta fila **no revoca nada**, o `null` si no hay ninguno.
 *
 * Existe porque la lista de Personal resuelve la dirección con
 * `COALESCE(hub_user.email, perfil.email)`: una fila así enseña un email de aspecto normal mientras
 * su baja no revoca la membresía en el SaaS y su primer login aterriza en otra fila. Hasta hub#463
 * lo único que lo decía era el log de arranque.
 *
 * Un motivo que este shell no conoce se trata como **ausencia**: pintar una insignia sin frase
 * detrás es peor que el silencio que esto viene a arreglar.
 */
export function accessEmailWarningOf(user: HubUser): AccessEmailConflict | null {
  const reason = user.access_email_conflict;
  return reason && ACCESS_EMAIL_CONFLICTS.includes(reason) ? reason : null;
}

/** De dónde sale un rol del catálogo (hub#352). */
export type HubRoleSource =
  /** Rol base del core (`admin`/`manager`/`employee`): siempre en el catálogo y siempre activo. */
  | { kind: 'core' }
  /** Declarado en el `roles[]` de un módulo instalado y activo. */
  | { kind: 'module'; module_id: string }
  /** Ya no lo declara nadie, pero algún usuario todavía lo lleva (módulo desinstalado). */
  | { kind: 'in_use' };

/** Un rol del hub: catálogo base del core ∪ roles que declaran los módulos activos ∪ roles en uso. */
export interface HubRole {
  name: string;
  /** Etiqueta legible en **inglés canónico** (ADR-0055); la traducción va por i18n. */
  label: string;
  /** Rol base del que cuelga. Un rol base cuelga de sí mismo; uno huérfano, de nada. */
  extends: string;
  source: HubRoleSource;
  /** ¿Está vivo en ESTE hub? Los base, siempre; los declarados, solo si el admin los activó. */
  active: boolean;
  /** Permisos efectivos que concede (unión de `role_permissions` de los módulos activos). */
  permissions: number;
  /** Usuarios activos con ese rol. */
  members: number;
}

/**
 * Alta. Es **exhaustiva** (plan paso 2b): la casilla `local` elige cuál de las dos identidades se
 * crea, y las dos son la MISMA fila `hub_user`.
 *
 *  - `local: true` (hub#355) → esta persona existe solo en la BD de este hub: **nombre + PIN**, sin
 *    email y sin nada en el SaaS. Guardas: PIN obligatorio, ningún rol administrativo y un nombre
 *    que el hub no conozca ya.
 *  - `local` ausente/`false` (hub#356) → **usuario de cuenta**: el **email es obligatorio**, el
 *    SaaS le manda la invitación y la contraseña la pone él (el administrador no la conoce jamás).
 *    El `pin` sigue siendo opcional —lo necesita quien además atiende la barra— y, si se teclea,
 *    pasa por las mismas reglas que el del usuario local.
 */
export interface NewHubUser {
  name: string;
  email: string;
  role: string;
  pin: string;
  /** La placa que rellena el lector (o que se teclea, para un iButton). Vacío = sin placa. */
  badge?: string;
  local?: boolean;
}

/**
 * Edición parcial: solo viaja lo que se toca. `pin: ''` retira el PIN y `badge: ''` revoca la placa
 * **sin tocar el PIN** — la revocación independiente es el contrato entero de hub#658.
 */
export interface HubUserPatch {
  name?: string;
  email?: string;
  role?: string;
  is_active?: boolean;
  pin?: string;
  badge?: string;
}

interface Envelope<T> {
  ok?: boolean;
  data?: T;
  // hub#1190: `field`/`reason` travel beside the code on an `invalid_field` refusal (ADR-0398 §6).
  // hub#1258: `module`/`query` travel beside the code on a PLATFORM refusal — `error_payload`
  // (`crates/server/src/lib.rs`) sets `module` for `module_not_installed`/`module_inactive`/
  // `missing_dependency` and `query` for `read_unavailable`, the same fields the SDK's
  // `platformFailureMessage` (hub#1102) reads to name the app in its own sentence.
  error?:
    | { message?: string; code?: string; field?: string; reason?: string; module?: string; query?: string }
    | string;
}

/**
 * Rechazo del runtime con su **código estable** (`hub.users.pin_in_use`, …) cuando lo trae. El
 * mensaje del runtime está en inglés y es solo el respaldo: lo que se enseña se traduce por i18n
 * contra el código (ver [`hubUserErrorKey`]).
 */
export class HubUsersError extends Error {
  constructor(
    message: string,
    readonly code?: string,
    // hub#1190: `field` and `reason` of an `invalid_field` refusal (ADR-0398 §6), carried as DATA
    // so the screen translates by code instead of painting the runtime's English sentence.
    readonly field?: string,
    readonly reason?: string,
    // hub#1258: `module`/`query` of a PLATFORM refusal (`module_not_installed`, `module_inactive`,
    // `missing_dependency`, `read_unavailable`), so the screen names the app instead of parsing it
    // out of a sentence — same rule as `field`/`reason` above.
    readonly module?: string,
    readonly query?: string,
    // hub#2518: the wait of a `too_many_attempts` refusal, read by `lockRefusal` like the
    // pinpad's (`RuntimeError.retryAfterSecs`, hub#2283).
    readonly retryAfterSecs?: number,
  ) {
    super(message);
    this.name = 'HubUsersError';
  }
}

/** Mensaje legible del envelope de error del runtime (`{ok:false,error:{message}}` o string). */
function errorMessage(body: unknown, fallback: string): string {
  const env = body as Envelope<unknown> | undefined;
  const error = env?.error;
  if (typeof error === 'string') return error;
  return error?.message ?? fallback;
}

/** Código estable del envelope, si el error viene del namespace del core (`hub.users.*`). */
function errorCode(body: unknown): string | undefined {
  const error = (body as Envelope<unknown> | undefined)?.error;
  return typeof error === 'string' ? undefined : error?.code;
}

/**
 * The lock of the PIN doors (hub#2518) is a PLATFORM refusal, shaped like the pinpad's:
 * `{ok:false, error:"<sentence>", code:"too_many_attempts", retry_after_secs}` — code and wait at
 * the top, beside a plain-string `error`.
 */
function topLevelLock(body: unknown): [string | undefined, number | undefined] {
  const env = body as { code?: unknown; retry_after_secs?: unknown } | undefined;
  const code = typeof env?.code === 'string' ? env.code : undefined;
  const secs = typeof env?.retry_after_secs === 'number' ? env.retry_after_secs : undefined;
  return [code, secs];
}

/** `field` and `reason` of the envelope when the refusal names one (hub#1190). */
function errorFieldReason(body: unknown): [string | undefined, string | undefined] {
  const error = (body as Envelope<unknown> | undefined)?.error;
  if (typeof error === 'string' || !error) return [undefined, undefined];
  return [error.field, error.reason];
}

/** `module` and `query` of the envelope when a PLATFORM refusal names one (hub#1258). */
function errorModuleQuery(body: unknown): [string | undefined, string | undefined] {
  const error = (body as Envelope<unknown> | undefined)?.error;
  if (typeof error === 'string' || !error) return [undefined, undefined];
  return [error.module, error.query];
}

function failed(body: unknown, fallback: string): HubUsersError {
  const [field, reason] = errorFieldReason(body);
  const [module, query] = errorModuleQuery(body);
  const [lockCode, retryAfterSecs] = topLevelLock(body);
  return new HubUsersError(
    errorMessage(body, fallback),
    errorCode(body) ?? lockCode,
    field,
    reason,
    module,
    query,
    retryAfterSecs,
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { ...runtimeHeaders() };
  if (init?.body) headers['Content-Type'] = 'application/json';
  const res = await fetch(`${RUNTIME_URL}${path}`, { ...init, headers });
  const body = await res.json().catch(() => undefined);
  if (!res.ok) throw failed(body, `${path} → ${res.status}`);
  const env = body as Envelope<T>;
  if (env?.ok === false) throw failed(body, `${path} → error`);
  return (env?.data ?? (body as T)) as T;
}

/** Todos los usuarios del hub (activos e inactivos, con PIN y sin él). */
export async function listHubUsers(): Promise<HubUser[]> {
  const data = await request<HubUser[]>('/api/hub/users');
  return Array.isArray(data) ? data : [];
}

/** Roles del hub con sus permisos y sus miembros. */
export async function listHubRoles(): Promise<HubRole[]> {
  const data = await request<HubRole[]>('/api/hub/roles');
  return Array.isArray(data) ? data : [];
}

/**
 * Rechazo de la activación de un rol que CONSERVA el motivo del runtime (hub#352/hub#353).
 *
 * El runtime rechaza por dos razones distintas —«es un rol base, siempre está encendido» y «no lo
 * declara ningún módulo instalado»— y cada una pide algo distinto del administrador: la primera es
 * un límite del producto, la segunda se resuelve instalando el módulo que trae ese rol. Aplanarlas
 * a «no se pudo activar» convierte la guarda en un interruptor mudo. Mismo contrato que
 * `ModuleActionError` (hub#314): `code` presente = hay un motivo que enseñar; sin él es un fallo de
 * transporte y la UI se queda con su mensaje genérico.
 */
export class RoleActivationError extends Error {
  readonly code?: string;
  /** hub#1190: `field`/`reason` of an `invalid_field` refusal, so the panel translates by code. */
  readonly field?: string;
  readonly reason?: string;
  /** hub#1258: `module`/`query` of a PLATFORM refusal — same rule as `field`/`reason` above. */
  readonly module?: string;
  readonly query?: string;

  constructor(
    message: string,
    code?: string,
    field?: string,
    reason?: string,
    module?: string,
    query?: string,
  ) {
    super(message);
    this.name = 'RoleActivationError';
    this.code = code;
    this.field = field;
    this.reason = reason;
    this.module = module;
    this.query = query;
  }
}

/**
 * Enciende o apaga un rol del catálogo **en este hub**. Requiere sesión owner/admin.
 *
 * Devuelve el catálogo YA actualizado (lo que responde el endpoint): la pantalla se queda con el
 * estado que afirma el servidor en vez de pintar un optimismo local que un rechazo dejaría mintiendo.
 */
export async function setRoleActivation(key: string, active: boolean): Promise<HubRole[]> {
  const res = await fetch(`${RUNTIME_URL}/api/hub/roles/${encodeURIComponent(key)}`, {
    method: 'PUT',
    headers: { ...runtimeHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ active }),
  });
  const env = (await res.json().catch(() => ({}))) as {
    ok?: boolean;
    data?: HubRole[];
    error?: { code?: string; message?: string; field?: string; reason?: string; module?: string; query?: string };
  };
  if (!res.ok || env.ok === false) {
    throw new RoleActivationError(
      env.error?.message ?? `roles/${key} → ${res.status}`,
      env.error?.code,
      env.error?.field,
      env.error?.reason,
      env.error?.module,
      env.error?.query,
    );
  }
  return Array.isArray(env.data) ? env.data : [];
}

/**
 * De un catálogo, los roles que se le pueden DAR hoy a una persona en este hub.
 *
 * Espejo EN UI de `roles::ensure_assignable` del runtime, que sigue siendo la autoridad y
 * revalida: un rol **declarado por un módulo** solo se asigna si el hub lo ha encendido. Los
 * demás no se estrechan — un rol **base** es el contrato congelado del core, y uno **huérfano**
 * (tecleado a mano antes de que hubiera catálogo, o el resto de un módulo desinstalado) hay que
 * poder seguir reasignándolo o se rompen hubs que funcionan.
 *
 * Sirve para no ofrecer en el alta lo que el servidor va a rechazar: un desplegable con roles
 * inasignables hace que apagar un rol parezca que no hace nada.
 */
export function assignableRoles(roles: HubRole[]): HubRole[] {
  return roles.filter((role) => role.source?.kind !== 'module' || role.active);
}

/** Alta de usuario. Requiere sesión owner/admin. */
export function createHubUser(input: NewHubUser): Promise<HubUser> {
  return request<HubUser>('/api/hub/users', { method: 'POST', body: JSON.stringify(input) });
}

/** Edición parcial. Requiere sesión owner/admin. */
export function updateHubUser(id: string, patch: HubUserPatch): Promise<HubUser> {
  return request<HubUser>(`/api/hub/users/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

/** Baja = **desactivar**, nunca borrar. Requiere sesión owner/admin. */
export function deactivateHubUser(id: string): Promise<HubUser> {
  return request<HubUser>(`/api/hub/users/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

/** Cómo entra un usuario al Hub. `none` = existe como persona, pero no puede iniciar sesión. */
export type HubAccess = 'pin' | 'pin_badge' | 'badge' | 'cloud' | 'none';

/**
 * Vía de acceso de un usuario. El **PIN manda** cuando hay varias: es la del día a día en el POS.
 * `none` no es un error — es el registro de alguien que trabaja en el negocio pero no usa el Hub
 * (p. ej. un profesional reservable en la agenda). Distinguirlo importa: decir «cuenta online» de
 * quien no tiene cuenta hace creer que puede entrar.
 *
 * La **placa** (hub#658) se dice aparte y no absorbida en «PIN», porque quien administra necesita
 * ver de un vistazo quién lleva tarjeta: es lo que hay que revocar cuando alguien pierde la suya, y
 * es la credencial que se presta. `badge` a secas solo lo produce un usuario de cuenta que retiró su
 * PIN — el runtime no deja que una placa sea la única puerta de nadie.
 */
export function accessOf(user: HubUser): HubAccess {
  if (user.has_pin) return user.has_badge ? 'pin_badge' : 'pin';
  if (user.has_badge) return 'badge';
  return user.cloud_user_id ? 'cloud' : 'none';
}

// ── Alta de usuario LOCAL (plan paso 2b, hub#355) ─────────────────────────────────────────────

/** Roles que administran el hub (mismo conjunto que `is_admin_role` en el runtime). */
const ADMIN_ROLES = ['owner', 'admin'];

/** Prefijo de los códigos de rechazo del core en `/api/hub/users` (namespace reservado, ADR-0192). */
/** Prefijo de los códigos de dominio `hub.users.*` (hub#355 y siguientes). Exportado para que otra
 *  puerta que recibe el MISMO catálogo de códigos por otro cliente (self-service «Mi perfil» →
 *  cambiar mi PIN, hub#1430, vía `RuntimeError` de `lib/cloud.ts`) pueda pelarlo igual sin
 *  duplicar el literal. */
export const HUB_USERS_ERROR_PREFIX = 'hub.users.';

/**
 * Los códigos con los que el runtime cuenta que **no pudo sincronizar el acceso con el Cloud**
 * (hub#1214), que es la otra mitad de un alta/baja: la ficha local se guarda en este hub, pero
 * quién puede ENTRAR lo administra el SaaS (ADR-0157 §7).
 *
 * Van sin prefijo —son códigos de plataforma, no del namespace `hub.users.*`— y cada uno pide algo
 * distinto de quien administra, que es justo por lo que no se aplanan a «no se pudo guardar»:
 *
 *  - `cloud_rate_limited` → espera y vuelve a intentarlo; no hay nada que corregir.
 *  - `cloud_rejected` → el Cloud rechaza el cambio: hay algo que corregir (normalmente el email).
 *  - `cloud_unreachable` → no contestó; se reintenta.
 *  - `not_enrolled` → este hub no está enrolado; lo resuelve soporte, no quien está guardando.
 *
 * Hasta hub#1214 el runtime mandaba aquí el **cuerpo crudo del SaaS**
 * (`el SaaS respondió 429: {"detail":"Request was throttled…"}`) y la pantalla lo pintaba tal cual.
 */
export const ACCESS_SYNC_ERRORS = [
  'cloud_rate_limited',
  'cloud_rejected',
  'cloud_unreachable',
  'not_enrolled',
] as const;

/**
 * Clave i18n del motivo de un rechazo del runtime (`hub.users.pin_in_use` → `pin_in_use`), o
 * `undefined` si el error no trae uno (fallo de red, 401 del gate, un error del navegador).
 *
 * Es lo que permite enseñar el motivo **traducido**: el runtime responde en inglés a propósito
 * (regla del código en inglés) y el Hub se ve en español.
 *
 * Dos familias, una sola clave: los rechazos de NEGOCIO del core (`hub.users.*`, que se leen sin su
 * prefijo) y los de **sincronización del acceso** ([`ACCESS_SYNC_ERRORS`], hub#1214), que ya llegan
 * con el nombre de su clave. Un código que no sea de ninguna de las dos devuelve `undefined` a
 * propósito: la pantalla se queda entonces con la frase que vino, que dice más que un genérico.
 */
export function hubUserErrorKey(error: unknown): string | undefined {
  const code = error instanceof HubUsersError ? error.code : undefined;
  if (!code) return undefined;
  if (code.startsWith(HUB_USERS_ERROR_PREFIX)) return code.slice(HUB_USERS_ERROR_PREFIX.length);
  return (ACCESS_SYNC_ERRORS as readonly string[]).includes(code) ? code : undefined;
}

/**
 * The sentence of a spent PIN budget (hub#2518), or `undefined` for any other refusal. Creating a
 * person or editing their record with a PIN spends the EDITOR's tries —the same budget as changing
 * one's own PIN (hub#2499)— and past it the hub answers `too_many_attempts` instead of saying
 * whether the number is taken. The minutes are the pinpad's rounding (`lockRefusal`).
 */
export function pinLockRefusal(error: unknown): Refusal | undefined {
  if (!(error instanceof HubUsersError) || error.code !== 'too_many_attempts') return undefined;
  const { minutes } = lockRefusal(error);
  return minutes === undefined
    ? { key: 'employeeForm.pinTooManyAttemptsNoWait' }
    : { key: 'employeeForm.pinTooManyAttempts', minutes };
}

/**
 * ¿Es este uno de los PIN que se prueban primero? Todo el mismo dígito (`0000`) o una cuesta
 * seguida, arriba o abajo (`1234`, `4321`). **Espejo** de `is_guessable_pin` del runtime, que es
 * quien manda; aquí solo sirve para no hacer pulsar «Crear» para enterarse.
 */
export function isGuessablePin(pin: string): boolean {
  const digits = [...pin].map(Number);
  if (digits.length < 2 || digits.some(Number.isNaN)) return true;
  const stepIs = (step: number) => digits.every((d, i) => i === 0 || d - digits[i - 1] === step);
  return stepIs(0) || stepIs(1) || stepIs(-1);
}

/**
 * Motivo por el que el runtime rechazaría este alta **local**, o `''` si es admisible. Espejo EN UI
 * de `ensure_local_identity` (`crates/runtime/src/hub_users.rs`), igual que [`canDeactivate`] lo es
 * del guard de la baja: la autoridad sigue siendo el runtime, que revalida y responde 409.
 *
 * `pin_in_use` **no** se puede adelantar desde aquí: los PIN se guardan hasheados (argon2id con sal
 * propia) y el shell no los ve nunca. Ese motivo llega del servidor, por [`hubUserErrorKey`].
 */
export function localUserIssue(
  input: { name: string; role: string; pin: string },
  users: HubUser[],
): string {
  const pin = input.pin.trim();
  if (!pin) return 'local_needs_pin';
  if (pin.length !== hubPinLength.value || !/^\d+$/.test(pin)) return 'pin_length';
  if (isGuessablePin(pin)) return 'pin_too_simple';
  if (ADMIN_ROLES.includes(input.role.trim().toLowerCase())) return 'local_cannot_administer';
  // Activos e inactivos: una persona = una fila, y un homónimo al lado de quien fue dado de baja
  // le devuelve por la espalda un PIN que funciona (hub#348).
  const name = input.name.trim().toLowerCase();
  if (users.some((u) => u.name.trim().toLowerCase() === name)) return 'name_taken';
  return '';
}

// ── Alta de usuario de CUENTA (plan paso 2b, hub#356) ─────────────────────────────────────────

/**
 * Roles que el **SaaS** sabe poner en una membresía (su `HUB_ROLES`) y, por tanto, los únicos que
 * puede llevar un usuario de cuenta. Espejo de `is_grantable_account_role` en el runtime.
 *
 * `owner` **no** está: la propiedad del hub sale de `HUB_OWNER_EMAIL` (ADR-0157), no de una
 * invitación. Y un rol que declara un módulo (`kitchen`, `waiter`…) es de ESTE hub y de ninguno
 * más, así que es del personal local.
 */
const ACCOUNT_ROLES = ['admin', 'manager', 'employee'];

/** Forma mínima de un email (la misma que valida el runtime). */
function looksLikeEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/**
 * Motivo por el que el runtime rechazaría este alta **de cuenta**, o `''` si es admisible. Gemelo
 * de [`localUserIssue`] para la otra identidad del paso 2b: la autoridad sigue siendo el runtime,
 * que revalida y responde 409.
 *
 * Aquí sí se puede adelantar el email duplicado —el censo que pinta Personal ya trae el email de
 * cada fila, activos e inactivos—, y merece la pena: es el rechazo que significa «esta persona ya
 * existe, reincorpórala», no «vuelve a intentarlo».
 */
export function accountUserIssue(
  input: { email: string; role: string; pin: string },
  users: HubUser[],
): string {
  const email = input.email.trim().toLowerCase();
  if (!email) return 'account_needs_email';
  if (!looksLikeEmail(email)) return 'invalid_email';
  if (!ACCOUNT_ROLES.includes(input.role.trim().toLowerCase())) return 'account_role_not_grantable';
  // Activos e inactivos: una persona = una fila, y volver a invitar a quien fue dado de baja
  // resucitaría por la espalda una membresía que alguien revocó (hub#348).
  if (users.some((u) => u.email.trim().toLowerCase() === email)) return 'email_taken';
  // El PIN es OPCIONAL para un usuario de cuenta —entra con su cuenta— pero, si lo teclea, es la
  // misma credencial que la del usuario local y pasa por las mismas reglas.
  const pin = input.pin.trim();
  if (!pin) return '';
  if (pin.length !== hubPinLength.value || !/^\d+$/.test(pin)) return 'pin_length';
  if (isGuessablePin(pin)) return 'pin_too_simple';
  return '';
}

/**
 * ¿Puede `actorId` editar la ficha de `targetId`? Espejo en UI del guard del servidor
 * (`hub.users.owner_row`, hub#1429): **la ficha del dueño de la cuenta solo la edita el dueño** —su
 * PIN, su placa, su nombre—, porque una credencial nueva en esa fila es una entrada al TPV COMO el
 * dueño y el SaaS no puede vigilarlo (el hub le habla con la credencial de máquina, que allí tiene
 * rango de owner). La propiedad se traspasa en la cuenta de ERPlora, no en esta pantalla, que es
 * como lo resuelven Shopify, Square, Toast, Lightspeed y Vagaro.
 *
 * Solo para mostrar/ocultar la acción: la autoridad sigue siendo el runtime, que revalida y
 * responde 403. Un runtime anterior a hub#1429 no manda la marca y aquí no cambia nada.
 */
export function canEditUser(users: HubUser[], actorId: string, targetId: string): boolean {
  const target = users.find((u) => u.id === targetId);
  if (!target) return false;
  return !target.is_account_owner || target.id === actorId;
}

/** Is this one of the roles that administer the hub (`is_admin_role` in the runtime)? */
export function isAdminRole(role: string): boolean {
  return ADMIN_ROLES.includes(role.trim().toLowerCase());
}

/** ¿Este usuario administra el hub y está activo? */
function isActiveAdmin(user: HubUser): boolean {
  return user.is_active && ADMIN_ROLES.includes(user.role.toLowerCase());
}

/**
 * ¿Se le puede ofrecer al admin la acción «dar de baja» sobre `targetId`? Espejo EN UI del guard
 * del servidor (`crates/server/src/hub_users.rs`): nadie se da de baja a sí mismo y el hub no se
 * queda sin ningún administrador activo. Es solo para mostrar/ocultar la acción — la autoridad
 * sigue siendo el runtime, que revalida y responde 400.
 */
export function canDeactivate(users: HubUser[], actorId: string, targetId: string): boolean {
  const target = users.find((u) => u.id === targetId);
  if (!target || !target.is_active) return false;
  if (target.id === actorId) return false;
  if (!canEditUser(users, actorId, targetId)) return false;
  if (!isActiveAdmin(target)) return true;
  return users.some((u) => u.id !== targetId && isActiveAdmin(u));
}
