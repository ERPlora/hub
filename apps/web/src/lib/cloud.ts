// Cliente del Cloud Portal. hub-next NUNCA habla con LLMs directamente; auth/marketplace/
// billing van por aquí (ARQUITECTURA.md §2.1–2.3). Si el Cloud no es accesible (sandbox),
// las llamadas lanzan y la capa de auth degrada a modo demo.
import { config } from './config';

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
  firstTime: boolean;
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

async function get<T>(path: string, timeoutMs = 8000): Promise<T> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  const token = getAccessToken();
  try {
    const res = await fetch(`${config.cloudApiUrl}${path}`, {
      headers: {
        'X-Client-Type': 'hub-next',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(config.hubId ? { 'X-Hub-Id': config.hubId } : {}),
      },
      signal: ctrl.signal,
    });
    if (!res.ok) throw new Error(`cloud ${path} → ${res.status}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(t);
  }
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

async function post<T>(path: string, body: unknown, timeoutMs = 8000): Promise<T> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${config.cloudApiUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Client-Type': 'hub-next' },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (!res.ok) throw new Error(`cloud ${path} → ${res.status}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(t);
  }
}

/** Login email+password contra el Cloud (primer setup / dispositivo no confiable). */
export async function cloudLogin(email: string, password: string): Promise<LoginResult> {
  const tokens = await post<{ access: string; refresh: string }>('/api/v1/auth/login/', { email, password });
  const me = await meRequest(tokens.access);
  return { access: tokens.access, refresh: tokens.refresh, user: me, firstTime: false };
}

function normalizeMarketplaceModule(raw: Record<string, unknown>): CloudMarketplaceModule {
  const id = String(raw.id ?? raw.module_id ?? raw.slug ?? raw.name);
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

/** Catálogo del Marketplace desde el Cloud Portal. En demo degrada a datos locales. */
export async function cloudMarketplaceModules(): Promise<CloudMarketplaceModule[]> {
  // Contrato del hub actual: apps/marketplace/api.py expone este proxy y el proxy
  // consulta Cloud en /api/v1/marketplace/modules/.
  const data = await get<unknown>('/api/v1/modules/marketplace/catalog/');
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
