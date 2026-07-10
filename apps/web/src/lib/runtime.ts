// Bootstrap del transporte hacia el runtime local (Axum) del Hub.
//
// Decisión del humano (3): data-path LOCAL end-to-end primero → hablamos con el runtime
// Axum local (default http://127.0.0.1:8787), config-driven vía VITE_RUNTIME_URL para que
// pueda apuntar al Cloud más adelante. ARQUITECTURA.md §7.5–7.6.
//
// El hub_id NO se elige en UI (decisión 2): se obtiene del runtime en el boot
// (`GET /api/hub/context`) y se usa como X-Hub-Id en TODAS las llamadas.
//
// Expone:
//   - getClient() singleton (ErploraClient sobre HttpWsTransport)
//   - clientInjectionKey (provide/inject de Vue) para inyectar el cliente a las vistas
//   - bootHubContext() — se llama una vez en main.ts; resuelve hub_id y lo guarda en config
import type { InjectionKey } from 'vue';
import { ref } from 'vue';
import { ErploraClient, HttpWsTransport, BridgeClient } from '@erplora/module-sdk';
import { config } from './config';
import { getAccessToken } from './cloud';
import { getBridgeToken } from './bridge-client';
import { getHubSession } from './session';
import { beginRequest, endRequest } from './shell';
import { getLocale, bootHubLanguage } from '../i18n';
import { hubSettings } from './hub-settings';
import { hubCurrency, publishHubCurrency } from './money';

/**
 * Base URL del runtime local del Hub. Config-driven (VITE_RUNTIME_URL).
 * Default: "" = MISMO ORIGEN siempre. En PRODUCCIÓN (build) el propio hub sirve este dist en el
 * mismo host:puerto que /api y /ws. En DEV (`vite dev`) las rutas relativas (/api, /ws) pasan por
 * el PROXY de Vite hacia :8787 (mismo origen → sin CORS; el runtime Axum no expone CORS). Usar la
 * URL absoluta :8787 en dev rompía por CORS (fetch cross-origin desde :5173).
 * `VITE_RUNTIME_URL` sigue teniendo prioridad si se define.
 */
export const RUNTIME_URL: string =
  (import.meta.env.VITE_RUNTIME_URL as string | undefined) || '';

/** Usuario con PIN del hub (para el grid de login local). */
export interface PinUser {
  id: string;
  name: string;
  role: string;
}

/** Respuesta de `GET /api/hub/context` del runtime. */
export interface HubContext {
  hub_id: string;
  user: unknown | null;
  /** Usuarios activos con PIN del hub (los que pueden hacer login local). */
  pin_users?: PinUser[];
  /**
   * Sector / tipo de negocio del hub (`hosteleria`|`retail`|`gestoria`|`rrhh`|`general`). Lo usa
   * el dashboard para derivar el preset "Recomendado" de widgets (ADR-0054). Opcional: el runtime
   * lo expondrá cuando se cablee el setting del hub; hasta entonces llega ausente y el preset
   * queda vacío (el board sigue funcionando). Acepta `sector` o `business_type` (alias).
   */
  sector?: string | null;
  business_type?: string | null;
  /**
   * Moneda ISO-4217 del hub (lectura barata en el boot; misma fuente que `GET /api/settings`).
   * La consume money.ts para formatear dinero. Ausente → degrada a EUR.
   */
  currency?: string | null;
  /**
   * Idioma DEFAULT del hub (código de locale). Se reconcilia con el override personal del usuario
   * en el boot (i18n → bootHubLanguage). Ausente → degrada a 'es'.
   */
  language?: string | null;
}

/**
 * Sector configurado del hub, resuelto en el boot (`GET /api/hub/context`). `null` mientras no se
 * sepa: el dashboard degrada (preset "Recomendado" vacío, el usuario activa widgets a mano).
 */
export const hubSector = ref<string | null>(null);

/** Sector actual del hub (o `null` si aún no se conoce). Lo usa la recolección de widgets. */
export function getHubSector(): string | null {
  return hubSector.value;
}

/**
 * Usuarios-PIN del hub resueltos en el boot (`GET /api/hub/context`). El LoginPage los usa para
 * mostrar el grid de PIN directamente cuando el hub ya tiene usuarios (p. ej. el demo: "Demo"),
 * sin depender de un flag en localStorage. `[]` hasta que el boot responde.
 */
export const pinUsers = ref<PinUser[]>([]);

let _client: ErploraClient | null = null;

