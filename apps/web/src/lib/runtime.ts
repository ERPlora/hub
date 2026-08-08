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
import { ErploraClient, HttpWsTransport } from '@erplora/module-sdk';
import { toast, type ToastColor } from './toast';
import { config } from './config';
import { getAccessToken } from './cloud';
import { makeBridgeTransport } from './bridge-transport';
import { getHubSession, user } from './session';
import { beginRequest, endRequest } from './shell';
import { getLocale, bootHubLanguage } from '../i18n';
import { hubSettings } from './hub-settings';
import { hubCurrency, publishHubCurrency } from './money';
import { STRICT_PIN_POLICY } from './pin-policy';
import { setRuntimeClientKind } from './device';

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
  /** Demo es la única excepción al registro obligatorio de máquina. */
  demo?: boolean;
  /** El runtime posee UUID Cloud + credencial de máquina (el secreto nunca llega al navegador). */
  machine_registered?: boolean;
  /** `true` en una instalación real que todavía debe completar el primer login/alta. */
  registration_required?: boolean;
  /** La clave pública RSA del SaaS está disponible para validar el JWT de usuario. */
  public_key_loaded?: boolean;
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
/** `true` cuando `/api/hub/context` respondió y `pinUsers` ya es una lista autoritativa. */
export const hubContextReady = ref(false);
/** Estado autoritativo del vínculo de la máquina, sin exponer su credencial. */
export const machineRegistered = ref(false);
export const machineRegistrationRequired = ref(false);
/** Permite distinguir un fallo de credenciales de un runtime que no pudo obtener la clave RSA. */
export const cloudPublicKeyLoaded = ref(false);

let _client: ErploraClient | null = null;

/**
 * Cabeceras de auth para cada llamada al runtime: X-Hub-Id (inyectado por deployment, leído
 * del runtime en boot) + Bearer del usuario activo si hay sesión. El runtime Rust revalida.
 */
export function runtimeHeaders(): Record<string, string> {
  const h: Record<string, string> = {};
  if (config.hubId) h['X-Hub-Id'] = config.hubId;
  if (user.value) {
    h['X-User-Id'] = user.value.id;
    h['X-User-Name'] = user.value.name;
    if (user.value.role) h['X-User-Role'] = user.value.role;
  }
  // Sesión local del runtime: autoridad de permisos en modo Session (gate de query/command).
  const session = getHubSession();
  if (session) h['X-Hub-Session'] = session;
  // JWT del usuario: fallback hub-scoped (marketplace/install) cuando el hub no está enrolado.
  const token = getAccessToken();
  if (token) h['Authorization'] = `Bearer ${token}`;
  return h;
}

/**
 * **The shell's credential for the event channel** (hub#504). The hub pushes nothing to a
 * connection that has not presented an API key of that hub with read access — including to us.
 *
 * So the app asks for one: `POST /api/events/ticket` is authenticated by the hub session and
 * answers with a **single-use** ticket bound to the read-only key the hub issues to itself. We
 * never hold the key: a long-lived `erpl_live_…` sitting in a browser tab would be liftable by any
 * XSS and would open the whole read API, not just this channel.
 *
 * Returns `null` — never throws — when there is no session yet or the runtime is unreachable: this
 * is called on every reconnect attempt, and a throw would kill the channel for good.
 */
export async function fetchStreamTicket(): Promise<string | null> {
  try {
    const res = await fetch(`${RUNTIME_URL}/api/events/ticket`, {
      method: 'POST',
      headers: runtimeHeaders(),
    });
    if (!res.ok) return null;
    const body = (await res.json()) as { data?: { ticket?: string } };
    return body?.data?.ticket ?? null;
  } catch {
    return null;
  }
}

