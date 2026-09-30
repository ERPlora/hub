// **Which device is this?** — the identity every "per device" decision of the hub keys on
// (ARQUITECTURA.md §2.9b, ADR-0154; the browser half is hub#454).
//
// Two hosts, two very different answers:
//
//  - **The Tauri shell** knows a real one. The `device_context` command (exposed through
//    `withGlobalTauri` → `window.__TAURI__.core.invoke`, so no `@tauri-apps/api` dependency)
//    returns an id per *installation*, persisted by the shell in `app_data_dir` — outside the
//    webview, so clearing the site data does not touch it.
//  - **A browser** has no serial number at all. The only identity available is one the browser
//    **mints for itself and keeps** in its own site storage, which is what [`browserDeviceId`]
//    does. A browser profile on a machine is therefore what "device" means here: another browser,
//    another OS user, a private window or a wipe of the site data are all *another device*.
//
// **The identity is client-held, and that decides what may rest on it.** Whoever holds the browser
// can read it, change it or copy it into another one, so it can only ever NAME a device — so the
// owner recognises it, the hub keys the device mode (hub#357) on it and the device-trust row
// (§2.9, hub#330) hangs off it. It is never a credential: no door opens because of the value here,
// and every path that reads it fails closed when it is absent or unknown (`shared`, the short
// session, and a refused PIN under `HUB_DEVICE_TRUST=enforce`).
//
// What it must never be is the **hub's** id. That was the bug hub#454 fixes: the web presented
// `hub_id` as its device identity, so every browser in the world was one single device — marking
// the owner's laptop `personal` took the pinpad off the till at the counter — and that id is
// published unauthenticated by `GET /api/hub/context`, which put "this device is trusted" within
// reach of anyone who could fetch one JSON.

export interface DeviceContext {
  id: string;
  clientType: 'hub-desktop' | 'hub-local' | 'hub-cloud';
  platform?: 'android' | 'windows' | 'macos' | 'linux' | 'cloud' | 'desktop';
  /**
   * How this binary reached the device — the shell stamps it at compile time (hub#757).
   *
   * It cannot be derived here: the web app is served by the hub, so one bundle answers every
   * install at once (ADR-0154/0159) and a build flag of THIS bundle could never tell a Play
   * install from a sideloaded one. Only the shell knows, and only when it was built.
   *
   * `undefined` means a shell older than hub#757, and is read as `direct` on purpose: those
   * builds are the ones nobody else updates, so taking their notice away would strand them.
   */
  distribution?: 'play' | 'msstore' | 'direct';
}

/**
 * What the runtime can say about this client: what **kind** it is, never **which** one.
 *
 * The hub cannot see the browser in front of it, and the only stable id it owns names the *hub*.
 * So this carries the client type and platform that travel to the Cloud on a login, and the device
 * identity is resolved where it actually lives — the shell, or the browser's own storage. Making
 * the id unrepresentable here is the point: it is the shape the previous bug needed.
 */
export interface ClientKind {
  clientType: DeviceContext['clientType'];
  platform?: DeviceContext['platform'];
}

let runtimeClientKind: ClientKind | null = null;

/** Publish what kind of client this is, as the runtime reported it (`GET /api/hub/context`). */
export function setRuntimeClientKind(kind: ClientKind | null): void {
  runtimeClientKind = kind;
}

/** Where a browser keeps the identity it minted for itself. Per origin, so per hub. */
const DEVICE_ID_STORAGE_KEY = 'erplora.device_id';

/** Prefix of a browser-minted identity: legible in a log, obviously not a hub id or a user id. */
const DEVICE_ID_PREFIX = 'dev_';

/** The identity of THIS page load, once resolved. Also the fallback when storage refuses to keep it. */
let browserIdentity: string | null = null;

/** The id this browser wrote down, or `null` if it has none (or cannot read its own storage). */
function storedDeviceId(): string | null {
  try {
    const stored = localStorage.getItem(DEVICE_ID_STORAGE_KEY);
    return stored && stored.trim() ? stored.trim() : null;
  } catch {
    return null; // storage unavailable (site data blocked, sandboxed frame, SSR).
  }
}

