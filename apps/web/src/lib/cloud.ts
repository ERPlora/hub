// Cliente del Cloud Portal. hub NUNCA habla con LLMs directamente; auth/marketplace/
// billing van por aquí (ARQUITECTURA.md §2.1–2.3). Si el Cloud no es accesible (sandbox),
// las llamadas lanzan y la capa de auth degrada a modo demo.
import { config, isLocalHub } from './config';
import { loginHeaders, resolveDeviceId } from './device';
import { getLocale } from '../i18n';
import { beginRequest, endRequest } from './shell';
import { getHubSession } from './session';

export interface CloudUser {
  id: string;
  name: string;
  email: string;
  /** URL de la foto de perfil. El Cloud aun NO expone este campo (el modelo User
   *  no tiene ImageField); queda preparado para cuando se añada (avatar_url/avatar). */
  avatarUrl?: string | null;
}

export interface LoginResult {
  access: string;
  refresh: string;
  user: CloudUser;
  /** Hub de ESTE dispositivo, creado/resuelto por el Cloud en el primer login (§2.9b) cuando el
   *  cliente manda `X-Client-Type: hub-desktop|hub-local` + `X-Device-Id`. Es el PK del registro
   *  `Hub` en la BD del Cloud → se adopta como `X-Hub-Id`. `undefined` en web-pwa pura. */
  hubId?: string;
}

// --- Login 2-pasos (2FA por OTP de email, ERPlora/saas#994) -------------------
// El SaaS cambió `POST /api/v1/auth/login/` a 2 pasos:
//   · Paso 1: 401 con body {two_factor_required: true, ticket, method: 'email', expires_in}.
//   · Paso 2: POST {ticket, code} a /api/v1/auth/login/2fa/ → {access, refresh, hub_id}.
// Un código erróneo responde 401 con un ticket NUEVO (single-use) en el body: el cliente DEBE
// adoptar ese ticket para reintentar, nunca reusar el anterior ya consumido. El `ticket` vive
// SOLO en memoria del componente (nunca en localStorage): es transitorio y monouso.
export interface TwoFactorChallenge {
  /** Ticket monouso emitido por el Cloud; viaja al /2fa/ en el paso 2. */
  ticket: string;
  /** Canal del OTP (hoy siempre 'email'). */
  method: string;
  /** TTL del challenge en segundos. */
  expiresIn: number;
}

/**
 * Lanzado por [`cloudLogin`] y [`cloudLogin2fa`] cuando el Cloud exige 2FA (401 con
 * `two_factor_required`). El llamador muestra la pantalla de OTP y, al tener el código, llama a
 * [`cloudLogin2fa`] con el `ticket` del challenge. Un código erróneo lanza DE NUEVO este error,
 * esta vez con el ticket RENOVADO del Cloud: el reintentador debe usar el nuevo `ticket`.
 */
export class TwoFactorRequiredError extends Error {
  readonly ticket: string;
  readonly method: string;
  readonly expiresIn: number;
  constructor(challenge: TwoFactorChallenge) {
    super('two_factor_required');
    this.name = 'TwoFactorRequiredError';
    this.ticket = challenge.ticket;
    this.method = challenge.method;
    this.expiresIn = challenge.expiresIn;
  }
}

export interface CloudMarketplaceModule {
  id: string;
  name: string;
  description: string;
  priceLabel: string;
  priceAmount: string | null;
  priceInterval: 'month' | 'year' | null;
  isFree: boolean;
  moduleType: 'free' | 'one_time' | 'subscription' | string;
  category: string;
  installed: boolean;
  available: boolean;
  version?: string;
}

// --- Token store (JWT del usuario activo) -----------------------------------
// El acceso a billing/marketplace requiere `Authorization: Bearer` (spec: security
// Bearer). Persistimos el access+refresh del login en localStorage.
const TOKENS = { access: 'erplora.access', refresh: 'erplora.refresh' };