/**
 * Cabeceras de auth para cada llamada al runtime: X-Hub-Id (inyectado por deployment, leído
 * del runtime en boot) + Bearer del usuario activo si hay sesión. El runtime Rust revalida.
 */
export function runtimeHeaders(): Record<string, string> {
  const h: Record<string, string> = {};
  if (config.hubId) h['X-Hub-Id'] = config.hubId;
  // Sesión local del runtime: autoridad de permisos en modo Session (gate de query/command).
  const session = getHubSession();
  if (session) h['X-Hub-Session'] = session;
  // JWT del usuario: fallback hub-scoped (marketplace/install) cuando el hub no está enrolado.
  const token = getAccessToken();
  if (token) h['Authorization'] = `Bearer ${token}`;
  return h;
}

/** Singleton del cliente SDK (HTTP RPC + WS eventos) apuntado al runtime local. */
export function getClient(): ErploraClient {
  if (!_client) {
    const transport = new HttpWsTransport({
      baseUrl: RUNTIME_URL,
      headers: runtimeHeaders,
    });
    // Inyecta la MONEDA DEL HUB (ADR-0059) al cliente que consumen los Web Components de módulo
    // (`globalThis.erplora.currency` / `formatMoney` / `formatAmount`). Misma fuente que el shell
    // (money.ts → hubCurrency, de /api/hub/context); así módulos y dashboard formatean igual.
    //
    // Bridge de hardware (web-PWA, §2.7): el transporte de periféricos que consumen los módulos
    // (`erplora.peripherals`, p.ej. el módulo printing) debe presentar el TOKEN DE EMPAREJAMIENTO
    // del Bridge en el WS (fail-closed). Se inyecta como getter para releer el token que el usuario
    // introduce en Ajustes → Bridge sin recrear el cliente. En Tauri el shell inyectará su propio
    // BridgeTransport (IpcBridgeTransport); aquí es siempre el WS a localhost:12321.
    const bridge = new BridgeClient(undefined, { token: getBridgeToken });
    _client = new ErploraClient(transport, { currency: hubCurrency }, bridge);
  }
  return _client;
}

/** Clave de inyección Vue para el cliente del runtime. */
export const clientInjectionKey: InjectionKey<ErploraClient> = Symbol('erplora.client');

/** Respuesta de `POST /api/modules/request-install` del runtime. */
export interface InstallRequestResult {
  ok: boolean;
  module_id: string;
  version: string;
  status: string;
}

/**
 * Pide al runtime que instale (vía marketplace del Cloud) un módulo. El runtime descarga el
 * zip firmado, verifica SHA256 y aplica migraciones; al terminar emite el evento WS
 * `module.installed`. ARQUITECTURA.md §2.2/§4.
 */
export async function requestInstall(moduleId: string, version: string): Promise<InstallRequestResult> {
  // Barra de progreso del shell mientras instala: descarga el zip + verifica SHA256 + migra puede
  // tardar (trabajo en background). beginRequest/endRequest alimenta el `inFlight` de la topbar.
  beginRequest();
  try {
    const res = await fetch(`${RUNTIME_URL}/api/modules/request-install`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
      body: JSON.stringify({ module_id: moduleId, version }),
    });
    if (!res.ok) throw new Error(`request-install ${moduleId} → ${res.status}`);
    return (await res.json()) as InstallRequestResult;
  } finally {
    endRequest();
  }
}

/** Un módulo instalado según el runtime (`GET /api/modules`). `status` = active|inactive. */
export interface InstalledModule {
  id: string;
  name: string;
  status: 'active' | 'inactive';
  version: string;
  /**
   * ADITIVO (ADR-0057): `true` si el módulo expone al menos una query/command `expose_api`.
   * Lo usa la matriz de scope de las API keys para listar solo módulos que conceden algo.
   * Ausente en runtimes antiguos → se trata como `false` (no expone API).
   */
  has_public_api?: boolean;
}

/** Lista los módulos instalados en el runtime (fuente de verdad local, no el catálogo Cloud). */
export async function listInstalledModules(): Promise<InstalledModule[]> {
  // `?locale=` (ADR-0055): el runtime devuelve el `name` de cada módulo ya traducido.
  const res = await fetch(`${RUNTIME_URL}/api/modules?locale=${encodeURIComponent(getLocale())}`, {
    headers: runtimeHeaders(),
  });
  if (!res.ok) throw new Error(`modules → ${res.status}`);
  const env = (await res.json()) as { ok: boolean; data?: InstalledModule[] };
  return env.ok && env.data ? env.data : [];
}