/**
 * Mint a fresh identity, or `null` when this browser has no CSPRNG.
 *
 * **`null` rather than something predictable.** `Math.random` would hand out ids an attacker can
 * enumerate, and enumerable ids are exactly what device-trust and the device mode must not key on.
 * A client with no identity is answered `shared` and refused a PIN under enforcement — annoying,
 * and strictly safer than a guessable name.
 *
 * `randomUUID` is only exposed in secure contexts; `getRandomValues` is not, so a hub reached over
 * plain http on a LAN still gets a real random identity instead of none.
 */
function mintDeviceId(): string | null {
  const source = (globalThis as { crypto?: Crypto }).crypto;
  if (typeof source?.randomUUID === 'function') {
    return `${DEVICE_ID_PREFIX}${source.randomUUID().replaceAll('-', '')}`;
  }
  if (typeof source?.getRandomValues === 'function') {
    const bytes = source.getRandomValues(new Uint8Array(16));
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    return `${DEVICE_ID_PREFIX}${hex}`;
  }
  return null;
}

/**
 * The identity **this browser** minted for itself, kept in its site storage. `null` only when the
 * browser cannot produce a random value at all (see {@link mintDeviceId}).
 *
 * What it survives, because it is what the owner is promised: closing the tab, reloading, quitting
 * the browser, installing the PWA. What it does **not** survive: another browser or another OS
 * user (a different profile, a different storage — a different device, correctly), clearing the
 * site data, and a private window ending. A browser whose storage refuses writes keeps the
 * identity for the life of the page — it is then never a *known* device, which is fail-closed.
 *
 * Scoped to the origin, so a browser presents a **different** identity to each hub: nothing here
 * lets one hub correlate a device with another's.
 */
export function browserDeviceId(): string | null {
  if (browserIdentity) return browserIdentity;
  const stored = storedDeviceId();
  if (stored) {
    browserIdentity = stored;
    return stored;
  }
  const minted = mintDeviceId();
  if (!minted) return null;
  try {
    localStorage.setItem(DEVICE_ID_STORAGE_KEY, minted);
  } catch {
    /* cannot be kept: this identity lasts one page load, and the hub never knows it. */
  }
  browserIdentity = minted;
  return minted;
}

interface TauriCore {
  invoke?: (cmd: string, args?: unknown) => Promise<unknown>;
  /** A mobile plugin's event (`@tauri-apps/api/core` → `addPluginListener`), same global. */
  addPluginListener?: (
    plugin: string,
    event: string,
    cb: (payload: unknown) => void,
  ) => Promise<{ unregister: () => Promise<void> }>;
}

/** The event API of the same global (`@tauri-apps/api/event` → `listen`). */
interface TauriEvent {
  listen?: (event: string, handler: (event: unknown) => void) => Promise<() => void>;
}

function tauriGlobal(): { core?: TauriCore; event?: TauriEvent } | null {
  const w = (globalThis as { window?: { __TAURI__?: { core?: TauriCore; event?: TauriEvent } } }).window;
  return w?.__TAURI__ ?? null;
}

function tauriCore(): TauriCore | null {
  // Se llega a `window` a través de `globalThis` a propósito: la referencia pelada LANZA un
  // `ReferenceError` donde no hay DOM (un test en node, un worker), y este es el predicado con el
  // que otros deciden si hay hardware — que reviente en vez de contestar «no» convierte una
  // pregunta en una excepción para todos sus llamadores.
  const g = tauriGlobal();
  return g?.core?.invoke ? g.core : null;
}

/** True when we run inside the Tauri shell. */
export function isTauri(): boolean {
  return tauriCore() !== null;
}

/**
 * Invoke a Tauri command through the `window.__TAURI__` global (no `@tauri-apps/api` dependency).
 * Returns `null` when we are NOT in Tauri (web-pwa) → the caller degrades gracefully.
 * Tauri v2 maps the camelCase keys of the object to the snake_case params of the Rust command.
 */
