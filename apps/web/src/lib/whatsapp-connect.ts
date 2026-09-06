// «Connect WhatsApp» from the hub (hub#1600, ADR-0452) — the browser half.
//
// The owner presses the button in the WhatsApp module's settings; this loads Meta's JS SDK, opens
// the Embedded Signup popup (the number already in the WhatsApp Business app is connected by
// scanning a QR — «coexistence»), and hands the runtime what Meta returned: the short-lived `code`
// and the ids the popup posts as a `message` event. The runtime, not the page, talks to the SaaS
// with the hub's machine credential; the page carries the hub session and nothing else.
//
// Everything Meta-specific is here, with the window and the document injectable, so the whole
// exchange is testable without a browser (`whatsapp-connect.test.ts`).
import { RUNTIME_URL, runtimeHeaders } from './runtime';

/** The Embedded Signup variant where the customer keeps using the WhatsApp Business app. */
export const BUSINESS_APP_FEATURE = 'whatsapp_business_app_onboarding';
/** The version of Meta's session-info payload that carries `phone_number_id` for that variant. */
export const SESSION_INFO_VERSION = '3';

export interface WhatsAppConnectConfig {
  configured: boolean;
  app_id: string;
  config_id: string;
  graph_version: string;
}

export interface WhatsAppNumber {
  phone_number_id: string;
  display_phone: string;
  is_active: boolean;
  is_on_biz_app?: boolean;
}

/** What the popup handed back: the code plus the ids Meta posted (empty when it posted none). */
export interface EmbeddedSignupResult {
  code: string;
  event: string;
  waba_id: string;
  phone_number_id: string;
  business_id: string;
}

export interface MetaSdk {
  init(options: { appId: string; autoLogAppEvents: boolean; xfbml: boolean; version: string }): void;
  login(callback: (response: { authResponse?: { code?: string } | null }) => void, options: Record<string, unknown>): void;
}

/** A refusal with a `code` the page maps to a sentence (`whatsappConnect.errors.<code>`). */
export class WhatsAppConnectError extends Error {
  readonly code: string;
  readonly status: number;
  constructor(code: string, status: number) {
    super(code);
    this.name = 'WhatsAppConnectError';
    this.code = code;
    this.status = status;
  }
}

const SDK_LOCALES: Record<string, string> = { es: 'es_ES', en: 'en_US' };

/** Meta serves its SDK per locale; anything we do not map falls back to English. */
export function sdkScriptUrl(locale: string): string {
  const base = (locale || 'en').split('-')[0].toLowerCase();
  return `https://connect.facebook.net/${SDK_LOCALES[base] ?? 'en_US'}/sdk.js`;
}

/** Only facebook.com and its subdomains may tell us which number was picked. */
export function isMetaOrigin(origin: string): boolean {
  try {
    const host = new URL(origin).hostname;
    return host === 'facebook.com' || host.endsWith('.facebook.com');
  } catch {
    return false;
  }
}

interface SdkWindow {
  FB?: MetaSdk;
  fbAsyncInit?: () => void;
  __erploraMetaSdk?: Promise<MetaSdk>;
}

interface SdkDocument {
  createElement(tag: string): { src: string; async?: boolean; defer?: boolean; crossOrigin?: string; onerror?: () => void };
  head: { appendChild(node: unknown): unknown };
}

/** Loads Meta's SDK once (per window) and initialises it with OUR app; reused afterwards. */
export function loadMetaSdk(
  options: { appId: string; graphVersion: string; locale: string },
  win: SdkWindow = window as unknown as SdkWindow,
  doc: SdkDocument = document as unknown as SdkDocument,
): Promise<MetaSdk> {
  if (win.FB) return Promise.resolve(win.FB);
  if (win.__erploraMetaSdk) return win.__erploraMetaSdk;
  win.__erploraMetaSdk = new Promise<MetaSdk>((resolve, reject) => {
    win.fbAsyncInit = () => {
      const FB = win.FB;
      if (!FB) {
        reject(new WhatsAppConnectError('sdk_unavailable', 0));
        return;
      }
      FB.init({ appId: options.appId, autoLogAppEvents: true, xfbml: false, version: options.graphVersion });
      resolve(FB);
    };
    const script = doc.createElement('script');
    script.src = sdkScriptUrl(options.locale);
    script.async = true;
    script.defer = true;
    script.crossOrigin = 'anonymous';
    script.onerror = () => {
      win.__erploraMetaSdk = undefined;
      reject(new WhatsAppConnectError('sdk_unavailable', 0));
    };
    doc.head.appendChild(script);
  });
  return win.__erploraMetaSdk;
}

interface MessageWindow {
  addEventListener(type: 'message', listener: (event: { origin: string; data: unknown }) => void): void;
  removeEventListener(type: 'message', listener: (event: { origin: string; data: unknown }) => void): void;
}

