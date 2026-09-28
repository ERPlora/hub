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
import { config, markCloudApiUrlPending, resolveCloudApiUrl } from './config';
import { getAccessToken } from './cloud';
import { makeBridgeTransport } from './bridge-transport';
import { getHubSession, logout, user } from './session';
import { beginRequest, endRequest } from './shell';
import { getLocale, bootHubLanguage } from '../i18n';
import { hubSettings, hubTimezone, publishHubTimezone } from './hub-settings';
import { normalizePinLength } from './pin-length';
import { hubCurrency, publishHubCurrency } from './money';
import { STRICT_PIN_POLICY } from './pin-policy';
import { askForApproval } from './elevation';
import { setRuntimeClientKind } from './device';
import type { ModuleUpdateInfo, ModuleVersions } from './module-updates';
import { publicationStatusOf, type PublicationStatus } from './apps-catalog';
import { sessionEndReason } from './session-end-reason';
import { CLIENT_INSTANCE } from './client-instance';

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
   * Sector / tipo de negocio del hub (`hosteleria`|`retail`|`gestoria`|`rrhh`|`belleza`|`general`). Lo usa
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
  /**
   * Zona horaria IANA del NEGOCIO, ya RESUELTA (hub#731, hub#1022): la declarada o la deducida
   * del país — nunca `null` cuando el runtime la envía. La publica `publishHubTimezone` para que
   * módulos y shell lean el mismo reloj que el runtime da a los handlers (`context.timezone`).
   * Ausente → degrada a UTC.
   */
  timezone?: string | null;
  /**
   * Which Cloud this hub belongs to (`HUB_CLOUD_API_URL`, the same value its CSP `connect-src`
   * allows — hub#1164). Non-empty → becomes `config.cloudApiUrl`; empty/absent → build-time
   * fallback (`VITE_CLOUD_API_URL`, dev/local only).
   */
  cloud_base_url?: string | null;
  /**
   * How many DIGITS this hub's PIN has (hub#974): 4 or 6. It travels in the context because the
   * screen that needs it —the login pinpad— is the only one WITHOUT a session, and
   * `GET /api/settings` demands one: without this key the shell fell back to its own default and
   * painted four circles on a six-digit hub, firing a truncated login on the fourth digit
   * (hub#1765). Missing → whatever was already known is kept.
   */
  pin_length?: unknown;
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
  // hub#1980: which shell tab is calling. The hub repeats it on the live frames this call produces,
  // so only the till that charged a sale prints its ticket. It names, it grants nothing.
  h['X-Client-Instance'] = CLIENT_INSTANCE;
  return h;
}

// ── Central reaction to a DEAD runtime session (hub#846) ──────────────────────────────────────
// Before this existed, every fetch in this file decided on its own what `!res.ok` meant, and most
// flattened a 401 to "no data": the user kept their name, email and navigation while the screens
// emptied one by one (hub#902's 401-every-10s loop is this file's event-ticket retry; hub#894's
// "you have no apps" is the same flattening). The shell has to REACT — close the local session
// once and lead to the login — not merely show the failure.

/**
 * The runtime said this shell's session is no longer valid (expired, or displaced by a sign-in on
 * another device). By the time a caller sees this error the local session has already been closed
 * and the redirect hook fired — so no screen may present it as a retryable failure or as an empty
 * list: retrying cannot help, and "no data" would be a lie.
 */
export class RuntimeSessionExpiredError extends Error {
  readonly code = 'session_expired';

  constructor() {
    super('the runtime session is no longer valid');
    this.name = 'RuntimeSessionExpiredError';
  }
}

/**
 * End-of-session hook, mirror of `cloud.setOnSessionExpired` (the Cloud plane's twin in
 * `lib/cloud.ts`). `main.ts` registers the shell's reaction — explain (toast, i18n `auth.*`) and
 * redirect to the login via the router. It CANNOT live here: `router/index.ts` imports this
 * module, so importing the router back would be a cycle. Closing the session itself is not
 * delegated to the hook — `handleRuntime401` calls `logout()` directly, so the invalidation
 * happens even before `main.ts` has registered anything.
 *
 * It receives the REASON the session ended when the runtime knows one (hub#1801, today only
 * `session_evicted_device_limit`) and `null` when there is nothing to explain. Passing it on
 * instead of deciding here is deliberate: this module cannot reach the router or the catalogue,
 * and a reason is only worth anything on the screen that has both.
 */
let onRuntimeSessionExpired: ((reason: string | null) => void) | null = null;
export function setOnRuntimeSessionExpired(fn: ((reason: string | null) => void) | null): void {
  onRuntimeSessionExpired = fn;
}

/**
 * What the probe found out. `dead` is the verdict of hub#846; `reason` is what hub#1801 added —
 * the two are separate on purpose, because «dead, and I can say why» and «dead» must not collapse
 * into one truthy value that a later reader mistakes for the other.
 */
interface SessionVerdict {
  dead: boolean;
  reason: string | null;
}

const ALIVE: SessionVerdict = { dead: false, reason: null };

/** Single-flight death confirmation: one probe per burst, not one per call in flight. */
let sessionProbe: Promise<SessionVerdict> | null = null;

/**
 * Is the local session actually DEAD? A raw `401` is not enough to know: several admin-gated
 * handlers map a role refusal to 401 too (`crates/server/src/settings.rs` documents «401 para
 * fallo de auth (sin sesión / sesión inválida / **rol insuficiente**)»), and signing a live
 * cashier out for touching an admin door would be a regression, not a fix. `GET /api/settings`
 * accepts ANY valid user session (`require_user_session`), so a 401 THERE can only mean the
 * session itself is gone. A probe that cannot be read (network failure) answers "not dead":
 * death is proven, never presumed — connectivity must stay a retryable error (hub#770).
 */