export async function invokeTauri<T>(cmd: string, args?: Record<string, unknown>): Promise<T | null> {
  const core = tauriCore();
  if (!core?.invoke) return null;
  return (await core.invoke(cmd, args)) as T;
}

/**
 * Listen to an event a PLUGIN of the installed app reports (hub#2305: the tap on a notice is the
 * notification plugin's `actionPerformed`), through the same `window.__TAURI__` global.
 *
 * `null` when there is nothing to listen to — a browser, or a global without plugin listeners. A
 * refused subscription (an app whose capabilities do not grant it) rejects: the caller decides.
 */
export async function listenTauriPlugin(
  plugin: string,
  event: string,
  cb: (payload: unknown) => void,
): Promise<(() => void) | null> {
  const listen = tauriCore()?.addPluginListener;
  if (!listen) return null;
  const listener = await listen(plugin, event, cb);
  return () => {
    void listener.unregister().catch((e) => console.warn('[device] unregister', e));
  };
}

/**
 * Listen to an event the SHELL itself emits (hub#2360: «a tap on a notice is waiting», from a click
 * on the computer), through the same `window.__TAURI__` global. The payload is not handed on: the
 * event only says something is waiting, and what it is is claimed through a command.
 *
 * `null` when there is nothing to listen to — a browser, or a global without the event API. A
 * refused subscription rejects: the caller decides.
 */
export async function listenTauriEvent(event: string, cb: () => void): Promise<(() => void) | null> {
  const listen = tauriCore() ? tauriGlobal()?.event?.listen : undefined;
  if (!listen) return null;
  const unlisten = await listen(event, () => cb());
  return () => unlisten();
}

/** The device identity of the Tauri shell, or `null` in a plain browser. */
export async function getDeviceContext(): Promise<DeviceContext | null> {
  const core = tauriCore();
  if (!core?.invoke) return null;
  try {
    const ctx = (await core.invoke('device_context')) as {
      id?: string;
      client_type?: string;
      platform?: DeviceContext['platform'];
      distribution?: DeviceContext['distribution'];
    };
    if (ctx && typeof ctx.id === 'string' && ctx.id) {
      const clientType = ctx.client_type === 'hub-local' ? 'hub-local' : 'hub-desktop';
      // `distribution` is read from a shell older than hub#757 as `undefined`, never as a guess:
      // callers treat the silence as `direct`, which is what those builds actually are.
      return { id: ctx.id, clientType, platform: ctx.platform, distribution: ctx.distribution };
    }
  } catch {
    /* ignore — degrade to the browser identity */
  }
  return null;
}

/**
 * Which device is asking, with the same resolution the headers use: the **shell** first (its id
 * lives outside the webview and survives a cleanup of the site data), otherwise the identity this
 * **browser** minted for itself.
 *
 * `null` only for a client that can produce neither — the hub then decides whether that is enough
 * (it is not, under device-trust: hub#330).
 */
export async function resolveDeviceId(): Promise<string | null> {
  const native = await getDeviceContext();
  return native?.id ?? browserDeviceId();
}

/**
 * Identification headers for the login **against the Cloud**. In Tauri `X-Client-Type`
 * (desktop/local) + `X-Device-Id` name the installation (§2.9b). In a browser the client type is
 * the one the runtime reported, and the id is the browser's own — a provisioned Cloud machine
 * still says `hub-cloud`, but it no longer says that every browser is the same one.
 */
export async function loginHeaders(): Promise<Record<string, string>> {
  const native = await getDeviceContext();
  if (native) {
    return {
      'X-Client-Type': native.clientType,
      'X-Device-Id': native.id,
      ...(native.platform ? { 'X-Device-Platform': native.platform } : {}),
    };
  }
  if (!runtimeClientKind) return { 'X-Client-Type': 'hub' };
  const id = browserDeviceId();
  return {
    'X-Client-Type': runtimeClientKind.clientType,
    ...(id ? { 'X-Device-Id': id } : {}),
    ...(runtimeClientKind.platform ? { 'X-Device-Platform': runtimeClientKind.platform } : {}),
  };
}