/**
 * Opens the popup and resolves with the code plus the ids Meta posted BEFORE the login callback
 * fires. Rejects with `cancelled` when the person closes it (or Meta reports a CANCEL).
 */
export function openEmbeddedSignup(FB: MetaSdk, configId: string, win: MessageWindow = window): Promise<EmbeddedSignupResult> {
  return new Promise((resolve, reject) => {
    const pending = { event: 'FINISH', waba_id: '', phone_number_id: '', business_id: '' };
    const onMessage = (event: { origin: string; data: unknown }) => {
      if (!isMetaOrigin(event.origin)) return;
      let data: { type?: string; event?: string; data?: Record<string, unknown> } | null = null;
      try {
        data = typeof event.data === 'string' ? JSON.parse(event.data) : (event.data as typeof data);
      } catch {
        return;
      }
      if (!data || data.type !== 'WA_EMBEDDED_SIGNUP') return;
      if (data.event === 'CANCEL') {
        pending.event = 'CANCEL';
        return;
      }
      const ids = data.data ?? {};
      pending.event = data.event ?? 'FINISH';
      pending.waba_id = String(ids.waba_id ?? '');
      pending.phone_number_id = String(ids.phone_number_id ?? '');
      pending.business_id = String(ids.business_id ?? '');
    };
    win.addEventListener('message', onMessage);
    const finish = (response: { authResponse?: { code?: string } | null }) => {
      win.removeEventListener('message', onMessage);
      const code = response?.authResponse?.code;
      if (!code || pending.event === 'CANCEL') {
        reject(new WhatsAppConnectError('cancelled', 0));
        return;
      }
      resolve({ code, ...pending });
    };
    try {
      FB.login(finish, {
        config_id: configId,
        response_type: 'code',
        override_default_response_type: true,
        extras: { setup: {}, featureType: BUSINESS_APP_FEATURE, sessionInfoVersion: SESSION_INFO_VERSION },
      });
    } catch {
      win.removeEventListener('message', onMessage);
      reject(new WhatsAppConnectError('sdk_unavailable', 0));
    }
  });
}

async function runtimeCall<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${RUNTIME_URL}${path}`, {
      ...init,
      headers: { ...runtimeHeaders(), ...((init.headers as Record<string, string>) ?? {}) },
      cache: 'no-store',
    });
  } catch {
    throw new WhatsAppConnectError('unreachable', 0);
  }
  let body: Record<string, unknown> = {};
  try {
    body = (await response.json()) as Record<string, unknown>;
  } catch {
    body = {};
  }
  if (!response.ok) {
    throw new WhatsAppConnectError(refusalCode(body, response.status), response.status);
  }
  return body as T;
}

/** A catalogue key, not a sentence: what `whatsappConnect.errors.<code>` can be looked up by. */
const CODE_SHAPE = /^[a-z][a-z0-9_.-]*$/;

/**
 * The code a refusal maps to: `code` first (what the SaaS's view is asked to send next to its
 * prose), then `error.code`, then a bare `error` that IS a code. Prose is never a key — the SaaS's
 * connect view answers with sentences («No phone numbers found…», saas#1886) and the runtime's
 * gate with its own — so it falls back on the status: 401/403 is «not yours», the rest is the
 * generic sentence.
 */
function refusalCode(body: Record<string, unknown>, status: number): string {
  const nested = typeof body.error === 'object' && body.error ? (body.error as { code?: unknown }).code : undefined;
  for (const candidate of [body.code, nested, body.error]) {
    if (typeof candidate === 'string' && CODE_SHAPE.test(candidate)) return candidate;
  }
  return status === 401 || status === 403 ? 'forbidden' : 'default';
}

export function fetchWhatsAppConfig(): Promise<WhatsAppConnectConfig> {
  return runtimeCall<WhatsAppConnectConfig>('/api/hub/whatsapp/config');
}

export async function fetchWhatsAppNumbers(): Promise<WhatsAppNumber[]> {
  const body = await runtimeCall<{ numbers?: WhatsAppNumber[] }>('/api/hub/whatsapp/numbers');
  return body.numbers ?? [];
}

export async function connectWhatsApp(result: EmbeddedSignupResult): Promise<{ phone_number_id: string; display_phone: string; is_on_biz_app?: boolean }> {
  try {
    return await runtimeCall('/api/hub/whatsapp/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(result),
    });
  } catch (error) {
    // The only 404 the SaaS's connect view returns is «no phone numbers in the WhatsApp Business
    // Account» (`whatsapp_connect`, saas#1886): named in prose alone, the page can still name it.
    if (error instanceof WhatsAppConnectError && error.status === 404 && error.code === 'default') {
      throw new WhatsAppConnectError('no_phone_number', 404);
    }
    throw error;
  }
}

export async function disconnectWhatsApp(phoneNumberId: string): Promise<void> {
  await runtimeCall(`/api/hub/whatsapp/disconnect/${encodeURIComponent(phoneNumberId)}`, { method: 'POST' });
}