function probeSessionDead(): Promise<SessionVerdict> {
  if (!sessionProbe) {
    sessionProbe = (async () => {
      try {
        const res = await fetch(`${RUNTIME_URL}/api/settings`, { headers: runtimeHeaders() });
        if (res.status !== 401) return ALIVE;
        // The refusal names WHY, as data (hub#1801). Read only on the death path, and never
        // allowed to change the verdict: a body that cannot be parsed still means dead — the
        // session is gone either way, and `sessionEndReason` answers `null` for every silence.
        const body = await res.json().catch(() => null);
        return { dead: true, reason: sessionEndReason(body) };
      } catch {
        return ALIVE;
      }
    })();
    void sessionProbe.finally(() => {
      sessionProbe = null;
    });
  }
  return sessionProbe;
}

/**
 * The one place every runtime 401 goes through. Returns `true` when the 401 meant "this session
 * is dead" — and by then the shell session has been invalidated (once) and the hook fired.
 */
async function handleRuntime401(): Promise<boolean> {
  // Only a shell that believes it is signed in can be signed out. The login screen probes the
  // runtime without a session and collects 401s legitimately — nothing to react to.
  if (!getHubSession() && !user.value) return false;
  const verdict = await probeSessionDead();
  if (!verdict.dead) return false;
  // Invalidate ONCE: a screen load has dozens of calls in flight and they all hit this on the
  // same dead session. `logout()` clears the local session synchronously, so the first arrival
  // closes it and every other in-flight 401 falls out at this guard.
  if (getHubSession() || user.value) {
    logout();
    onRuntimeSessionExpired?.(verdict.reason);
  }
  return true;
}

/**
 * `fetch` against the runtime with the central 401 handling of hub#846. Behaves exactly like
 * `fetch` — network errors and non-401 statuses pass through untouched, so every caller keeps its
 * own degradation contract — except that a 401 from a confirmed-dead session throws
 * [`RuntimeSessionExpiredError`] instead of returning, so no caller can flatten it to "no data".
 */
async function runtimeFetch(input: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(input, init);
  if (res.status === 401 && (await handleRuntime401())) {
    throw new RuntimeSessionExpiredError();
  }
  return res;
}

/**
 * The `fetch` of the MODULE transport (hub#2281): a 401 feeds the same central reaction as the
 * shell's own calls, so a module screen that meets a dead session leads to the login instead of
 * showing a refusal and nothing else.
 *
 * Unlike [`runtimeFetch`] it never throws: the response goes back to the SDK, which reads the
 * refusal as `unauthorized`. A throw here would reach the SDK as a transport failure, and on a
 * command that is the «we can't tell whether it completed» verdict (hub#906) — false for a 401,
 * which the runtime answers before anything runs. The global `fetch` is read on every call, not
 * captured once, like everywhere else in this file.
 */
function moduleTransportFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  return fetch(input, init).then((res) => {
    if (res.status === 401) void handleRuntime401();
    return res;
  });
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
 * is called on every reconnect attempt, and a throw would kill the channel for good. A 401 from a
 * session confirmed dead still triggers the CENTRAL reaction (hub#846) on its way to `null`: this
 * retry loop was the «WS 101 + 401 every ~10 s» symptom of hub#902, hammering forever a door that
 * retrying could never open.
 */
export async function fetchStreamTicket(): Promise<string | null> {
  try {
    const res = await runtimeFetch(`${RUNTIME_URL}/api/events/ticket`, {
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

/**
 * **The credential a PHOTO can carry** (hub#791).
 *
 * Everything the app calls goes out with `X-Hub-Session` attached by hand. A photo is not one of
 * those: `<img src="/api/media/raw?path=…">` is issued by the rendering engine, which attaches
 * nothing — so the till's product pictures came back 401 and the grid came up blank. What the
 * browser does attach by itself is a cookie, so the hub mints one: read-only, `HttpOnly`, and scoped
 * by `Path` to the media read door alone (`crates/server/src/media.rs`).
 *
 * Called on boot and after every login, because the cookie carries the session token and therefore
 * dies with the session. It is not called before there IS a session: that request could only be a
 * 401, and a 401 is not free — it feeds the central dead-session reaction (hub#846).
 *
 * Returns `false` — never throws — on any refusal or network failure. This runs before the router
 * mounts, so a throw here would trade "the photos are missing" for "the till does not open".
 */
export async function ensureMediaCookie(): Promise<boolean> {
  if (!getHubSession()) return false;
  try {
    const res = await runtimeFetch(`${RUNTIME_URL}/api/media/session`, {
      method: 'POST',
      headers: runtimeHeaders(),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** Singleton del cliente SDK (HTTP RPC + WS eventos) apuntado al runtime local. */
export function getClient(): ErploraClient {
  if (!_client) {
    const transport = new HttpWsTransport({
      baseUrl: RUNTIME_URL,
      headers: runtimeHeaders,
      // hub#2281: a module's 401 goes through the same dead-session reaction as the shell's own.
      fetchImpl: moduleTransportFetch,
      // hub#504: without this the socket connects and is told nothing — the live dashboard, the
      // auto-print on a sale, the kitchen docket and the install progress all go silent.
      streamCredential: fetchStreamTicket,
      onStreamRefused: (code, message) => {
        // A channel that goes quiet without a word is the failure nobody debugs. This one says so.
        console.error(`[erplora] the event channel was refused (${code}): ${message}`);
      },
      // hub#363: the manager's PIN, asked for HERE — once, for every app. Wiring it per screen
      // would mean the first module that forgets leaves a cashier staring at a raw
      // `requires_elevation` instead of a dialog, and nothing would say which one forgot.
      elevationApprover: askForApproval,
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
        // La zona horaria RESUELTA del negocio (hub#1022): misma fuente que el resto del shell
        // (`hubTimezone()` ← `/api/hub/context`), para que un módulo que agende lea el MISMO
        // reloj que el runtime le entrega a un handler (`context.timezone`).
        timezone: hubTimezone,
        // hub#1211: gives `queryOptional`/`queryAllOptional` the set of ACTIVE modules — without
        // it, the only way to learn a module was missing was to ask the transport anyway and catch
        // `module_not_installed` after the request had already travelled.
        installedModules: activeModuleIds,
        notifier: (n) => {
          const color: ToastColor =
            n.type === 'success' ? 'success' : n.type === 'error' ? 'danger' : n.type === 'warning' ? 'warning' : 'primary';
          void toast(n.message, color);
        },
      },
      bridge,
    );
    // Initial seed (hub#1211): while it resolves, `activeModuleIds()` keeps answering `undefined`
    // ("not known yet") and the SDK falls back to asking the transport, as before. On a cold boot
    // there is no session yet and the seed asks nothing — login re-seeds through `setHubSession`.
    void refreshActiveModuleIds();
    // `module.installed` (ARQUITECTURA.md §2.2/§4) is the only module lifecycle WS event that
    // exists today; activate/deactivate/uninstall emit none of their own, so those three refresh
    // synchronously when `moduleAction` resolves (in THIS tab — another tab only learns of them on
    // its next refresh, see the note on `refreshActiveModuleIds`).
    _client.on('module.installed', () => {
      void refreshActiveModuleIds();
    });
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
  /** hub#1130: ids que el cierre de dependencias (ADR-0060) instaló junto al pedido, y que NO
   *  estaban instalados antes de esta llamada. Siempre presente — vacío, nunca ausente, cuando
   *  no arrastró nada — para que quien la lea no tenga que distinguir dos formas. */
  also_installed: string[];
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
  /** What the RUNTIME said, or `null` if its body could not be read. See `InstallFailedError`. */
  readonly detail: string | null;

  constructor(
    message: string,
    blockedOn: string[],
    purchase: InstallPurchaseOption[],
    detail: string | null = null,
  ) {
    super(message);
    this.name = 'InstallBlockedError';
    this.blockedOn = blockedOn;
    this.purchase = purchase;
    this.detail = detail;
  }
}

/** Fallo de instalación con el CÓDIGO estable del runtime (hub#139) para que la UI lo traduzca. */
export class InstallFailedError extends Error {
  readonly code: string;
  /**
   * The sentence the RUNTIME sent, or `null` when its body could not be read (hub#673).
   *
   * `message` is no good for this: it falls back to a TECHNICAL string on purpose
   * (`request-install sales → 502`), which is what the logs want and the last thing to show
   * somebody running a shop. `detail` separates «the runtime said something» from «it said
   * nothing», which is the only way to know whether there is a sentence worth replacing ours with.
   */
  readonly detail: string | null;
  /**
   * The facts the translated sentence names, or `null` when the code needs none (hub#1620): «this
   * app needs ERPlora {required} and your hub runs {core}» travels as data, never parsed out of
   * the engine's English line.
   */
  readonly params: Record<string, string> | null;

  constructor(
    message: string,
    code: string,
    detail: string | null = null,
    params: Record<string, string> | null = null,
  ) {
    super(message);
    this.name = 'InstallFailedError';
    this.code = code;
    this.detail = detail;
    this.params = params;
  }
}

/**
 * The versions a `core_version_too_old` refusal carries (hub#1620), or `null` when the body does
 * not bring both — a half sentence («needs ERPlora  · yours is 1.1.15») is worse than none.
 */
function coreVersionParams(body: Record<string, unknown> | null): Record<string, string> | null {
  const required = body?.required;
  const core = body?.core;
  return typeof required === 'string' && typeof core === 'string' && required && core
    ? { required, core }
    : null;
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
    const res = await runtimeFetch(`${RUNTIME_URL}/api/modules/request-install`, {
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
      // What the runtime said (hub#673), kept apart from the technical message the logs want:
      // `null` when the body could not be read, so there is no sentence of its own to show.
      const detail = typeof body?.error === 'string' ? (body.error as string) : null;
      const message = detail || `request-install ${moduleId} → ${res.status}`;
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
        throw new InstallBlockedError(message, (body?.blocked_on as string[]) ?? [], purchase, detail);
      }
      throw new InstallFailedError(message, code, detail, coreVersionParams(body));
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
  const res = await runtimeFetch(`${RUNTIME_URL}/api/modules?locale=${encodeURIComponent(getLocale())}`, {
    headers: runtimeHeaders(),
  });
  if (!res.ok) throw new Error(`modules → ${res.status}`);
  const env = (await res.json()) as {
    ok: boolean;
    data?: InstalledModule[];
    error?: { message?: string } | string;
  };
  // A 200 whose envelope says `ok:false` is a DOMAIN error, not "this hub has no modules": it was
  // flattened to `[]` here and a hub with 12 registered modules showed «you have no apps yet»,
  // inviting its owner to reinstall what they already had (hub#894 / hub#846). It surfaces — and
  // it is NOT a session death either, so the central 401 reaction plays no part in it.
  if (!env.ok) {
    const msg = typeof env.error === 'string' ? env.error : env.error?.message;
    throw new Error(msg?.trim() ? msg : 'modules → the runtime reported a failure');
  }
  return env.data ?? [];
}

// hub#1211 — the live set of ACTIVE module ids, published for `ErploraClient`'s `installedModules`
// option (`getClient()` below): lets `queryOptional`/`queryAllOptional` learn a module is absent
// WITHOUT a round trip, instead of asking the transport and catching `module_not_installed` after
// the request already happened — which is what left a `404 POST /api/query` in the console on
// EVERY call of an optional integration the hub does not have (`sales` asking `verifactu`, hub#1121
// surfaced it as `sales` → `modifiers`). `undefined` means "not known yet"; the SDK treats that as
// "cannot rule the module out" and falls back to asking the transport, same as before this existed.
let activeModuleIdsCache: ReadonlySet<string> | undefined;

/** Current answer for `ErploraClient`'s `installedModules` option. Inyectable/legible en tests. */
export function activeModuleIds(): ReadonlySet<string> | undefined {
  return activeModuleIdsCache;
}

/**
 * Republishes the ACTIVE module id set (hub#1211). Exported so tests can seed/clear it exactly
 * like `publishHubTimezone` — `null`/`undefined` clears it back to "not known yet".
 */
export function publishActiveModuleIds(ids: ReadonlySet<string> | null | undefined): void {
  activeModuleIdsCache = ids ?? undefined;
}

/**
 * Re-asks the runtime which modules are ACTIVE and republishes the set (hub#1211). Called once at
 * client construction, on every login (`setHubSession`, the funnel all five ways in go through —
 * `main.ts` builds the client on a cold boot BEFORE anyone signs in, and login is a route change,
 * not a reload) and after every install (`module.installed` WS event) / activate / deactivate /
 * uninstall — the exact same moments the shell already refreshes its own nav and module list.
 *
 * Never asks before there IS a session, same rule as `ensureMediaCookie`: that request could only
 * be a 401, which is console noise of the exact kind this exists to remove and feeds the central
 * dead-session probe (hub#846). Best-effort by contract, like `refreshHubTimezone`: a failed
 * refresh KEEPS the previous answer (never publishes an empty set on a transient error, which
 * would make every optional query look absent) — it just stays `undefined` ("not known yet") if
 * there was no previous answer either.
 */
export async function refreshActiveModuleIds(): Promise<void> {
  if (!getHubSession()) return;
  try {
    const modules = await listInstalledModules();
    publishActiveModuleIds(new Set(modules.filter((m) => m.status === 'active').map((m) => m.id)));
  } catch {
    // Keeps the previous answer — see the doc comment above.
  }
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

  /**
   * Las apps que dejarían de funcionar, cuando el rechazo es `has_dependents` (hub#1101).
   *
   * Viaja como CAMPO, igual que el `permission` de `requires_elevation`: la pantalla la ENUMERA,
   * y sacarla a fuerza de parsear una frase es exactamente lo que hace que un día deje de
   * funcionar en silencio.
   */
  readonly dependents?: readonly string[];

  constructor(message: string, code?: string, dependents?: readonly string[]) {
    super(message);
    this.name = 'ModuleActionError';
    this.code = code;
    this.dependents = dependents;
  }
}

/**
 * Activa / desactiva / desinstala un módulo en el runtime (hot-plug). Lanza si el runtime falla.
 *
 * `force` (solo en `uninstall`, hub#1101) es la respuesta del dueño a «otras apps necesitan esta,
 * ¿la quito igualmente?», después de que la pantalla se las haya nombrado. Sin él el runtime
 * rechaza con `409 has_dependents`, que es lo que tiene que pasarle a quien nunca vio esa lista:
 * un script, el asistente, un flujo o un `curl`. Por eso el cuerpo **no se manda** cuando no hay
 * nada que confirmar — «sin cuerpo» tiene que seguir significando la respuesta segura.
 */
async function moduleAction(
  id: string,
  action: 'activate' | 'deactivate' | 'uninstall',
  opts: { force?: boolean } = {},
): Promise<void> {
  const res = await runtimeFetch(`${RUNTIME_URL}/api/modules/${encodeURIComponent(id)}/${action}`, {
    method: 'POST',
    headers: opts.force
      ? { ...runtimeHeaders(), 'Content-Type': 'application/json' }
      : runtimeHeaders(),
    ...(opts.force ? { body: JSON.stringify({ force: true }) } : {}),
  });
  const env = (await res.json().catch(() => ({}))) as {
    ok?: boolean;
    error?: { code?: string; message?: string; dependents?: string[] };
  };
  if (!res.ok || env.ok === false) {
    throw new ModuleActionError(
      env.error?.message ?? `${action} ${id} → ${res.status}`,
      env.error?.code,
      env.error?.dependents,
    );
  }
  // hub#1211: activate/deactivate/uninstall change WHICH modules are active — re-publish the set
  // the SDK's short-circuit reads, or an optional query for the module just (de)activated would
  // keep answering with yesterday's cache until something else happened to refresh it.
  await refreshActiveModuleIds();
}

/**
 * Pide al runtime **actualizar** un módulo instalado (hub#516). Mismo pipeline verificado que
 * instalar (SHA256 + firma ed25519 + manifest + plan de dependencias) y las mismas fases por WS.
 *
 * Sin versión, el runtime resuelve la que toca con el resolutor del arranque: nunca una en
 * cuarentena, nunca hacia atrás, y el pin de soporte gana. `updated: false` **no es un fallo**: es
 * «ya está en la versión que le toca».
 *
 * Los errores llegan con el mismo contrato que `requestInstall`: un 409 por dependencia de pago sin
 * contratar sale como [`InstallBlockedError`] (nunca se cobra solo), el resto como
 * [`InstallFailedError`] con su `code` estable.
 */
export async function updateModule(moduleId: string, version = ''): Promise<ModuleUpdateResult> {
  beginRequest();
  try {
    const res = await runtimeFetch(`${RUNTIME_URL}/api/modules/${encodeURIComponent(moduleId)}/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
      body: JSON.stringify({ version }),
    });
    if (!res.ok) {
      let body: Record<string, unknown> | null = null;
      try {
        body = (await res.json()) as Record<string, unknown>;
      } catch {
        body = null;
      }
      const detail = typeof body?.error === 'string' ? (body.error as string) : null;
      const message = detail || `update ${moduleId} → ${res.status}`;
      const code = (body?.code as string) || 'update_failed';
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
        throw new InstallBlockedError(message, (body?.blocked_on as string[]) ?? [], purchase, detail);
      }
      throw new InstallFailedError(message, code, detail, coreVersionParams(body));
    }
    return (await res.json()) as ModuleUpdateResult;
  } finally {
    endRequest();
  }
}

/** Respuesta de `POST /api/modules/{id}/update`. */
export interface ModuleUpdateResult {
  ok: boolean;
  module_id: string;
  from: string;
  to: string;
  /** `false` = ya estaba en la versión que le toca; no se descargó nada. */
  updated: boolean;
}

/**
 * Qué versión ofrece hoy el marketplace para cada módulo instalado (`GET /api/modules/updates`).
 *
 * **On demand, never a fast poll**: each call asks the Cloud once per installed module. The Apps
 * screen asks when it opens, and the bell's «N apps have a new version» (hub#1172,
 * `module-update-notice.ts`) asks when an admin session starts and then hours apart. A failure
 * returns an empty list: with no answer, nothing is offered.
 */
export async function listModuleUpdates(): Promise<ModuleUpdateInfo[]> {
  const res = await runtimeFetch(`${RUNTIME_URL}/api/modules/updates`, { headers: runtimeHeaders() });
  if (!res.ok) return [];
  const env = (await res.json().catch(() => ({}))) as { ok?: boolean; data?: ModuleUpdateInfo[] };
  return env.ok && env.data ? env.data : [];
}

/**
 * Entre qué versiones puede elegir este hub para un módulo (`GET /api/modules/{id}/versions`).
 *
 * Sirve a las dos puertas: instalar (el módulo aún no está: valen todas las publicadas) y actualizar
 * (solo hacia delante desde la instalada). El runtime ya aplica ahí la política —fuera cuarentena,
 * fuera retroceso, y un módulo clavado por soporte no ofrece nada—, así que la pantalla pinta lo que
 * le llega y no filtra por su cuenta.
 *
 * Un fallo devuelve la lista vacía, y el llamante cae a `latest`: sin lista se instala igual que
 * antes de que existiera el desplegable. Quedarse sin poder instalar porque el Cloud no contestó
 * sería un precio absurdo por una comodidad.
 */
export async function listModuleVersions(moduleId: string): Promise<ModuleVersions> {
  const empty: ModuleVersions = { module_id: moduleId, installed: null, latest: null, versions: [] };
  const res = await runtimeFetch(`${RUNTIME_URL}/api/modules/${encodeURIComponent(moduleId)}/versions`, {
    headers: runtimeHeaders(),
  });
  if (!res.ok) return empty;
  const env = (await res.json().catch(() => ({}))) as { ok?: boolean; data?: ModuleVersions };
  return env.ok && env.data ? env.data : empty;
}

/**
 * Whether the marketplace still OFFERS one module (`GET /api/marketplace/modules/{id}`, hub#1134).
 *
 * The runtime proxies the Cloud's module record with the hub's machine token and hands it over
 * untouched; the only field this screen reads out of it is `publication_status` (ADR-0380). It is
 * the DETAIL door on purpose: the catalogue lists `listed` modules only, so it is the one door that
 * still answers for a module this hub runs and the marketplace has retired.
 *
 * `null` = "I could not ask" — no credential, no network, a Cloud that answered something else.
 * It is never `listed`: silence and "still on the shelf" are different facts, and the caller
 * paints neither of them.
 */
export async function modulePublicationStatus(moduleId: string): Promise<PublicationStatus | null> {
  try {
    const res = await runtimeFetch(
      `${RUNTIME_URL}/api/marketplace/modules/${encodeURIComponent(moduleId)}`,
      { headers: runtimeHeaders() },
    );
    if (!res.ok) return null;
    const body = (await res.json().catch(() => null)) as Record<string, unknown> | null;
    const raw = body?.publication_status;
    // An answer that does not carry the field comes from a SaaS older than saas#1542. That is
    // "I do not know", not "listed": inventing the healthy state here would be indistinguishable
    // from having asked and been told.
    return raw === undefined || raw === null ? null : publicationStatusOf(raw);
  } catch (error) {
    console.warn(`[runtime] publication status of ${moduleId} could not be read`, error);
    return null;
  }
}

export const activateModule = (id: string): Promise<void> => moduleAction(id, 'activate');
export const deactivateModule = (id: string): Promise<void> => moduleAction(id, 'deactivate');
export const uninstallModule = (id: string, opts: { force?: boolean } = {}): Promise<void> =>
  moduleAction(id, 'uninstall', opts);

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
 * El catálogo de respaldo de labels vive en `./module-capabilities` (`CAPABILITY_CATALOG`).
 *
 * Estaba aquí con CUATRO entradas y `manage_flows` (hub#714) nunca se añadió: un espejo
 * desincronizado de `crates/server/src/settings.rs::capability_meta` que nadie leía (el servidor
 * manda `label`) hasta que hizo falta ponerle nombre a un id suelto del catálogo Cloud (pm#132).
 * Ahora vive junto a la lógica que lo usa, con descripción además de etiqueta.
 */

/**
 * Lee las capabilities (permisos) que declara un módulo instalado y su estado de concesión.
 * Cualquier sesión puede leerlas; conceder/revocar es solo admin (`putModuleCapabilities`).
 */
export async function getModuleCapabilities(moduleId: string): Promise<ModuleCapabilities> {
  const res = await runtimeFetch(
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
  const res = await runtimeFetch(
    `${RUNTIME_URL}/api/modules/${encodeURIComponent(moduleId)}/capabilities`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
      body: JSON.stringify({ grants }),
    },
  );
  if (!res.ok) throw new Error(`put-capabilities ${moduleId} → ${res.status}`);
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
 * Lo que `GET /api/hub/export/tables` le cuenta al formulario de export.
 *
 * `lockedPurpose` es el `purpose` que el hub tiene IMPUESTO (hub#377, ADR-0195): un hub de
 * desarrollo sin enrolar o una demo efímera exporta SIEMPRE como plantilla, decida lo que decida
 * el formulario. `null` = el usuario elige.
 *
 * 🔴 hub#1249: sin este dato el formulario ofrecía «copia de seguridad» con la casilla de usuarios
 * marcada y el servidor devolvía un zip sin usuarios, en silencio — una copia que parece hecha y
 * no lo está.
 */
export interface ExportTablesInfo {
  modules: ExportModuleTables[];
  lockedPurpose: BundlePurpose | null;
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
  // ADR-0273 D8 / hub#560. El runtime lo emitía desde entonces y esta lista no lo conocía, así que
  // la fila del informe enseñaba la cadena cruda.
  'system_table_not_portable',
  // hub#753 — la serie de facturación y el libro de números ya entregados son de UNA instalación.
  'numbering_not_portable',
  // hub#380 — la sección es de un módulo que declara `installation_bound_data` en su module.json:
  // sus registros son de la instalación que los emitió. Antes el motivo era prosa que nombraba
  // VeriFactu; el código sirve igual para TicketBai o NF525, y aquí se traduce.
  'installation_bound_data',
  // hub#473 — los permisos módulo→host (`certificate`, `network`, `printer`, `notify`) que el dueño
  // había concedido. De OTRO hub se descartan enteros; del backup PROPIO se reconceden los que el
  // módulo instalado siga declarando, y los demás se cuentan.
  'capability_grants_not_portable',
  'capabilities_not_grantable',
  // hub#986 — el kernel de automatización. El DOCUMENTO de un flujo es del negocio y aterriza; lo
  // que se le permitía hacer es la aprobación de ESTE despliegue, así que de otro hub no se
  // reconcede nada y el flujo llega en pausa (`flow_grants_not_portable`). En el backup PROPIO,
  // un permiso que aquí ya no existe deja el flujo pausado (`flows_paused_without_grants`), y un
  // documento que este hub rechazaría en la pantalla tampoco entra por el zip
  // (`flows_not_restorable`).
  'flow_grants_not_portable',
  'flows_paused_without_grants',
  'flows_not_restorable',
  // hub#1947 — la plantilla se publicó contra una versión anterior de la app y trae filas de una
  // tabla que la versión instalada ya no guarda (Citas devolvió el horario del negocio a Horarios).
  // Esas filas no pueden aterrizar en ningún sitio; lo que sí entró es el resto de la sección.
  'table_gone_in_installed_version',
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
  /**
   * Where the bundle came from (hub#845): the catalogue card (`source: "catalog"`, with the exact
   * `slug` + `version` a retry needs to re-download the SAME bundle) or an explicit
   * `source: "local"` for a hand-uploaded file — which is what makes that import non-retryable.
   * Absent on reports older than the field: same meaning as `local`, no origin to go back to.
   */
  origin?: ImportReportOrigin;
}

/** The persisted origin of an import (hub#845) — what decides whether a retry can act. */
export interface ImportReportOrigin {
  source: 'catalog' | 'local';
  slug?: string;
  version?: string;
  locale?: string;
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
  /**
   * The version the bundle pinned, present ONLY when it is not the one that got installed
   * (hub#751/#752): the marketplace had already pruned it and the engine fell back to the newest
   * compatible one. Absent = the pin was honoured exactly.
   */
  requested_version?: string;
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
  /**
   * La versión que pedía la plantilla, cuando NO es la que se instaló (hub#751/#752). Se pinta:
   * una plantilla que instala en silencio otra versión de la que anuncia es justo la sorpresa que
   * la sustitución evita.
   */
  substitutedFor?: string;
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
    return { kind: m.status, blockedOn: [], purchase: [], substitutedFor: m.requested_version };
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
export async function fetchExportTables(): Promise<ExportTablesInfo> {
  const empty: ExportTablesInfo = { modules: [], lockedPurpose: null };
  try {
    const res = await runtimeFetch(`${RUNTIME_URL}/api/hub/export/tables`, { headers: runtimeHeaders() });
    if (!res.ok) return empty;
    const body = (await res.json()) as {
      modules?: ExportModuleTables[];
      locked_purpose?: BundlePurpose | null;
    };
    return {
      modules: Array.isArray(body.modules) ? body.modules : [],
      // Un runtime anterior a hub#1249 no manda el campo: `null` = «elige tú», que es lo que ese
      // runtime hacía. Solo un valor conocido ata el formulario — un `purpose` que no entendemos
      // no puede desactivar casillas a ciegas.
      lockedPurpose: body.locked_purpose === 'template' || body.locked_purpose === 'backup'
        ? body.locked_purpose
        : null,
    };
  } catch {
    return empty;
  }
}

/**
 * Deadline del export (hub#765). El POST empaqueta datos de cada módulo + media, así que puede
 * tardar más que un `fetch` normal; pero NO puede ser infinito. Sin deadline, un runtime o proxy
 * colgado deja el spinner girando hasta que el usuario se rinde — y se va pensando que la copia
 * existe. Dos minutos cubre los zips grandes (módulos + imágenes) y sigue siendo finito: una copia
 * que no sabe decir que falló es peor que una que suelta el error.
 */
const EXPORT_DEADLINE_MS = 120_000;

export async function exportHub(
  name: string,
  locale: string,
  selection: ExportSelection,
): Promise<{ blob: Blob; filename: string }> {
  beginRequest(); // volcar datos + empaquetar puede tardar → barra de progreso del shell
  // El AbortController es lo que convierte un cuelgue en un error accionable: cuando salta el
  // deadline, el fetch rechaza con un nombre legible en vez de quedarse abierto para siempre.
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), EXPORT_DEADLINE_MS);
  try {
    let res: Response;
    try {
      res = await runtimeFetch(`${RUNTIME_URL}/api/hub/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
        body: JSON.stringify({ name, locale, selection }),
        signal: ctrl.signal,
      });
    } catch (e) {
      // `AbortController#abort()` rechaza como `DOMException` nombre `TimeoutError` (o `AbortError`
      // en algunos navegadores). Ese es el caso del deadline: el runtime no respondió a tiempo.
      if (ctrl.signal.aborted) throw new Error('export → timeout');
      // Otro error de red (runtime caído, sin conexión): que el mensaje original llegue al usuario.
      throw e instanceof Error ? e : new Error(String(e));
    }
    if (!res.ok) throw new Error(await readErrorMessage(res, `export → ${res.status}`));
    const blob = await res.blob();
    const filename =
      filenameFromDisposition(res.headers.get('Content-Disposition')) ??
      `${name}_${locale}.blueprint.zip`;
    return { blob, filename };
  } finally {
    clearTimeout(timer);
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
    const res = await runtimeFetch(`${RUNTIME_URL}/api/blueprints/catalog`, { headers: runtimeHeaders() });
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
    const res = await runtimeFetch(`${RUNTIME_URL}/api/blueprints/${encodeURIComponent(slug)}/download`, {
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
    const res = await runtimeFetch(`${RUNTIME_URL}/api/hub/import/inspect`, {
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
  // hub#845 — the catalogue card the bundle came from, so the persisted report keeps the exact
  // origin (slug + version) a retry needs. Omitted for a local file: the report then says
  // `origin.source: "local"` and the retry button explains itself instead of guessing.
  origin?: { slug: string; version: string },
): Promise<ImportReport> {
  beginRequest(); // instalar módulos + aplicar SQL puede tardar → barra de progreso del shell
  try {
    const res = await runtimeFetch(`${RUNTIME_URL}/api/hub/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
      body: JSON.stringify({ upload_id: uploadId, selection, ...(origin ? { origin } : {}) }),
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
    // hub#974: the PIN length belongs to the hub (4 or 6). The context DOES carry it (hub#1765) —
    // it is the only read the login screen, which has no session, can make. When this response is
    // silent (older runtime, failed read) what is already known is kept rather than shortening the
    // PIN: falling back to 4 on a six-digit hub fires the login truncated at the fourth digit.
    pin_length: normalizePinLength(ctx.pin_length, hubSettings.value?.pin_length),
    // El contexto del hub solo trae moneda/idioma; la identidad de negocio la rellena el GET completo
    // de /api/settings (getHubSettings). Preservamos lo ya cacheado para no pisarlo con vacío.
    business_tax_id: hubSettings.value?.business_tax_id ?? '',
    business_legal_name: hubSettings.value?.business_legal_name ?? '',
    business_address: hubSettings.value?.business_address ?? '',
    business_street: hubSettings.value?.business_street ?? '',
    business_street_number: hubSettings.value?.business_street_number ?? '',
    business_postal_code: hubSettings.value?.business_postal_code ?? '',
    business_city: hubSettings.value?.business_city ?? '',
    business_identity_for_erplora_billing: hubSettings.value?.business_identity_for_erplora_billing ?? false,
    // La paleta global tampoco viaja en el context: la trae el GET completo (que además
    // la refleja en el shell vía theme.ts). Aquí solo se preserva la cache.
    theme_palette: hubSettings.value?.theme_palette ?? 'erplora',
    // El dial «pedir PIN» (hub#359) tampoco viaja en el context. Se preserva lo cacheado y, sin
    // cache, el valor que SIGUE preguntando: sembrar la cache con `never` porque el context calló
    // sería quitar el pinpad por una lectura que no habla de él. La autoridad son el GET completo
    // y `GET /api/device/mode` (que es el que lee la pantalla de login, sin sesión).
    pin_policy: hubSettings.value?.pin_policy ?? STRICT_PIN_POLICY,
    // Los minutos de inactividad (hub#628) tampoco viajan en el context: se preserva la cache o
    // el default del runtime (5) hasta el GET completo.
    pin_inactivity_minutes: hubSettings.value?.pin_inactivity_minutes ?? 5,
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
/**
 * How long the boot waits for `/api/hub/context` before «the hub is not answering» is the verdict
 * (hub#2143). Without it a request that never finishes kept the boot spinner turning for ever; the
 * browser's own timeout is over a minute. Same bound as the hub probe (`HUB_PROBE_TIMEOUT_MS`).
 */
export const BOOT_CONTEXT_TIMEOUT_MS = 10_000;

export async function bootHubContext(): Promise<HubContext | null> {
  // Cloud callers wait for this answer (hub#1164): a login that raced ahead would hit the
  // build-time URL and be blocked by the hub's own CSP.
  markCloudApiUrlPending();
  let cloudBaseUrl: string | null = null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), BOOT_CONTEXT_TIMEOUT_MS);
  try {
    const res = await fetch(`${RUNTIME_URL}/api/hub/context`, {
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
    });
    if (!res.ok) return null;
    const ctx = (await res.json()) as HubContext;
    cloudBaseUrl = typeof ctx.cloud_base_url === 'string' ? ctx.cloud_base_url : null;
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
    // Zona horaria RESUELTA del negocio (hub#731, hub#1022): se publica para módulos y shell
    // (`erplora.timezone` / `hubTimezone()`), el mismo IANA que el runtime bindea como
    // `:timezone` y entrega a los handlers como `context.timezone`. El context la trae SIEMPRE
    // resuelta (nunca `null`); ausente/imposible → UTC, que es lo que el reloj hará de todos modos.
    publishHubTimezone(ctx.timezone ?? null);
    return ctx;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
    // Always opens the gate: with the runtime's Cloud when it answered, with the fallback otherwise.
    resolveCloudApiUrl(cloudBaseUrl);
  }
}

/**
 * Vuelve a preguntar al runtime la zona horaria RESUELTA del negocio y la republica (hub#1154).
 *
 * Hace falta porque el ajuste que se guarda NO es el que se usa: `hub_settings.timezone` puede ser
 * `null` («dedúcela del país»), y quien sabe deducirla —y quien conoce la tabla de husos— es el
 * runtime, no el navegador. Duplicar aquí esa deducción crearía una segunda autoridad sobre el
 * reloj del negocio, que es justo lo que `schedules` acaba de retirar por haberse desincronizado.
 * Así que tras guardar se pregunta, no se calcula.
 *
 * Es deliberadamente MÁS ESTRECHO que `bootHubContext`: lee el mismo documento pero solo toca la
 * zona. Reusar el boot entero desde una pantalla de ajustes re-sembraría la cache de settings, el
 * idioma y la URL de Cloud como efecto colateral de cambiar una lista desplegable.
 *
 * Best-effort por contrato: si el runtime no contesta se queda la zona publicada anterior y se
 * devuelve `null`. Lo que NO hace es publicar un valor inventado — un reloj que miente con
 * confianza es peor que uno que se ha quedado atrás.
 */
export async function refreshHubTimezone(): Promise<string | null> {
  try {
    const res = await fetch(`${RUNTIME_URL}/api/hub/context`, {
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) return null;
    const ctx = (await res.json()) as HubContext;
    const zone = typeof ctx.timezone === 'string' && ctx.timezone.trim() ? ctx.timezone.trim() : null;
    if (!zone) return null;
    publishHubTimezone(zone);
    return zone;
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
  /**
   * Undo only (hub#1556): tables where what the import replaced did NOT come back, because the
   * business had written its own rows there afterwards. Absent/empty when nothing was lost.
   */
  not_restored?: string[];
}

/**
 * Dry-run del reset (`POST /api/hub/reset/plan`): NO borra nada. Se llama al abrir el panel para
 * pintar las secciones con sus cifras y sus bloqueos.
 */
export async function fetchResetPlan(): Promise<ResetPlan> {
  const res = await runtimeFetch(`${RUNTIME_URL}/api/hub/reset/plan`, {
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
    const res = await runtimeFetch(`${RUNTIME_URL}/api/hub/reset`, {
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
  /**
   * Tables the business edited after this import (hub#1556): undoing it now keeps only its own
   * rows there. The undo confirmation warns off this.
   */
  edited_after_import?: string[];
}

/** Importaciones del hub, de la más reciente a la más antigua (`GET /api/hub/import/batches`). */
export async function fetchImportBatches(): Promise<ImportBatch[]> {
  const res = await runtimeFetch(`${RUNTIME_URL}/api/hub/import/batches`, { headers: runtimeHeaders() });
  if (!res.ok) throw new Error(await readErrorMessage(res, `import/batches → ${res.status}`));
  const body = (await res.json()) as { ok: boolean; batches?: ImportBatch[] };
  return body.batches ?? [];
}

/**
 * El último informe de importación persistido del hub (hub#763): lo que el Dashboard anuncia y la
 * pestaña Datos recupera al montarse, para que navegar fuera del hero (o recargar) no pierda el
 * informe accionable. `null` = sin import reciente, o el último lote ya se deshizo.
 */
export interface StoredImportReport {
  /** `batch_id` del lote — para deshacerlo o reintentarlo. */
  batch_id: string;
  /** Nombre del blueprint, como lo reconoce el usuario. */
  name: string;
  /** Cuándo se corrió el import (RFC3339). */
  created_at: string;
  /** El informe extendido: `sections` + `installed_modules` + `media` + `fiscal`. */
  report: ImportReport;
}

/** Recupera el último informe de importación del hub (`GET /api/hub/import/report`, hub#763). */
export async function fetchImportReport(): Promise<StoredImportReport | null> {
  const res = await runtimeFetch(`${RUNTIME_URL}/api/hub/import/report`, { headers: runtimeHeaders() });
  if (!res.ok) throw new Error(await readErrorMessage(res, `import/report → ${res.status}`));
  const body = (await res.json()) as { ok: boolean; report?: StoredImportReport | null };
  return body.report ?? null;
}

/** Outcome of `POST /api/hub/import/retry` (hub#845). */
export interface RetryOutcome {
  /** `false` = explicit no-op: everything in that import already applied (`code` says so). */
  retried: boolean;
  /** Stable server code (`import_nothing_to_retry`, …) when the run did not happen. */
  code?: string;
  /** The fresh extended report when the retry ran; `null` on a no-op. */
  report: ImportReport | null;
}

/** A retry the server REFUSED, keeping its stable code so the shell can translate it (hub#845). */
export class RetryRefusedError extends Error {
  code?: string;
  constructor(message: string, code?: string) {
    super(message);
    this.name = 'RetryRefusedError';
    this.code = code;
  }
}

/**
 * Retries ONLY what a partial import left out (`POST /api/hub/import/retry`, hub#845): the server
 * derives the selection from the persisted report of that `batch_id`, re-downloads the SAME
 * catalogue bundle (slug + version travel with the report) and re-runs it. What already applied is
 * never duplicated — that is the engine's natural-key guarantee (ADR-0304), not a UI promise.
 *
 * Throws {@link RetryRefusedError} with the server's stable `code` when the retry cannot run: a
 * local upload has no origin to re-download (`import_origin_not_retryable`), or the catalogue no
 * longer serves the imported version (`import_retry_version_unavailable`).
 */
export async function retryImport(batchId: string): Promise<RetryOutcome> {
  beginRequest(); // installing modules + applying SQL can take a while → shell progress bar
  try {
    const res = await runtimeFetch(`${RUNTIME_URL}/api/hub/import/retry`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
      body: JSON.stringify({ batch_id: batchId }),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      let code: string | undefined;
      let message = text.trim() || `import/retry → ${res.status}`;
      try {
        const parsed = JSON.parse(text) as { code?: string; error?: { message?: string } | string };
        code = parsed.code;
        const m = typeof parsed.error === 'string' ? parsed.error : parsed.error?.message;
        if (m) message = m;
      } catch {
        // Not JSON: the raw text is the honest message.
      }
      throw new RetryRefusedError(message, code);
    }
    const body = (await res.json()) as {
      ok: boolean;
      retried?: boolean;
      code?: string;
      report?: ImportReport | null;
    };
    return { retried: Boolean(body.retried), code: body.code, report: body.report ?? null };
  } finally {
    endRequest();
  }
}

/**
 * Deshace una importación (`POST /api/hub/import/undo`): borra solo lo que trajo ese blueprint,
 * conservando lo que el usuario creó después. Un lote ya deshecho es un no-op.
 */
export async function undoImport(batchId: string): Promise<ResetReport> {
  beginRequest();
  try {
    const res = await runtimeFetch(`${RUNTIME_URL}/api/hub/import/undo`, {
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