/** Singleton del cliente SDK (HTTP RPC + WS eventos) apuntado al runtime local. */
export function getClient(): ErploraClient {
  if (!_client) {
    const transport = new HttpWsTransport({
      baseUrl: RUNTIME_URL,
      headers: runtimeHeaders,
      // hub#504: without this the socket connects and is told nothing — the live dashboard, the
      // auto-print on a sale, the kitchen docket and the install progress all go silent.
      streamCredential: fetchStreamTicket,
      onStreamRefused: (code, message) => {
        // A channel that goes quiet without a word is the failure nobody debugs. This one says so.
        console.error(`[erplora] the event channel was refused (${code}): ${message}`);
      },
    });
    // Inyecta la MONEDA DEL HUB (ADR-0059) al cliente que consumen los Web Components de módulo
    // (`globalThis.erplora.currency` / `formatMoney` / `formatAmount`). Misma fuente que el shell
    // (money.ts → hubCurrency, de /api/hub/context); así módulos y dashboard formatean igual.
    //
    // Bridge de hardware (§2.7, ADR-0159): el transporte de periféricos que consumen los módulos
    // (`erplora.peripherals`, p.ej. el módulo printing) se elige por entorno en
    // `makeBridgeTransport()` — WS a localhost:12321 en web/WebView (con el token de
    // emparejamiento fail-closed) o `invoke` in-process dentro del shell Tauri.
    const bridge = makeBridgeTransport();
    // `notifier`: el canal de AVISOS de los módulos. El SDK ya exponía `erplora.notify()`, pero
    // nadie le pasaba a dónde llevarlo, así que era un **no-op silencioso** — y cada módulo acababa
    // colando sus mensajes de éxito por su hueco de ERROR (rojo). El Hub ya tiene toast global:
    // se conecta aquí, una vez, para todos.
    _client = new ErploraClient(
      transport,
      {
        permissions: () => {
          const role = user.value?.role?.toLowerCase();
          if (role === 'owner' || role === 'admin') return new Set(['*']);
          return new Set(user.value?.permissions ?? []);
        },
        currency: hubCurrency,
        notifier: (n) => {
          const color: ToastColor =
            n.type === 'success' ? 'success' : n.type === 'error' ? 'danger' : n.type === 'warning' ? 'warning' : 'primary';
          void toast(n.message, color);
        },
      },
      bridge,
    );
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

/** Un módulo del plan que hay que COMPRAR antes de poder instalar (ADR-0060). */
export interface InstallPurchaseOption {
  moduleId: string;
  moduleType: string;
  price: string;
  currency: string;
  purchaseUrl: string;
}

/**
 * El plan de instalación (ADR-0060) exige contratar dependencias: **no se ha instalado nada**.
 * No es una avería, es una decisión del usuario — por eso es un error propio y lleva a dónde ir.
 * Nunca hay auto-cobro: el Hub solo enseña el precio y el enlace.
 */
export class InstallBlockedError extends Error {
  readonly code = 'install_blocked';
  readonly blockedOn: string[];
  readonly purchase: InstallPurchaseOption[];

  constructor(message: string, blockedOn: string[], purchase: InstallPurchaseOption[]) {
    super(message);
    this.name = 'InstallBlockedError';
    this.blockedOn = blockedOn;
    this.purchase = purchase;
  }
}

/** Fallo de instalación con el CÓDIGO estable del runtime (hub#139) para que la UI lo traduzca. */
export class InstallFailedError extends Error {
  readonly code: string;

  constructor(message: string, code: string) {
    super(message);
    this.name = 'InstallFailedError';
    this.code = code;
  }
}

/**
 * Pide al runtime que instale (vía marketplace del Cloud) un módulo. El runtime pide el PLAN al
 * Cloud (ADR-0060), lo ejecuta en orden —instalando las dependencias que falten—, verifica SHA256
 * y aplica migraciones; al terminar emite el evento WS `module.installed`. ARQUITECTURA.md §2.2/§4.
 *
 * Si el plan trae dependencias de pago sin contratar, el runtime responde **409** y aquí sale un
 * [`InstallBlockedError`] con qué falta y su puntero de compra (nunca se cobra solo).
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
    if (!res.ok) {
      // El cuerpo del runtime lleva `error` + `code` estables; un 409 además trae la compra.
      // Si no se puede leer, se cae al mensaje de siempre (nunca se traga el fallo).
      let body: Record<string, unknown> | null = null;
      try {
        body = (await res.json()) as Record<string, unknown>;
      } catch {
        body = null;
      }
      const message = (body?.error as string) || `request-install ${moduleId} → ${res.status}`;
      const code = (body?.code as string) || 'install_failed';
      if (code === 'install_blocked') {
        const purchase = Array.isArray(body?.purchase)
          ? (body!.purchase as Record<string, string>[]).map((p) => ({
              moduleId: p.module_id,
              moduleType: p.module_type,
              price: p.price,
              currency: p.currency,
              purchaseUrl: p.purchase_url,
            }))
          : [];
        throw new InstallBlockedError(message, (body?.blocked_on as string[]) ?? [], purchase);
      }
      throw new InstallFailedError(message, code);
    }
    return (await res.json()) as InstallRequestResult;
  } finally {
    endRequest();
  }
}

/** Un módulo instalado según el runtime (`GET /api/modules`).
 *  `inactive` = apagado A MANO (se respeta); `inactive_auto` = arrastrado por la cascada de una
 *  dependencia (ADR-0128) — vuelve solo cuando sus `depends_on` estén activas. */
export interface InstalledModule {
  id: string;
  name: string;
  status: 'active' | 'inactive' | 'inactive_auto';
  version: string;
  /** Dependencias declaradas: el toggle las usa para AVISAR de la cascada antes de confirmar. */
  depends_on?: string[];
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

/**
 * Fallo de una acción de módulo que CONSERVA el código estable del runtime (hub#139).
 *
 * `code` presente = el runtime dio un motivo de negocio que el usuario puede accionar — p. ej.
 * `verifactu.unsent_records` (hub#314: quedan N registros sin remitir a la AEAT, así que el módulo
 * no se desactiva ni se desinstala). Sin `code` es un fallo de transporte/servidor y no hay motivo
 * que enseñar: la UI se queda con su mensaje genérico.
 */
export class ModuleActionError extends Error {
  readonly code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = 'ModuleActionError';
    this.code = code;
  }
}

/** Activa / desactiva / desinstala un módulo en el runtime (hot-plug). Lanza si el runtime falla. */
async function moduleAction(id: string, action: 'activate' | 'deactivate' | 'uninstall'): Promise<void> {
  const res = await fetch(`${RUNTIME_URL}/api/modules/${encodeURIComponent(id)}/${action}`, {
    method: 'POST',
    headers: runtimeHeaders(),
  });
  const env = (await res.json().catch(() => ({}))) as {
    ok?: boolean;
    error?: { code?: string; message?: string };
  };
  if (!res.ok || env.ok === false) {
    throw new ModuleActionError(
      env.error?.message ?? `${action} ${id} → ${res.status}`,
      env.error?.code,
    );
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
 * Comparte la identidad fiscal del negocio con el SaaS (`POST /api/business/fiscal-identity`) —
 * la casilla «usar estos datos también para mi factura de ERPlora» (ADR-0201 decisión 5).
 *
 * El body lo construye el RUNTIME leyendo `hub_settings`: el dato ya está escrito, aquí solo se
 * autoriza que suba una copia. Y la llamada al SaaS la hace el runtime porque el token de máquina
 * del hub nunca cruza a este navegador (ADR-0003). Solo admin (Rust revalida). Lanza si falla.
 */
export async function publishFiscalIdentity(): Promise<void> {
  const res = await fetch(`${RUNTIME_URL}/api/business/fiscal-identity`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
  });
  if (!res.ok) throw new Error(`publish-fiscal-identity → ${res.status}`);
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

// ── Export/Import del hub (blueprints, ADR-0113 — architecture/hub/export-import.md) ──────────
// Motor CORE de backup/restore: exportar empaqueta configuración (+datos opcionales) en un
// `*.blueprint.zip`; importar lo restaura en orden «migrate» (instalar módulos → SQL → media →
// fiscal) con informe best-effort por sección. Endpoints solo owner/admin (el runtime revalida).

/** Selección por módulo del export: registrar el módulo y, opcionalmente, volcar sus datos. */
export interface ExportModuleSelection {
  module_id: string;
  with_data: boolean;
  /**
   * Subselección de TABLAS del módulo (hub#534). `null` = todas las suyas, que es lo que
   * significaba `with_data` antes de existir el campo. **Acota, nunca amplía**: lo que la regla del
   * `purpose` deja fuera sigue fuera aunque se marque aquí.
   */
  tables: string[] | null;
}

/** Una tabla de un módulo y cuántas filas volcaría el export (`GET /api/hub/export/tables`). */
export interface ExportTableCount {
  table: string;
  rows: number;
}

export interface ExportModuleTables {
  module_id: string;
  tables: ExportTableCount[];
}

/**
 * Para qué es el bundle (ADR-0195). `backup` = copia/migración privada (lo lleva todo);
 * `template` = plantilla publicable, y entonces el motor EXCLUYE identidades y fiscal del zip
 * marque lo que marque el formulario.
 */
export type BundlePurpose = 'backup' | 'template';

/** Selección de secciones del export (`POST /api/hub/export`). */
export interface ExportSelection {
  users: boolean;
  settings: boolean;
  /** Subselección ítem a ítem de settings; `null` = todos (la UI aún no la desglosa). */
  settings_items: string[] | null;
  /** OFF por defecto: incluye la config VeriFactu + el certificado .p12 (viaja tal cual). */
  fiscal: boolean;
  media: boolean;
  modules: ExportModuleSelection[];
  /** ADR-0195. Ausente en el server ⇒ `backup`; el front lo manda SIEMPRE explícito. */
  purpose: BundlePurpose;
}

/** Un módulo listado en el manifest de un blueprint. */
export interface BlueprintModule {
  id: string;
  version: string;
  /** `true` si el bundle lleva `data/<id>.sql` además de registrar el módulo para instalar. */
  with_data: boolean;
}

/** `manifest.json` del bundle — la fuente de verdad (a prueba de renombres del zip). */
export interface BlueprintManifest {
  schema_version: number;
  name: string;
  locale: string;
  hub: { name?: string | null; country?: string | null; currency?: string | null };
  created_at: string;
  modules: BlueprintModule[];
  /** Secciones presentes en el bundle: `hub_users`, `hub_settings`, `fiscal`, `media`, … */
  sections: string[];
  /** SHA256 por fichero (integridad dura: mismatch = rechazo entero sin efectos). */
  sha256: unknown;
}

/** Respuesta de `POST /api/hub/import/inspect` (el zip subido queda staged bajo `upload_id`). */
export interface BlueprintInspection {
  ok: boolean;
  upload_id: string;
  manifest: BlueprintManifest;
}

/** Selección de secciones a aplicar en el import (`POST /api/hub/import`). */
export interface ImportSelection {
  users: boolean;
  settings: boolean;
  fiscal: boolean;
  media: boolean;
  /** Ids de módulo del manifest a instalar/aplicar. */
  modules: string[];
}

/**
 * Estado de una sección del informe. Serde del enum Rust `SectionStatus`: `Applied`/`Skipped`
 * llegan como string; `Failed(motivo)` e `Ignored(motivo)` como objeto `{"Failed": "motivo"}` /
 * `{"Ignored": "motivo"}`. Tolerar ambas formas.
 */
export type SectionStatus =
  | 'Applied'
  | 'Skipped'
  | { Failed: string }
  | { Ignored: string }
  | { PartiallyApplied: string };

/** Una entrada del informe: sección (`hub_users`, `media`, `modules/<id>`, …) + estado. */
export interface SectionResult {
  section: string;
  status: SectionStatus;
  /**
   * Filas que el motor se negó a aplicar: la sección entera cuando la descartó (hub#331) o solo
   * las no portables cuando la aplicó en parte (hub#405); 0 si no descartó nada. Ausente en
   * informes de un runtime anterior al campo → se lee como 0.
   */
  discarded_rows?: number;
}

/**
 * Motivos de descarte que el runtime emite como **código estable** (hub#331): la frase la pone el
 * shell traducida (inglés fuente + su `es`), no el runtime. Los descartes anteriores viajan como
 * prosa y se pintan tal cual, así que hay que distinguir unos de otros — traducir es SUSTITUIR el
 * texto, y sustituir lo que no es un código borraría el motivo.
 */
export const SECTION_DISCARD_CODES = [
  'identity_not_portable',
  'settings_not_portable',
  'roles_not_activatable',
] as const;

/** Código de descarte (ver [`SECTION_DISCARD_CODES`]). */
export type SectionDiscardCode = (typeof SECTION_DISCARD_CODES)[number];

/** El código estable de un motivo de descarte, o `null` si es prosa heredada (o no hay motivo). */
export function sectionDiscardCode(reason: string | undefined): SectionDiscardCode | null {
  const code = reason?.trim() ?? '';
  return (SECTION_DISCARD_CODES as readonly string[]).includes(code)
    ? (code as SectionDiscardCode)
    : null;
}

/** Resultado de la copia de media, que hace el SERVER (no el motor del runtime). */
export interface MediaReport {
  selected: boolean;
  copied: number;
  failed: number;
}

/** Informe final del import (best-effort: una sección rota NO aborta el resto). */
export interface ImportReport {
  sections: SectionResult[];
  /**
   * Media/fiscal las materializa la capa server (gestor media + endpoint del certificado), no
   * el motor del runtime — que las reporta como `Skipped` en `sections`. Su resultado REAL viene
   * en estas claves aparte; la UI las usa para pintar el estado verdadero (p. ej. media copiada).
   */
  media?: MediaReport;
  fiscal?: { certificate: string; note?: string };
  /**
   * Qué hizo el import con **cada módulo del manifest**. La pantalla promete «instala los módulos
   * que falten», así que este es el resultado de la mitad del trabajo — no un detalle interno.
   *
   * Estuvo tipado como `unknown[]` y el panel no lo pintaba: cuando los 13 módulos de un blueprint
   * fallaban, el informe salía «bien» y el panel quedaba vacío sin ninguna señal (2026-08-03).
   */
  installed_modules?: ModuleInstallResult[];
}

/**
 * Where to subscribe to a module that BLOCKS an install, as the engine serializes it inside
 * `installed_modules[]` (wire shape, snake_case — `module_install_entry` in `export_import.rs`).
 * The Hub never charges by itself: it only shows the price and where to go.
 */
export interface ModuleInstallPurchase {
  module_id: string;
  module_type?: string;
  price?: string;
  currency?: string;
  purchase_url?: string;
}

/** Resultado del import para un módulo del manifest (best-effort: uno roto no aborta el resto). */
export interface ModuleInstallResult {
  id: string;
  version: string;
  /**
   * `blocked` (ADR-0060) is a state of ITS OWN, not a `failed`: the module was not installed
   * because the plan requires subscribing to a dependency — a purchase decision, not a breakage.
   */
  status: 'installed' | 'already_installed' | 'blocked' | 'failed';
  /** Stable engine code (hub#139): `install_blocked` on `blocked`, the failure code on `failed`. */
  code?: string;
  /** Modules that have to be subscribed to first — only on `blocked`. */
  blocked_on?: string[];
  /** Where to subscribe to each blocking module — only on `blocked`. */
  purchase?: ModuleInstallPurchase[];
  /** Motivo real del motor — solo en `failed`. */
  error?: string;
}

/** Estado normalizado de UN módulo del informe de import, listo para pintar. */
export interface ModuleInstallStatusInfo {
  kind: 'installed' | 'already_installed' | 'blocked' | 'failed';
  /** Qué hay que contratar antes de reintentar — solo en `blocked`. */
  blockedOn: string[];
  /** Precio y enlace de cada módulo que bloquea — solo en `blocked`. */
  purchase: ModuleInstallPurchase[];
  /** Motivo del motor — solo en `failed`. */
  error?: string;
}

/**
 * Normaliza una entrada de `installed_modules[]` a un shape estable para la UI.
 *
 * El shell solo conocía tres estados, así que el `"status": "blocked"` del motor caía al fallback
 * de fallo y un módulo que solo faltaba CONTRATAR se pintaba como un ✗ rojo y mudo (hub#409).
 * Una forma desconocida sí cae a `failed` —misma regla de honestidad que `sectionStatusInfo`—:
 * jamás se inventa un éxito.
 */
export function moduleInstallStatusInfo(m: ModuleInstallResult): ModuleInstallStatusInfo {
  if (m.status === 'installed' || m.status === 'already_installed') {
    return { kind: m.status, blockedOn: [], purchase: [] };
  }
  if (m.status === 'blocked') {
    return { kind: 'blocked', blockedOn: m.blocked_on ?? [], purchase: m.purchase ?? [] };
  }
  return { kind: 'failed', blockedOn: [], purchase: [], error: m.error };
}

/** Estado normalizado de una sección del informe, listo para pintar. */
export interface SectionStatusInfo {
  kind: 'applied' | 'skipped' | 'ignored' | 'partial' | 'failed';
  /** Motivo — de un `failed`, o de por qué se descartó (del todo o en parte) una sección. */
  reason?: string;
}

/**
 * Normaliza el `status` serde (string `"Applied"`/`"Skipped"` u objeto `{"Failed": "motivo"}` /
 * `{"Ignored": "motivo"}` — y, defensivamente, las variantes objeto `{"Applied": …}`) a un shape
 * estable para la UI.
 */
export function sectionStatusInfo(status: SectionStatus | Record<string, unknown> | string): SectionStatusInfo {
  if (typeof status === 'string') {
    const s = status.toLowerCase();
    if (s === 'applied') return { kind: 'applied' };
    if (s === 'skipped') return { kind: 'skipped' };
    return { kind: 'failed', reason: status === 'Failed' ? undefined : status };
  }
  if (status && typeof status === 'object') {
    const obj = status as Record<string, unknown>;
    if ('Failed' in obj) return { kind: 'failed', reason: String(obj.Failed ?? '') };
    // ADR-0195: el motor DESCARTÓ la sección a propósito (identidades de un bundle `template`).
    // Ni un fallo —no se intentó nada— ni un «saltado» mudo, que sería indistinguible de «no la
    // marqué». Lleva siempre su motivo, y ese motivo es lo que la pantalla enseña.
    if ('Ignored' in obj) return { kind: 'ignored', reason: String(obj.Ignored ?? '') };
    // ADR-0195 §4 / hub#405: entró parte de la sección. `hub_settings` mezcla la configuración que
    // SÍ viaja con la identidad fiscal que no, así que de un bundle ajeno se aplica a medias —
    // decirlo «Aplicado» ocultaría el descarte, y «Descartado» negaría lo que sí entró.
    if ('PartiallyApplied' in obj) {
      return { kind: 'partial', reason: String(obj.PartiallyApplied ?? '') };
    }
    if ('Applied' in obj) return { kind: 'applied' };
    if ('Skipped' in obj) return { kind: 'skipped' };
  }
  // Forma desconocida → trátala como fallo SIN inventar un éxito (informe honesto).
  return { kind: 'failed', reason: JSON.stringify(status) };
}

/**
 * Extrae el mensaje de error HONESTO de una respuesta fallida del runtime: intenta el envelope
 * JSON (`{error:{message}}` / `{message}` / `{error:"…"}`) y cae al texto crudo; nunca inventa
 * un mensaje genérico si el server dijo algo.
 */
async function readErrorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const text = await res.text();
    if (!text.trim()) return fallback;
    try {
      const j = JSON.parse(text) as { error?: { message?: string } | string; message?: string };
      const msg = typeof j.error === 'string' ? j.error : (j.error?.message ?? j.message);
      return msg?.trim() ? msg : text;
    } catch {
      return text;
    }
  } catch {
    return fallback;
  }
}

/** Filename de un header `Content-Disposition` (`filename="…"` o `filename*=UTF-8''…`). */
function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null;
  const star = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(header);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ''));
    } catch {
      /* cae al filename= simple */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain?.[1]?.trim() ?? null;
}