export function setTokens(access: string, refresh: string): void {
  try {
    localStorage.setItem(TOKENS.access, access);
    localStorage.setItem(TOKENS.refresh, refresh);
  } catch { /* ignore */ }
}
export function clearTokens(): void {
  try {
    localStorage.removeItem(TOKENS.access);
    localStorage.removeItem(TOKENS.refresh);
  } catch { /* ignore */ }
}
export function getAccessToken(): string | null {
  try { return localStorage.getItem(TOKENS.access); } catch { return null; }
}
function getRefreshToken(): string | null {
  try { return localStorage.getItem(TOKENS.refresh); } catch { return null; }
}

/**
 * El runtime local/dev (hub_id vacío o DEV_HUB_ID) mantiene una sesión Runtime/PIN independiente
 * del JWT Cloud. ADR-0159: correr dentro del shell Tauri ya NO cuenta — el shell es un cliente
 * fino de la MISMA PWA cloud, así que la expiración de sesión se comporta igual que en el
 * navegador (la rama "Tauri enrolado" era del producto Hub Local, retirado por ADR-0154).
 */
export function hasIndependentLocalSession(): boolean {
  return isLocalHub();
}

// --- Refresh-on-401 (rotación de tokens del usuario activo) ------------------
// Contrato Cloud: POST /api/v1/auth/refresh/ {refresh} → {access, refresh}. En un 401
// refrescamos UNA vez, rotamos AMBOS tokens y reintentamos la llamada original. Si el
// refresh falla en Hub Cloud, limpiamos la sesión y mandamos a /login (sesión expirada de
// verdad). En Hub Local, la sesión del runtime/PIN es independiente: se limpian únicamente
// las credenciales Cloud caducadas y la vista consumidora muestra su estado recuperable.

/** Hook de fin de sesión. El shell lo registra para limpiar estado reactivo + redirigir. */
let onSessionExpired: (() => void) | null = null;
export function setOnSessionExpired(fn: () => void): void {
  onSessionExpired = fn;
}

/** Limpia tokens, avisa al shell y, por defecto, redirige a /login. */
function expireSession(): void {
  clearTokens();
  if (onSessionExpired) {
    onSessionExpired();
  } else if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
    window.location.assign('/login');
  }
}

// --- Hub borrado/revocado (Cloud 410 `hub_not_found`) -----------------------
// Distinto del fin de sesión por token caducado (401 → refresh): aquí la fila del hub ya no existe
// en el Cloud. El shell registra el hook para olvidar la identidad de máquina local (`forget_hub`)
// + logout → /login; el siguiente login re-registra por `X-Device-Id` (§2.9b). Lo disparan tanto el
// gate de entitlement (Tauri) como CUALQUIER llamada hub-scoped que reciba un 410 (marketplace, etc.).
let onHubGone: (() => void) | null = null;
let warnedHubGoneLocal = false;
export function setOnHubGone(fn: () => void): void {
  onHubGone = fn;
}
export function triggerHubGone(): void {
  // ADR-0064: un hub LOCAL/dev NO debe autoexpulsarse ante `hub_not_found` (el Cloud no gobierna su
  // registro). Se degrada a offline (el gate de entitlement queda permisivo) en vez de logout en
  // bucle, que dejaba al usuario sin shell (sin menú). Solo los hubs CLOUD reales hacen logout.
  if (isLocalHub()) {
    if (!warnedHubGoneLocal) {
      console.warn('[hub] entitlement: hub_not_found en hub local → modo offline (sin logout)');
      warnedHubGoneLocal = true;
    }
    return;
  }
  onHubGone?.();
}

/** Evita refresh-storms: si ya hay un refresh en vuelo, las demás llamadas lo esperan. */
let refreshing: Promise<string | null> | null = null;

