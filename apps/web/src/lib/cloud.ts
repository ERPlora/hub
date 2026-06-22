// Cliente del Cloud Portal. hub NUNCA habla con LLMs directamente; auth/marketplace/
// billing van por aquí (ARQUITECTURA.md §2.1–2.3). Si el Cloud no es accesible (sandbox),
// las llamadas lanzan y la capa de auth degrada a modo demo.
import { config } from './config';
import { loginHeaders } from './device';
import { beginRequest, endRequest } from './shell';

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

export interface CloudMarketplaceModule {
  id: string;
  name: string;
  description: string;
  priceLabel: string;
  category: string;
  installed: boolean;
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

// --- Refresh-on-401 (rotación de tokens del usuario activo) ------------------
// Contrato Cloud: POST /api/v1/auth/refresh/ {refresh} → {access, refresh}. En un 401
// refrescamos UNA vez, rotamos AMBOS tokens y reintentamos la llamada original. Si el
// refresh falla, limpiamos la sesión y mandamos a /login (sesión expirada de verdad).

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
export function setOnHubGone(fn: () => void): void {
  onHubGone = fn;
}
export function triggerHubGone(): void {
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
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
    return fetch(`${RUNTIME_URL}${path}`, { headers, signal: ctrl.signal }).finally(() =>
      clearTimeout(t),
    );
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
export async function runtimeCloudSession(access: string, name: string): Promise<HubSessionResult> {
  return runtimePost<HubSessionResult>('/api/auth/cloud', { name }, { Authorization: `Bearer ${access}` });
}

/** Login local por PIN contra el runtime → sesión server-side. */
export async function runtimePinLogin(name: string, pin: string): Promise<HubSessionResult> {
  return runtimePost<HubSessionResult>('/api/auth/pin', { name, pin }, {});
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

/** Lista de módulos que ESTE hub puede montar (según deployment_mode + compras de la org).
 *  Vía el runtime local (firma con el token de máquina del hub). */
export async function cloudEntitlement(): Promise<{ modules: EntitledModuleInfo[] }> {
  const data = await runtimeGet<{ modules?: Array<{ module_id?: string; tier?: string; version?: string }> }>(
    '/api/entitlement',
  );
  const modules = (data.modules ?? []).map((m) => ({
    moduleId: String(m.module_id ?? ''),
    tier: String(m.tier ?? 'basic'),
    version: String(m.version ?? ''),
  }));
  return { modules };
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

/** Login email+password contra el Cloud (primer setup / dispositivo no confiable). */
export async function cloudLogin(email: string, password: string): Promise<LoginResult> {
  // En Tauri esto añade X-Client-Type: hub-desktop|hub-local + X-Device-Id para que el Cloud
  // cree/resuelva el hub de ESTE dispositivo (ARQUITECTURA.md §2.9b). En web pura va como 'hub'.
  const tokens = await post<{ access: string; refresh: string; hub_id?: string }>(
    '/api/v1/auth/login/',
    { email, password },
    8000,
    await loginHeaders(),
  );
  const me = await meRequest(tokens.access);
  return { access: tokens.access, refresh: tokens.refresh, user: me, hubId: tokens.hub_id };
}

function normalizeMarketplaceModule(raw: Record<string, unknown>): CloudMarketplaceModule {
  // El id DEBE ser el slug del módulo (`module_id`, p.ej. "inventory"), no el id numérico del
  // catálogo Cloud (`raw.id`, p.ej. 362): es lo que el runtime usa como clave de instalación,
  // caché y desinstalación. Preferimos module_id/slug y caemos a id numérico solo como último.
  const id = String(raw.module_id ?? raw.slug ?? raw.id ?? raw.name);
  const price = raw.price_label ?? raw.price ?? raw.monthly_price ?? raw.pricing;
  return {
    id,
    name: String(raw.name ?? raw.title ?? id),
    description: String(raw.description ?? raw.short_description ?? raw.summary ?? ''),
    priceLabel: price === 0 || price === '0' || price === 'Gratis' ? 'Gratis' : String(price ?? ''),
    category: String(raw.category ?? raw.functional_unit ?? raw.unit ?? 'Marketplace'),
    installed: Boolean(raw.installed ?? raw.is_installed ?? raw.active),
  };
}

/** Catálogo del Marketplace vía el runtime local (firma con el token de máquina del hub, que
 *  proxea a Cloud `/api/v1/marketplace/modules/`). En demo degrada a datos locales. */
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