/**
 * Exporta el hub (`POST /api/hub/export`) y devuelve el zip como blob + el nombre de fichero
 * (del `Content-Disposition` o el default `<nombre>_<idioma>.blueprint.zip`). Solo owner/admin
 * (el runtime revalida). Lanza con el mensaje del server si rechaza.
 */
/**
 * Qué tablas tiene cada módulo instalado y **cuántas filas** volcaría el export (hub#534).
 *
 * El recuento es lo que convierte la lista de casillas en una decisión: «Citas: 28» es lo que hace
 * que quien monta una plantilla las desmarque. Sin el número, es una fila de nombres.
 *
 * **Degrada en silencio**: si el runtime no lo sirve (versión anterior, o sin sesión de admin) se
 * devuelve vacío y el formulario sigue funcionando exactamente como antes —todas las tablas—, en
 * vez de romper la pantalla de export por una comodidad.
 */
export async function fetchExportTables(): Promise<ExportModuleTables[]> {
  try {
    const res = await fetch(`${RUNTIME_URL}/api/hub/export/tables`, { headers: runtimeHeaders() });
    if (!res.ok) return [];
    const body = (await res.json()) as { modules?: ExportModuleTables[] };
    return Array.isArray(body.modules) ? body.modules : [];
  } catch {
    return [];
  }
}

