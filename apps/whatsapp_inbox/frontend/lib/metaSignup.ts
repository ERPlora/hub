// Meta's window (WhatsApp Embedded Signup) opened without Facebook's SDK, which the Hub's CSP never loads
// (WHATSAPP_INBOX-F01; WORKBOOK «Contrato con el SaaS», doors 10 and 11). The window is Facebook Login for Business
// with erplora.com's Embedded Signup configuration: while it runs, Meta posts to this page the account and the number
// chosen («session», from facebook.com); when it ends, Meta sends the browser to erplora.com's return page with the
// one-time code, and that page posts it back here («return», from erplora.com's origin, with this attempt's state).
// Both, as they came, are what door 11 connects.

/** What door 10 gave to open the window with (`whatsapp_inbox.channel.prepare`). */
export interface SignupOptions {
  app_id: string;
  config_id: string;
  graph_version: string;
  redirect_uri: string;
}

/** How the window finished, as Meta posted it. */
export type Session =
  | { finished: true; event: string; waba_id: string; phone_number_id: string; business_id: string }
  | { finished: false; event: string; error: string };

/** What erplora.com's return page brought back: the code, or Meta's reason for not giving one. */
export interface Return {
  code: string;
  error: string;
}

/** The type of the message erplora.com's return page posts to the window that opened Meta's. */
export const RETURN_TYPE = 'erplora.whatsapp.signup';
const SESSION_TYPE = 'WA_EMBEDDED_SIGNUP';
const META_ID = /^\d{1,50}$/;
const META_ID_OR_EMPTY = /^\d{0,50}$/;

export function dialogUrl(options: SignupOptions, state: string): string {
  const url = new URL(`https://www.facebook.com/${options.graph_version}/dialog/oauth`);
  const params = {
    client_id: options.app_id,
    config_id: options.config_id,
    response_type: 'code',
    override_default_response_type: 'true',
    redirect_uri: options.redirect_uri,
    state,
    display: 'popup',
    // Embedded Signup v4: what the window offers comes from the configuration, not from here.
    extras: JSON.stringify({ setup: {} }),
  };
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  return url.toString();
}

/** `<the business>.<32 hex>`: erplora.com's return page answers only the business it names, and this page only
 *  the attempt it opened. */
export function newState(hostname: string): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  const secret = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  return `${hostname.split('.')[0]}.${secret}`;
}

function fromFacebook(origin: string): boolean {
  try {
    const { protocol, hostname } = new URL(origin);
    return protocol === 'https:' && (hostname === 'facebook.com' || hostname.endsWith('.facebook.com'));
  } catch {
    return false;
  }
}

const text = (value: unknown): string => (typeof value === 'string' ? value : '');

export function readSession(event: MessageEvent): Session | null {
  if (!fromFacebook(event.origin) || typeof event.data !== 'string') return null;
  let message: unknown;
  try {
    message = JSON.parse(event.data);
  } catch {
    return null;
  }
  if (!message || typeof message !== 'object') return null;
  const { type, event: how, data } = message as { type?: unknown; event?: unknown; data?: unknown };
  if (type !== SESSION_TYPE || typeof how !== 'string') return null;
  const fields = (data && typeof data === 'object' ? data : {}) as Record<string, unknown>;
  if (!how.startsWith('FINISH')) return { finished: false, event: how, error: text(fields.error_message) };
  const [waba, number, business] = [text(fields.waba_id), text(fields.phone_number_id), text(fields.business_id)];
  if (!META_ID.test(waba) || !META_ID_OR_EMPTY.test(number) || !META_ID_OR_EMPTY.test(business)) return null;
  return { finished: true, event: how, waba_id: waba, phone_number_id: number, business_id: business };
}

export function readReturn(event: MessageEvent, options: SignupOptions, state: string): Return | null {
  if (event.origin !== new URL(options.redirect_uri).origin) return null;
  const message = event.data as Record<string, unknown> | null;
  if (!message || typeof message !== 'object' || message.type !== RETURN_TYPE || message.state !== state) return null;
  const code = text(message.code);
  const error = text(message.error_description) || text(message.error);
  if (!code && !error) return null;
  return { code, error: code ? '' : error };
}