/** Activa / desactiva / desinstala un módulo en el runtime (hot-plug). Lanza si el runtime falla. */
async function moduleAction(id: string, action: 'activate' | 'deactivate' | 'uninstall'): Promise<void> {
  const res = await fetch(`${RUNTIME_URL}/api/modules/${encodeURIComponent(id)}/${action}`, {
    method: 'POST',
    headers: runtimeHeaders(),
  });
  const env = (await res.json().catch(() => ({}))) as { ok?: boolean; error?: { message?: string } };
  if (!res.ok || env.ok === false) {
    throw new Error(env.error?.message ?? `${action} ${id} → ${res.status}`);
  }
}

export const activateModule = (id: string): Promise<void> => moduleAction(id, 'activate');
export const deactivateModule = (id: string): Promise<void> => moduleAction(id, 'deactivate');
export const uninstallModule = (id: string): Promise<void> => moduleAction(id, 'uninstall');

/**
 * Una capability (permiso) que declara un módulo. El runtime es la autoridad (default-deny):
 * `requested` = el módulo la pide en su manifest; `granted` = el hub se la ha concedido.
 * Contrato: `GET /api/modules/{id}/capabilities`. ADR de permisos de módulo.
 */
export interface ModuleCapability {
  id: string;
  label: string;
  description: string;
  requested: boolean;
  granted: boolean;
}

/** Respuesta de `GET /api/modules/{id}/capabilities`. */
export interface ModuleCapabilities {
  module_id: string;
  capabilities: ModuleCapability[];
}

/**
 * Catálogo de respaldo de labels de capability (por si el runtime no las devuelve traducidas).
 * Espejo del catálogo del backend; solo se usa como fallback de presentación.
 */
export const CAPABILITY_LABELS: Record<string, string> = {
  network: 'Acceso a internet',
  certificate: 'Certificado del negocio (firma fiscal)',
  printer: 'Impresora',
  notify: 'Notificaciones',
};

/**
 * Lee las capabilities (permisos) que declara un módulo instalado y su estado de concesión.
 * Cualquier sesión puede leerlas; conceder/revocar es solo admin (`putModuleCapabilities`).
 */
export async function getModuleCapabilities(moduleId: string): Promise<ModuleCapabilities> {
  const res = await fetch(
    `${RUNTIME_URL}/api/modules/${encodeURIComponent(moduleId)}/capabilities`,
    { headers: runtimeHeaders() },
  );
  if (!res.ok) throw new Error(`capabilities ${moduleId} → ${res.status}`);
  const body = (await res.json()) as ModuleCapabilities;
  return { module_id: body.module_id ?? moduleId, capabilities: body.capabilities ?? [] };
}

/**
 * Concede / revoca capabilities de un módulo (default-deny). Solo admin: el runtime devuelve 401
 * si la sesión no es admin (el gate de UI es solo cosmético; aquí revalida Rust). `grants` mapea
 * `capabilityId → granted`.
 */
export async function putModuleCapabilities(
  moduleId: string,
  grants: Record<string, boolean>,
): Promise<void> {
  const res = await fetch(
    `${RUNTIME_URL}/api/modules/${encodeURIComponent(moduleId)}/capabilities`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
      body: JSON.stringify({ grants }),
    },
  );
  if (!res.ok) throw new Error(`put-capabilities ${moduleId} → ${res.status}`);
}

/**
 * Estado del certificado fiscal del negocio (`GET /api/business/certificate`). NO devuelve los
 * bytes del .p12; solo si hay uno y metadatos. El certificado dejó de ser del módulo verifactu:
 * ahora es un recurso del NEGOCIO/hub, se sube donde se configura el VAT y el nombre de la tienda.
 */
export interface BusinessCertificate {
  present: boolean;
  uploaded_at?: string | null;
  subject?: string | null;
}

/**
 * Lee el estado del certificado fiscal del negocio. Cualquier sesión puede leerlo. Degrada a
 * `{ present: false }` si el endpoint todavía no existe (404) o el runtime no responde, para que
 * la UI muestre "Sin certificado" en vez de romper.
 */
export async function getBusinessCertificate(): Promise<BusinessCertificate> {
  try {
    const res = await fetch(`${RUNTIME_URL}/api/business/certificate`, {
      headers: runtimeHeaders(),
    });
    if (!res.ok) return { present: false };
    return (await res.json()) as BusinessCertificate;
  } catch {
    return { present: false };
  }
}