export async function exportHub(
  name: string,
  locale: string,
  selection: ExportSelection,
): Promise<{ blob: Blob; filename: string }> {
  beginRequest(); // volcar datos + empaquetar puede tardar → barra de progreso del shell
  try {
    const res = await fetch(`${RUNTIME_URL}/api/hub/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
      body: JSON.stringify({ name, locale, selection }),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, `export → ${res.status}`));
    const blob = await res.blob();
    const filename =
      filenameFromDisposition(res.headers.get('Content-Disposition')) ??
      `${name}_${locale}.blueprint.zip`;
    return { blob, filename };
  } finally {
    endRequest();
  }
}

/**
 * Sube un `*.blueprint.zip` para inspección (`POST /api/hub/import/inspect`, body = el zip como
 * octet-stream). El server valida manifest + SHA256 (integridad dura: rechazo sin efectos) y
 * devuelve el manifest + un `upload_id` staged para el import posterior.
 */
/** Ficha de un blueprint del catálogo del SaaS (ADR-0121). */
export interface CatalogBlueprint {
  slug: string;
  name: string;
  description: string;
  locale: string;
  country: string;
  latest_version: string;
  latest_sha256: string;
  size_bytes: number;
  downloads: number;
}

/**
 * Catálogo de blueprints publicados en el SaaS (`GET /api/blueprints/catalog`, ADR-0121).
 *
 * Es la **«fuente nube»** del import. El runtime hace de proxy: firma la llamada al SaaS con su
 * `X-Hub-Token`, que **nunca** llega al navegador.
 */
export async function fetchBlueprintCatalog(): Promise<CatalogBlueprint[]> {
  beginRequest();
  try {
    const res = await fetch(`${RUNTIME_URL}/api/blueprints/catalog`, { headers: runtimeHeaders() });
    if (!res.ok) throw new Error(await readErrorMessage(res, `blueprints/catalog → ${res.status}`));
    const body = (await res.json()) as { blueprints?: CatalogBlueprint[] };
    return body.blueprints ?? [];
  } finally {
    endRequest();
  }
}

/**
 * Descarga un blueprint del catálogo (`GET /api/blueprints/:slug/download`, ADR-0121).
 *
 * El **runtime verifica el SHA256** contra el que anunció el SaaS antes de entregarnos un solo
 * byte (integridad no-saltable, ADR-0015): si no casa, esto lanza. El Blob resultante se pasa a
 * `inspectBlueprint()` **igual que un fichero local** — el flujo de import es el mismo.
 */
export async function downloadBlueprint(slug: string): Promise<Blob> {
  beginRequest();
  try {
    const res = await fetch(`${RUNTIME_URL}/api/blueprints/${encodeURIComponent(slug)}/download`, {
      headers: runtimeHeaders(),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, `blueprints/download → ${res.status}`));
    return await res.blob();
  } finally {
    endRequest();
  }
}

export async function inspectBlueprint(file: Blob): Promise<BlueprintInspection> {
  beginRequest();
  try {
    const res = await fetch(`${RUNTIME_URL}/api/hub/import/inspect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream', ...runtimeHeaders() },
      body: file,
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, `import/inspect → ${res.status}`));
    const body = (await res.json()) as BlueprintInspection;
    if (!body.ok || !body.upload_id) {
      throw new Error(`import/inspect → respuesta inválida del runtime`);
    }
    return body;
  } finally {
    endRequest();
  }
}