/** Intenta refrescar el access token. Rota AMBOS tokens. Devuelve el nuevo access o null. */
async function refreshTokens(): Promise<string | null> {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    const refresh = getRefreshToken();
    if (!refresh) return null;
    try {
      const res = await fetch(`${config.cloudApiUrl}/api/v1/auth/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Client-Type': 'hub' },
        body: JSON.stringify({ refresh }),
      });
      if (!res.ok) return null;
      const data = (await res.json()) as { access?: string; refresh?: string };
      if (!data.access) return null;
      // Rota ambos: el access nuevo y el refresh nuevo (rotating refresh tokens del Cloud).
      setTokens(data.access, data.refresh ?? refresh);
      return data.access;
    } catch {
      return null;
    }
  })();
  try {
    return await refreshing;
  } finally {
    refreshing = null;
  }
}

/** `fetch` con auth + reintento único en 401 vía refresh. Base de get/post. */
async function authedFetch(path: string, init: RequestInit, timeoutMs = 8000): Promise<Response> {
  beginRequest(); // barra de progreso de la topbar
  const doFetch = (token: string | null): Promise<Response> => {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    const headers: Record<string, string> = {
      'X-Client-Type': 'hub',
      ...((init.headers as Record<string, string>) ?? {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(config.hubId ? { 'X-Hub-Id': config.hubId } : {}),
    };
    return fetch(`${config.cloudApiUrl}${path}`, { ...init, headers, signal: ctrl.signal })
      .finally(() => clearTimeout(t));
  };

  try {
    let res = await doFetch(getAccessToken());
    if (res.status === 401) {
      const fresh = await refreshTokens();
      if (fresh) {
        res = await doFetch(fresh); // reintento único con el token rotado
      } else if (hasIndependentLocalSession()) {
        // Un JWT Cloud ausente/caducado NO invalida la sesión local del runtime dev. Billing y
        // otras superficies atribuidas al usuario degradan a su estado "cuenta Cloud requerida",
        // pero el usuario conserva el shell, sus permisos locales y el contexto de trabajo.
        clearTokens();
      } else {
        expireSession();
      }
    }
    // Cloud `hub_not_found` (410): el hub fue borrado/revocado → olvidar identidad + logout.
    if (res.status === 410) triggerHubGone();
    return res;
  } finally {
    endRequest();
  }
}

async function get<T>(path: string, timeoutMs = 8000): Promise<T> {
  const res = await authedFetch(path, { method: 'GET' }, timeoutMs);
  if (!res.ok) throw new Error(`cloud ${path} → ${res.status}`);
  return (await res.json()) as T;
}

// --- Llamadas hub-scoped vía el RUNTIME local (no directas al Cloud) ---------
// marketplace + entitlement los firma el RUNTIME con el token de MÁQUINA del hub (X-Hub-Token),
// que es un secreto y NO debe vivir en el navegador. El web pega al runtime local; el runtime
// añade la credencial y proxea al Cloud. Reenviamos el JWT del usuario como FALLBACK para dev /
// Tauri sin enrolar (el runtime prefiere su token de máquina cuando lo tiene). RUNTIME_URL se
// define aquí (no se importa de ./runtime) para no crear un ciclo de módulos.
// Default: "" = mismo origen siempre (prod: el hub sirve el dist; dev: rutas relativas → proxy
// Vite hacia :8787, sin CORS). La URL absoluta :8787 en dev rompía por CORS.
const RUNTIME_URL: string =
  (import.meta.env.VITE_RUNTIME_URL as string | undefined) || '';

async function runtimeGet<T>(path: string, timeoutMs = 8000): Promise<T> {
  const call = (token: string | null): Promise<Response> => {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    const headers: Record<string, string> = {
      'Accept-Language': getLocale(),
    };
    const session = getHubSession();
    if (session) headers['X-Hub-Session'] = session;
    if (config.hubId) headers['X-Hub-Id'] = config.hubId;
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch(`${RUNTIME_URL}${path}`, {
      headers,
      signal: ctrl.signal,
      // Los estados 410/401 de un Hub revocado son cacheables por algunos navegadores. Una
      // identidad recién registrada o un catálogo recién publicado debe revalidarse de verdad.
      cache: 'no-store',
    }).finally(() => clearTimeout(t));
  };
  beginRequest();
  try {
    let res = await call(getAccessToken());
    if (res.status === 401) {
      const fresh = await refreshTokens();
      if (fresh) res = await call(fresh);
    }
    if (res.status === 410) {
      // Cloud `hub_not_found` (hub borrado/revocado): reacciona igual que el gate de entitlement.
      triggerHubGone();
      throw new Error(`runtime ${path} → hub_not_found`);
    }
    if (!res.ok) throw new Error(`runtime ${path} → ${res.status}`);
    return (await res.json()) as T;
  } finally {
    endRequest();
  }
}

// --- Sesión server-side del runtime (auth local, ARQUITECTURA.md §2.9) ------
// El JWT del Cloud prueba QUIÉN es el usuario; la autoridad de permisos es LOCAL. Tras el login
// cloud (o por PIN) el runtime abre una sesión (`hub_session`) y devuelve un token opaco que el
// frontend manda como `X-Hub-Session` en cada query/command. Estas tres llamadas pegan al RUNTIME
// local (no al Cloud): mintear sesión desde el JWT, login por PIN, y fijar el PIN del usuario.

export interface HubSessionResult {
  token: string;
  user: { id: string; name: string; role: string };
  permissions: string[];
}

export interface CourierSessionResult extends HubSessionResult {
  access: string;
  refresh: string;
  cloud_user: CloudUser;
}

async function runtimePost<T>(path: string, body: unknown, headers: Record<string, string>): Promise<T> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 8000);
  beginRequest();
  try {
    const res = await fetch(`${RUNTIME_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headers },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    const data = (await res.json().catch(() => ({}))) as { ok?: boolean; error?: string } & T;
    if (!res.ok || data.ok === false) {
      throw new Error(data.error ?? `runtime ${path} → ${res.status}`);
    }
    return data;
  } finally {
    clearTimeout(t);
    endRequest();
  }
}

/** Abre una sesión local en el runtime a partir del JWT del usuario (login cloud). `name` se usa
 *  para el `hub_user` local (y para el posterior login por PIN, que resuelve por nombre). */
export async function runtimeCloudSession(
  access: string,
  name: string,
  email?: string,
): Promise<HubSessionResult> {
  return runtimePost<HubSessionResult>(
    '/api/auth/cloud',
    { name, email },
    { Authorization: `Bearer ${access}` },
  );
}

/** Redeems the short-lived shell courier through the same-origin runtime.  The runtime binds the
 * code to its machine identity and performs the Cloud exchange server-to-server. */
export async function runtimeCourierSession(
  code: string,
  deviceId?: string,
): Promise<CourierSessionResult> {
  return runtimePost<CourierSessionResult>(
    '/api/auth/courier',
    { code, ...(deviceId ? { device_id: deviceId } : {}) },
    {},
  );
}

/** Login local por PIN contra el runtime → sesión server-side. Va con el `device_id` que este
 * cliente pueda acreditar: con device-trust activo el hub exige identificar el dispositivo
 * (hub#330), y sin él el PIN se rechaza en vez de colarse por el hueco de antes. */
export async function runtimePinLogin(name: string, pin: string): Promise<HubSessionResult> {
  const deviceId = await resolveDeviceId();
  return runtimePost<HubSessionResult>(
    '/api/auth/pin',
    { name, pin, ...(deviceId ? { device_id: deviceId } : {}) },
    {},
  );
}

/** Fija el PIN del usuario de la sesión actual (alta de PIN tras el primer login cloud). */
export async function runtimeSetPin(pin: string, sessionToken: string): Promise<void> {
  await runtimePost<{ ok: boolean }>('/api/auth/set-pin', { pin }, { 'X-Hub-Session': sessionToken });
}

/** Revoca la sesión server-side del runtime (logout). Best-effort: no lanza si el runtime falla. */
export async function runtimeLogout(sessionToken: string): Promise<void> {
  try {
    await fetch(`${RUNTIME_URL}/api/auth/logout`, {
      method: 'POST',
      headers: { 'X-Hub-Session': sessionToken },
    });
  } catch {
    /* el token local se borra igualmente; la fila caduca por TTL */
  }
}

// --- Entitlement de módulos (gate de arranque, ARQUITECTURA.md §2.10) -------
// Camino WEB (online): pide directamente el endpoint del Cloud. El camino TAURI usa el
// comando `validate_entitlement` (caché offline + gracia) — ver lib/entitlement.ts.
export interface EntitledModuleInfo {
  moduleId: string;
  tier: string;
  version: string;
}

/** Lista de módulos que ESTE hub puede montar (según las compras/entitlement de la org).
 *  Vía el runtime local (firma con el token de máquina del hub). */
export async function cloudEntitlement(): Promise<{ modules: EntitledModuleInfo[]; blockedModules: string[] }> {
  const data = await runtimeGet<{
    modules?: Array<{ module_id?: string; tier?: string; version?: string }>;
    // Bloque ADITIVO del proxy del runtime (ADR-0114 §6): módulos de pago bloqueados
    // por la revalidación híbrida (no-entitled del servidor o gracia vencida).
    revalidation?: { blocked_modules?: string[] };
  }>('/api/entitlement');
  const modules = (data.modules ?? []).map((m) => ({
    moduleId: String(m.module_id ?? ''),
    tier: String(m.tier ?? 'basic'),
    version: String(m.version ?? ''),
  }));
  const blockedModules = (data.revalidation?.blocked_modules ?? []).map(String).filter(Boolean);
  return { modules, blockedModules };
}

// --- Billing: facturas y suscripciones (datos reales del Cloud) -------------
// Contrato: cloud/config/urls.py → /api/v1/billing/{invoices,subscriptions}/
// Schemas: InvoiceList / Subscription (cloud/ERPlora Cloud API.yaml).
export interface CloudInvoice {
  id: number;
  number: string;
  status: 'draft' | 'open' | 'paid' | 'void' | 'uncollectible';
  total: number;
  currency: string;
  issueDate: string;
  dueDate: string;
  paidDate: string | null;
}

export interface CloudSubscription {
  id: number;
  planName: string;
  planPrice: number;
  status: 'draft' | 'open' | 'paid' | 'void' | 'uncollectible';
  billingCycle: string;
  currentPeriodEnd: string | null;
  cancelAtPeriodEnd: boolean;
}

function asArray(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data as Record<string, unknown>[];
  const r = (data as { results?: unknown[] }).results;
  return Array.isArray(r) ? (r as Record<string, unknown>[]) : [];
}

const VALID_STATUS = ['draft', 'open', 'paid', 'void', 'uncollectible'] as const;
function normStatus(s: unknown): CloudInvoice['status'] {
  return (VALID_STATUS as readonly string[]).includes(String(s)) ? (s as CloudInvoice['status']) : 'open';
}

/** Facturas del usuario/hub desde el Cloud. */
export async function cloudInvoices(): Promise<CloudInvoice[]> {
  const data = await get<unknown>('/api/v1/billing/invoices/');
  return asArray(data).map((r) => ({
    id: Number(r.id),
    number: String(r.invoice_number ?? r.number ?? r.id),
    status: normStatus(r.status),
    total: Number(r.total ?? 0),
    currency: String(r.currency ?? 'EUR'),
    issueDate: String(r.issue_date ?? r.created_at ?? ''),
    dueDate: String(r.due_date ?? ''),
    paidDate: (r.paid_date as string | null) ?? null,
  }));
}

/** Suscripciones activas del usuario/hub desde el Cloud. */
export async function cloudSubscriptions(): Promise<CloudSubscription[]> {
  const data = await get<unknown>('/api/v1/billing/subscriptions/');
  return asArray(data).map((r) => ({
    id: Number(r.id),
    planName: String(r.plan_name ?? r.name ?? ''),
    planPrice: Number(r.plan_price ?? 0),
    status: normStatus(r.status),
    billingCycle: String(r.billing_cycle ?? ''),
    currentPeriodEnd: (r.current_period_end as string | null) ?? null,
    cancelAtPeriodEnd: Boolean(r.cancel_at_period_end),
  }));
}

async function post<T>(
  path: string,
  body: unknown,
  timeoutMs = 8000,
  extraHeaders: Record<string, string> = {},
): Promise<T> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  beginRequest();
  try {
    const res = await fetch(`${config.cloudApiUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Client-Type': 'hub', ...extraHeaders },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (!res.ok) throw new Error(`cloud ${path} → ${res.status}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(t);
    endRequest();
  }
}

/** Login email+password contra el Cloud (primer setup / dispositivo no confiable).
 *
 *  Login 2-pasos (ERPlora/saas#994): si el Cloud exige 2FA, el `POST /auth/login/` responde
 *  `401 {two_factor_required, ticket, method, expires_in}`. Esta función lee ese body (que el
 *  `post()` genérico descarta) y lanza [`TwoFactorRequiredError`] con el `ticket`. El llamador
 *  pide entonces el OTP y completa con [`cloudLogin2fa`]. Cualquier otro error (credenciales,
 *  red) sube como `Error` normal — el llamador lo mapea a su mensaje. */
export async function cloudLogin(email: string, password: string): Promise<LoginResult> {
  // En Tauri esto añade X-Client-Type: hub-desktop|hub-local + X-Device-Id para que el Cloud
  // cree/resuelva el hub de ESTE dispositivo (ARQUITECTURA.md §2.9b). En web pura va como 'hub'.
  const headers = await loginHeaders();
  const res = await loginRequest('/api/v1/auth/login/', { email, password }, headers);
  const challenge = await twoFactorChallengeIfPresent(res);
  if (challenge) throw new TwoFactorRequiredError(challenge);
  if (!res.ok) throw new Error(`cloud /api/v1/auth/login/ → ${res.status}`);
  const tokens = (await res.json()) as { access: string; refresh: string; hub_id?: string };
  const me = await meRequest(tokens.access);
  return { access: tokens.access, refresh: tokens.refresh, user: me, hubId: tokens.hub_id };
}

/** Paso 2 del login 2-pasos (ERPlora/saas#994): `POST /api/v1/auth/login/2fa/ {ticket, code}`
 *  → `{access, refresh, hub_id}`. Devuelve un [`LoginResult`] con la MISMA forma que
 *  [`cloudLogin`], para reusar el flujo de finalización de login.
 *
 *  Reintento: un código erróneo responde `401` con un ticket NUEVO (single-use) en el body; esta
 *  función lo lanza como [`TwoFactorRequiredError`] con el ticket renovado, de modo que el
 *  llamador debe adoptar `error.ticket` para reintentar (nunca reusar el anterior ya gastado). */
export async function cloudLogin2fa(ticket: string, code: string): Promise<LoginResult> {
  const headers = await loginHeaders();
  const res = await loginRequest('/api/v1/auth/login/2fa/', { ticket, code }, headers);
  const challenge = await twoFactorChallengeIfPresent(res);
  if (challenge) throw new TwoFactorRequiredError(challenge);
  if (!res.ok) throw new Error(`cloud /api/v1/auth/login/2fa/ → ${res.status}`);
  const tokens = (await res.json()) as { access: string; refresh: string; hub_id?: string };
  const me = await meRequest(tokens.access);
  return { access: tokens.access, refresh: tokens.refresh, user: me, hubId: tokens.hub_id };
}

// `post()` genérico descarta el body en un non-2xx; el login 2-pasos necesita leer el 401 (para
// detectar `two_factor_required` y el ticket renovado). Este helper hace el mismo POST pero
// devuelve el `Response` sin lanzar, dejando al llamador interpretar status + body.
async function loginRequest(
  path: string,
  body: unknown,
  extraHeaders: Record<string, string>,
  timeoutMs = 8000,
): Promise<Response> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  beginRequest();
  try {
    return await fetch(`${config.cloudApiUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Client-Type': 'hub', ...extraHeaders },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
  } finally {
    clearTimeout(t);
    endRequest();
  }
}

/** Lee el body de un 401 y, si trae `two_factor_required: true`, devuelve el challenge con el
 *  ticket. Para cualquier otra respuesta (2xx, 401 sin 2FA, etc.) devuelve `null`. Best-effort:
 *  si el body no es JSON válido se trata como ausencia de challenge. */
async function twoFactorChallengeIfPresent(res: Response): Promise<TwoFactorChallenge | null> {
  if (res.status !== 401) return null;
  // Clonamos antes de leer para no consumir el stream si el llamador quiere el body de un 2xx.
  let raw: Record<string, unknown>;
  try {
    raw = (await res.clone().json()) as Record<string, unknown>;
  } catch {
    return null;
  }
  if (raw.two_factor_required === true && typeof raw.ticket === 'string' && raw.ticket) {
    const method = typeof raw.method === 'string' && raw.method ? raw.method : 'email';
    const expiresIn = Number.isFinite(raw.expires_in) ? Number(raw.expires_in) : 300;
    return { ticket: raw.ticket, method, expiresIn };
  }
  return null;
}

// --- «Continuar con Google» (ADR-0157 §8) ----------------------------------
// El Hub NUNCA habla con Google. Abre el OAuth del SaaS con
// `next=/auth/hub-bridge/?callback=<callback-del-hub>`: allauth solo redirige a rutas del PROPIO
// SaaS (un `next` cross-host se descarta y caería a /dashboard/), y es `/auth/hub-bridge/` quien
// emite el **código de un solo uso** y redirige al hub como `<callback>?code=` (validando el host
// contra su allowlist). El Hub lo canjea (`session-exchange`) por `{access, refresh}` y sigue
// EXACTAMENTE el flujo de `cloudLogin` (mint de sesión local, etc.).

/** URL del OAuth de Google DEL SaaS. `callbackUrl` es la ruta de retorno del hub (absoluta) que
 *  recibirá el `code`; viaja dentro del `next` (bridge del SaaS), doblemente encodeada. */
export function googleLoginUrl(callbackUrl: string): string {
  const bridge = `/auth/hub-bridge/?callback=${encodeURIComponent(callbackUrl)}`;
  return `${config.cloudApiUrl}/auth/google/login/?next=${encodeURIComponent(bridge)}`;
}

/** Canjea el **código de un solo uso** del retorno OAuth por tokens de sesión (ADR-0157 §8):
 *  `POST /api/v1/auth/session-exchange/ {code}` → `{access, refresh}`. Devuelve un [`LoginResult`]
 *  con la MISMA forma que [`cloudLogin`], para reusar tal cual el flujo de finalización de login. */
export async function exchangeGoogleCode(code: string): Promise<LoginResult> {
  const tokens = await post<{ access: string; refresh: string; hub_id?: string }>(
    '/api/v1/auth/session-exchange/',
    { code },
    8000,
    await loginHeaders(),
  );
  const me = await meRequest(tokens.access);
  return { access: tokens.access, refresh: tokens.refresh, user: me, hubId: tokens.hub_id };
}

function positiveDecimal(value: unknown): string | null {
  if (value === null || value === undefined || value === '') return null;
  const amount = Number(value);
  return Number.isFinite(amount) && amount > 0 ? String(value) : null;
}

export function normalizeMarketplaceModule(raw: Record<string, unknown>): CloudMarketplaceModule {
  // El id DEBE ser el slug del módulo (`module_id`, p.ej. "inventory"), no el id numérico del
  // catálogo Cloud (`raw.id`, p.ej. 362): es lo que el runtime usa como clave de instalación,
  // caché y desinstalación. Preferimos module_id/slug y caemos a id numérico solo como último.
  const id = String(raw.module_id ?? raw.slug ?? raw.id ?? raw.name);
  const moduleType = String(raw.module_type ?? (raw.is_free ? 'free' : ''));
  const isFree = raw.is_free === true || moduleType === 'free';
  const priceAmount = isFree
    ? null
    : positiveDecimal(
        raw.price_from
        ?? (moduleType === 'subscription'
          ? raw.subscription_price_monthly ?? raw.monthly_price
          : raw.price),
      );
  const interval =
    raw.subscription_interval === 'year'
      ? 'year'
      : raw.subscription_interval === 'month'
        ? 'month'
        : moduleType === 'subscription'
          ? 'month'
          : null;
  const subcategory = raw.primary_subcategory as Record<string, unknown> | null | undefined;
  return {
    id,
    name: String(raw.name ?? raw.title ?? id),
    description: String(raw.description ?? raw.short_description ?? raw.summary ?? ''),
    priceLabel: typeof raw.price_label === 'string' ? raw.price_label : '',
    priceAmount,
    priceInterval: interval,
    isFree,
    moduleType,
    category: String(
      raw.category
      ?? subcategory?.category_name
      ?? raw.functional_unit_name
      ?? raw.functional_unit
      ?? raw.unit
      ?? 'Marketplace',
    ),
    installed: Boolean(raw.installed ?? raw.is_installed ?? raw.active),
    available: Boolean(raw.can_install ?? raw.is_active ?? true) && raw.is_coming_soon !== true,
    version: raw.version ? String(raw.version) : undefined,
  };
}

/** Catálogo real del Marketplace vía el runtime local. Un Hub real firma con su token de máquina;
 *  Demo usa el endpoint público de metadatos del SaaS. Nunca hay una lista local alternativa. */
export async function cloudMarketplaceModules(): Promise<CloudMarketplaceModule[]> {
  const data = await runtimeGet<unknown>('/api/marketplace/catalog');
  const items = Array.isArray(data)
    ? data
    : Array.isArray((data as { results?: unknown[] }).results)
      ? (data as { results: unknown[] }).results
      : Array.isArray((data as { modules?: unknown[] }).modules)
        ? (data as { modules: unknown[] }).modules
        : [];

  return items.map((item) => normalizeMarketplaceModule(item as Record<string, unknown>));
}

// --- Plan de un módulo: suscripción + compra/upgrade/cancelación (plano "compra = usuario") ---
// Contrato Cloud (auth JWT de usuario + X-Hub-Id, DIRECTO al Cloud, NO al runtime):
//   GET  /api/v1/hub/device/module-subscription/?module=<slug>
//   POST /api/v1/marketplace/modules/{module}/purchase/           (module = pk|slug|module_id)
//   POST /api/v1/marketplace/modules/{module}/cancel-subscription/
//   GET  /api/v1/marketplace/modules/{module}/check_ownership/
// El ViewSet del Cloud resuelve `{module}` por pk numérico, slug o module_id (api_views.get_object),
// así que aquí pasamos el SLUG del módulo (lo que conoce el Hub) tal cual.

/** Estado de la suscripción de un módulo (GET module-subscription). */
export type ModuleSubscriptionStatus =
  | 'active'
  | 'trialing'
  | 'expired'
  | 'none'
  | 'canceled'
  | 'past_due';

export interface CloudModuleSubscription {
  status: ModuleSubscriptionStatus;
  /** Fin del periodo de prueba (ISO) o null. */
  trialEnd: string | null;
  /** Fin del periodo de facturación actual (ISO) o null. */
  periodEnd: string | null;
}

const SUB_STATUS = ['active', 'trialing', 'expired', 'none', 'canceled', 'past_due'] as const;
function normSubStatus(s: unknown): ModuleSubscriptionStatus {
  return (SUB_STATUS as readonly string[]).includes(String(s)) ? (s as ModuleSubscriptionStatus) : 'none';
}

/** Estado de plan del módulo para ESTE hub (auth usuario + X-Hub-Id). */
export async function cloudModuleSubscription(moduleSlug: string): Promise<CloudModuleSubscription> {
  const data = await get<{ status?: string; trial_end?: string | null; period_end?: string | null }>(
    `/api/v1/hub/device/module-subscription/?module=${encodeURIComponent(moduleSlug)}`,
  );
  return {
    status: normSubStatus(data.status),
    trialEnd: data.trial_end ?? null,
    periodEnd: data.period_end ?? null,
  };
}

// La compra/cancelación/ownership desde el Hub se RETIRÓ (ADR-0114 + hub#119): el Hub no
// vende — ModulePlanPanel/AppsPage abren el marketplace del SaaS por deep-link (openExternal)
// y el estado se refleja vía cloudModuleSubscription + entitlement (recheck-on-focus).

async function meRequest(access: string): Promise<CloudUser> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 8000);
  try {
    const res = await fetch(`${config.cloudApiUrl}/api/v1/auth/me/`, {
      headers: { Authorization: `Bearer ${access}` },
      signal: ctrl.signal,
    });
    if (!res.ok) throw new Error(`cloud /me → ${res.status}`);
    const raw = (await res.json()) as Record<string, unknown>;
    return {
      id: String(raw.id),
      name: String(raw.name ?? ''),
      email: String(raw.email ?? ''),
      // El Cloud aun no manda foto; leemos defensivamente el nombre que tendra.
      avatarUrl: (raw.avatar_url ?? raw.avatar ?? null) as string | null,
    };
  } finally {
    clearTimeout(t);
  }
}