/**
 * Sube / reemplaza el certificado fiscal del negocio (`PUT /api/business/certificate`). El .p12 va
 * en base64 + su contraseña. Solo admin: el runtime devuelve 401 si la sesión no lo es (el gate de
 * UI es solo cosmético; aquí revalida Rust). Lanza si el runtime rechaza.
 */
export async function putBusinessCertificate(pkcs12_b64: string, password: string): Promise<void> {
  const res = await fetch(`${RUNTIME_URL}/api/business/certificate`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
    body: JSON.stringify({ pkcs12_b64, password }),
  });
  if (!res.ok) throw new Error(`put-business-certificate → ${res.status}`);
}

/**
 * Elimina el certificado fiscal del negocio (`DELETE /api/business/certificate`). Solo admin (401
 * si no). Lanza si el runtime rechaza.
 */
export async function deleteBusinessCertificate(): Promise<void> {
  const res = await fetch(`${RUNTIME_URL}/api/business/certificate`, {
    method: 'DELETE',
    headers: runtimeHeaders(),
  });
  if (!res.ok) throw new Error(`delete-business-certificate → ${res.status}`);
}

/**
 * Siembra la cache de settings del hub con la lectura barata del context (`currency`/`language`).
 * El context NO trae `api_docs_enabled` (eso vive en /api/settings, que se carga aparte tras el
 * login); preservamos el valor previo o degradamos a OFF. Así money.ts ya tiene moneda en el boot
 * sin un GET /api/settings extra.
 */
function seedHubSettingsFromContext(ctx: HubContext): void {
  const currency =
    typeof ctx.currency === 'string' && ctx.currency.trim()
      ? ctx.currency.trim().toUpperCase()
      : (hubSettings.value?.currency ?? 'EUR');
  const language =
    typeof ctx.language === 'string' && ctx.language.trim()
      ? ctx.language.trim()
      : (hubSettings.value?.language ?? 'es');
  hubSettings.value = {
    currency,
    language,
    api_docs_enabled: hubSettings.value?.api_docs_enabled ?? false,
    // El contexto del hub solo trae moneda/idioma; la identidad de negocio la rellena el GET completo
    // de /api/settings (getHubSettings). Preservamos lo ya cacheado para no pisarlo con vacío.
    business_tax_id: hubSettings.value?.business_tax_id ?? '',
    business_legal_name: hubSettings.value?.business_legal_name ?? '',
    business_address: hubSettings.value?.business_address ?? '',
  };
  // Publica la moneda a `globalThis.__erploraCurrency` para los Web Components de módulo (ADR-0059):
  // el SDK la lee de ahí como fallback cuando el shell no inyecta el getter (mirror de cómo `locale`
  // lee `localStorage`), y queda fresca tras un cambio de settings.
  publishHubCurrency(currency);
}

/**
 * Obtiene el hub_id del runtime (`GET /api/hub/context`) y lo fija en `config.hubId`.
 * Se llama una vez en el boot (main.ts). Si el runtime no responde, deja el fallback
 * (VITE_HUB_ID) que ya trae `config`. No lanza: el boot del shell no debe romperse aquí.
 */
export async function bootHubContext(): Promise<HubContext | null> {
  try {
    const res = await fetch(`${RUNTIME_URL}/api/hub/context`, {
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) return null;
    const ctx = (await res.json()) as HubContext;
    if (ctx.hub_id) config.hubId = ctx.hub_id;
    if (Array.isArray(ctx.pin_users)) pinUsers.value = ctx.pin_users;
    // Sector del hub para el preset "Recomendado" del dashboard. Acepta `sector` o el alias
    // `business_type`; ausente → queda null (degradación elegante en la recolección de widgets).
    const sector = ctx.sector ?? ctx.business_type ?? null;
    hubSector.value = typeof sector === 'string' && sector.trim() ? sector.trim() : null;
    // Moneda + idioma del hub (lectura barata del context). Siembra la cache de settings para que
    // money.ts ya tenga la moneda y reconcilia el idioma DEFAULT del hub con el override del usuario
    // (i18n → bootHubLanguage), sin esperar a un GET /api/settings explícito.
    seedHubSettingsFromContext(ctx);
    bootHubLanguage(typeof ctx.language === 'string' ? ctx.language : null);
    return ctx;
  } catch {
    return null;
  }
}