/**
 * Aplica un blueprint ya inspeccionado (`POST /api/hub/import`): instala los módulos que falten,
 * aplica los `data/*.sql` seleccionados, copia media y restaura fiscal — best-effort, con informe
 * por sección. Lanza con el mensaje del server solo si el import entero fue rechazado.
 */
export async function importBlueprint(
  uploadId: string,
  selection: ImportSelection,
): Promise<ImportReport> {
  beginRequest(); // instalar módulos + aplicar SQL puede tardar → barra de progreso del shell
  try {
    const res = await fetch(`${RUNTIME_URL}/api/hub/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
      body: JSON.stringify({ upload_id: uploadId, selection }),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, `import → ${res.status}`));
    const body = (await res.json()) as { ok: boolean; report?: ImportReport };
    return body.report ?? { sections: [] };
  } finally {
    endRequest();
  }
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
    country_code: hubSettings.value?.country_code ?? 'ES',
    region_code: hubSettings.value?.region_code ?? null,
    // El contexto del hub solo trae moneda/idioma; la identidad de negocio la rellena el GET completo
    // de /api/settings (getHubSettings). Preservamos lo ya cacheado para no pisarlo con vacío.
    business_tax_id: hubSettings.value?.business_tax_id ?? '',
    business_legal_name: hubSettings.value?.business_legal_name ?? '',
    business_address: hubSettings.value?.business_address ?? '',
    // La paleta global tampoco viaja en el context: la trae el GET completo (que además
    // la refleja en el shell vía theme.ts). Aquí solo se preserva la cache.
    theme_palette: hubSettings.value?.theme_palette ?? 'erplora',
    // El dial «pedir PIN» (hub#359) tampoco viaja en el context. Se preserva lo cacheado y, sin
    // cache, el valor que SIGUE preguntando: sembrar la cache con `never` porque el context calló
    // sería quitar el pinpad por una lectura que no habla de él. La autoridad son el GET completo
    // y `GET /api/device/mode` (que es el que lee la pantalla de login, sin sesión).
    pin_policy: hubSettings.value?.pin_policy ?? STRICT_PIN_POLICY,
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
    hubContextReady.value = true;
    machineRegistered.value = Boolean(ctx.machine_registered);
    machineRegistrationRequired.value = Boolean(ctx.registration_required);
    cloudPublicKeyLoaded.value = Boolean(ctx.public_key_loaded);
    if (ctx.hub_id) config.hubId = ctx.hub_id;
    // The runtime is the authority on demo mode and on the machine link. What it can say about the
    // client is what KIND it is — a provisioned Cloud machine — and nothing more: **which** device
    // is asking is not something the hub can see, and its own id names the hub (hub#454). The
    // device identity is resolved in `device.ts`: the shell's installation id, or the one this
    // browser minted for itself.
    if (ctx.demo) config.demo = true;
    setRuntimeClientKind(
      ctx.machine_registered ? { clientType: 'hub-cloud', platform: 'cloud' } : null,
    );
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

// ── Reset del hub (volver a cero, ADR-0170 — architecture/hub/export-import.md §8) ────────────
// El espejo DESTRUCTIVO del export. Dos pasos deliberados: `plan` (dry-run) enumera qué hay y qué
// está bloqueado; `reset` borra. La UI nunca inventa cifras: las saca del plan. Solo owner/admin
// (el runtime revalida; la UI gatea únicamente para mostrar/ocultar).

/** Una sección en el dry-run: cuántas filas se llevaría y, si aplica, por qué NO se puede. */
export interface ResetSectionPlan {
  /** `hub_settings` · `hub_users` · `roles` · `media` · `fiscal` · `modules/<id>`. */
  section: string;
  /** Filas reales que se borrarían. Es la cifra que se enseña al usuario. */
  rows: number;
  /** Motivo legible del bloqueo (p. ej. facturas remitidas a la AEAT). `null` = se puede borrar. */
  blocked_by: string | null;
}

/** Dry-run completo (`POST /api/hub/reset/plan`). */
export interface ResetPlan {
  sections: ResetSectionPlan[];
}

/** Selección de secciones a borrar (`POST /api/hub/reset`). Todo `false` = no se borra nada. */
export interface ResetSelection {
  settings: boolean;
  users: boolean;
  media: boolean;
  fiscal: boolean;
  /**
   * Juego de roles del hub (`hub_role_activation`, hub#417): cuáles de los roles que DECLARAN los
   * módulos instalados están vivos aquí. Es el espejo de lo que el export se lleva (ADR-0242) y la
   * única forma que tiene el dueño de retirar un rol que encendió una plantilla sin desinstalar el
   * módulo que lo declara.
   */
  roles: boolean;
  /** Ids de módulo cuyos datos de usuario se borran. */
  modules: string[];
}

/** Una entrada del informe del reset. */
export interface ResetSectionOutcome {
  section: string;
  rows_deleted: number;
}

/** Informe final del reset (`POST /api/hub/reset`). */
export interface ResetReport {
  sections: ResetSectionOutcome[];
}

/**
 * Dry-run del reset (`POST /api/hub/reset/plan`): NO borra nada. Se llama al abrir el panel para
 * pintar las secciones con sus cifras y sus bloqueos.
 */
export async function fetchResetPlan(): Promise<ResetPlan> {
  const res = await fetch(`${RUNTIME_URL}/api/hub/reset/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
    body: '{}',
  });
  if (!res.ok) throw new Error(await readErrorMessage(res, `reset/plan → ${res.status}`));
  const body = (await res.json()) as { ok: boolean; plan?: ResetPlan };
  return body.plan ?? { sections: [] };
}

/**
 * Ejecuta el reset (`POST /api/hub/reset`). Irreversible: el llamador ya ha confirmado.
 * Un 409 significa que el runtime lo bloqueó (límite fiscal) — su mensaje explica el motivo.
 */
export async function resetHub(selection: ResetSelection): Promise<ResetReport> {
  beginRequest(); // barrer varias tablas puede tardar → barra de progreso del shell
  try {
    const res = await fetch(`${RUNTIME_URL}/api/hub/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
      body: JSON.stringify({ selection }),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, `reset → ${res.status}`));
    const body = (await res.json()) as { ok: boolean; report?: ResetReport };
    return body.report ?? { sections: [] };
  } finally {
    endRequest();
  }
}

/** Una importación registrada: lo que trajo un blueprint, para poder deshacerlo (ADR-0170). */
export interface ImportBatch {
  id: string;
  /** Nombre del blueprint importado (`restaurante_es`), como lo reconoce el usuario. */
  name: string;
  /** Filas que ESE lote insertó realmente. */
  rows: number;
  created_at: string;
}

/** Importaciones del hub, de la más reciente a la más antigua (`GET /api/hub/import/batches`). */
export async function fetchImportBatches(): Promise<ImportBatch[]> {
  const res = await fetch(`${RUNTIME_URL}/api/hub/import/batches`, { headers: runtimeHeaders() });
  if (!res.ok) throw new Error(await readErrorMessage(res, `import/batches → ${res.status}`));
  const body = (await res.json()) as { ok: boolean; batches?: ImportBatch[] };
  return body.batches ?? [];
}

/**
 * Deshace una importación (`POST /api/hub/import/undo`): borra solo lo que trajo ese blueprint,
 * conservando lo que el usuario creó después. Un lote ya deshecho es un no-op.
 */
export async function undoImport(batchId: string): Promise<ResetReport> {
  beginRequest();
  try {
    const res = await fetch(`${RUNTIME_URL}/api/hub/import/undo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
      body: JSON.stringify({ batch_id: batchId }),
    });
    if (!res.ok) throw new Error(await readErrorMessage(res, `import/undo → ${res.status}`));
    const body = (await res.json()) as { ok: boolean; report?: ResetReport };
    return body.report ?? { sections: [] };
  } finally {
    endRequest();
  }
}
