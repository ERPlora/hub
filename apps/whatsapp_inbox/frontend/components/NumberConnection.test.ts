// «Your number» in Settings (WHATSAPP_INBOX-F01, F02): the number's state; «Connect WhatsApp» (or «Reconnect») when
// erplora.com says Meta's window can be opened from here, with why not otherwise; Meta's window followed until the
// number is connected; «Disconnect», asked first. erplora.com out of reach is said as the old hub said it, with Retry.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { click, flush, mountInbox, settle } from '../__tests__/mount-inbox';
import type { ChannelOut, ChannelPrepareOut } from '../operations';
import NumberConnection from './NumberConnection.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const CHANNEL: ChannelOut = {
  status: 'not_connected',
  phone_number: '',
  display_name: '',
  monthly_limit: 150,
  monthly_usage: 0,
  cap_reached: false,
  synced_at: null,
  manage_url: 'http://localhost:8001',
  plans_url: 'http://localhost:8001/store/plans',
};
const CONNECTED: ChannelOut = { ...CHANNEL, status: 'connected', phone_number: '+34910000000', display_name: 'Peluquería Ana' };
const READY: ChannelPrepareOut = {
  available: true,
  reason: null,
  app_id: '1234567890',
  config_id: '9876543210',
  graph_version: 'v25.0',
  redirect_uri: 'https://erplora.com/whatsapp/return',
};
const PREPARE = '/api/whatsapp_inbox/channel/prepare';
const CONNECT = '/api/whatsapp_inbox/channel/connect';
const DISCONNECT = '/api/whatsapp_inbox/channel/disconnect';

type Answers = Record<string, [number, unknown]>;

async function setup(channel: ChannelOut, answers: Answers = { [PREPARE]: [200, READY] }, locale: 'en' | 'es' = 'en') {
  const api = ({ url }: { url: string }) => {
    const [status, body] = answers[new URL(url, 'http://a.localhost').pathname] ?? [404, { error: { code: 'not_found', message: 'Not found.' } }];
    return Response.json(body, { status });
  };
  const m = await mountInbox(NumberConnection, { path: '/whatsapp_inbox/settings', props: { channel }, locale, api });
  await settle();
  const text = () => m.find('whatsapp-inbox-number').text();
  const paths = () => m.sent().map((call) => call.path);
  return { ...m, text, paths };
}

/** Ionic's buttons take `disabled` as a property, not as an attribute. */
const disabled = (el: Element) => (el as HTMLElement & { disabled?: boolean }).disabled === true;

let opened: string[];
let popup: { closed: boolean; close: () => void };

beforeEach(() => {
  opened = [];
  popup = { closed: false, close: vi.fn() };
  vi.spyOn(window, 'open').mockImplementation((url) => {
    opened.push(String(url));
    return popup as unknown as Window;
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

const meta = (event: string, data: Record<string, unknown>) =>
  window.dispatchEvent(
    new MessageEvent('message', { origin: 'https://www.facebook.com', data: JSON.stringify({ type: 'WA_EMBEDDED_SIGNUP', event, data }) }),
  );
const back = (data: Record<string, unknown>) =>
  window.dispatchEvent(new MessageEvent('message', { origin: 'https://erplora.com', data: { type: 'erplora.whatsapp.signup', ...data } }));

describe('NumberConnection: the number’s state', () => {
  it('connected: the number, its name and «Disconnect»; erplora.com is not asked how to open Meta’s window', async () => {
    const s = await setup(CONNECTED);
    expect(s.text()).toContain('Connected');
    expect(s.text()).toContain('+34910000000');
    expect(s.text()).toContain('Peluquería Ana');
    expect(s.find('whatsapp-inbox-number-disconnect').exists()).toBe(true);
    expect(s.find('whatsapp-inbox-number-connect').exists()).toBe(false);
    expect(s.paths()).toEqual([]);
  });

  it('not connected: asks erplora.com and offers «Connect WhatsApp» with what happens in Meta’s window', async () => {
    const s = await setup(CHANNEL);
    expect(s.paths()).toEqual([PREPARE]);
    expect(s.text()).toContain('Not connected');
    expect(s.find('whatsapp-inbox-number-connect').text()).toBe('Connect WhatsApp');
    expect(s.text()).toContain('scan the code with that phone');
    expect(s.find('whatsapp-inbox-number-disconnect').exists()).toBe(false);
  });

  it('to reconnect: says WhatsApp withdrew the permission, offers «Reconnect» and «Disconnect»', async () => {
    const s = await setup({ ...CONNECTED, status: 'reconnect_needed' });
    expect(s.text()).toContain('WhatsApp withdrew the permission');
    expect(s.find('whatsapp-inbox-number-connect').text()).toBe('Reconnect');
    expect(s.find('whatsapp-inbox-number-disconnect').exists()).toBe(true);
  });

  it('without WhatsApp on erplora.com, or without the window yet, says so and offers nothing to press', async () => {
    const off = await setup(CHANNEL, { [PREPARE]: [200, { ...READY, available: false, reason: 'not_configured' }] });
    expect(off.find('whatsapp-inbox-number-unavailable').text()).toBe('WhatsApp is not available in ERPlora yet.');
    expect(off.find('whatsapp-inbox-number-connect').exists()).toBe(false);
    for (const reason of ['window_unavailable', 'popups_blocked']) {
      const later = await setup(CHANNEL, { [PREPARE]: [200, { ...READY, available: false, reason, redirect_uri: '' }] });
      expect(later.find('whatsapp-inbox-number-unavailable').text()).toBe('Connecting the number from here is not available yet.');
      expect(later.find('whatsapp-inbox-number-connect').exists()).toBe(false);
    }
  });

  it('erplora.com out of reach is said as the old hub said it, and «Retry» asks again', async () => {
    const message = 'Your hub could not reach erplora.com. Check the connection and try again.';
    const s = await setup(CHANNEL, { [PREPARE]: [503, { error: { code: 'whatsapp_inbox.saas_unreachable', message } }] });
    expect(s.find('whatsapp-inbox-number-error').text()).toContain(message);
    expect(s.find('whatsapp-inbox-number-connect').exists()).toBe(false);
    await click(s.find('whatsapp-inbox-number-retry').element);
    expect(s.paths()).toEqual([PREPARE, PREPARE]);
  });

  it('a demo hears that it cannot connect a number', async () => {
    const message = 'erplora.com does not know this business: a demo cannot connect a WhatsApp number.';
    const s = await setup(CHANNEL, { [PREPARE]: [409, { error: { code: 'whatsapp_inbox.hub_unknown', message } }] });
    expect(s.find('whatsapp-inbox-number-error').text()).toContain(message);
  });
});

describe('NumberConnection: Meta’s window (WHATSAPP_INBOX-F01)', () => {
  const finished = { connected: true, phone_number: '+34910000000', display_name: 'Peluquería Ana', history_requested: true };

  it('opens Meta’s window in the click, follows it and connects what it gave', async () => {
    const s = await setup(CHANNEL, { [PREPARE]: [200, READY], [CONNECT]: [200, finished] });
    await click(s.find('whatsapp-inbox-number-connect').element);
    expect(opened).toHaveLength(1);
    const url = new URL(opened[0]);
    expect(`${url.origin}${url.pathname}`).toBe('https://www.facebook.com/v25.0/dialog/oauth');
    expect(s.find('whatsapp-inbox-number-waiting').text()).toBe('Finish in Meta’s window…');
    expect(disabled(s.find('whatsapp-inbox-number-connect').element)).toBe(true);

    meta('FINISH', { waba_id: '102290129340398', phone_number_id: '106540352242922', business_id: '2729063490586005' });
    back({ state: url.searchParams.get('state'), code: 'AQD-one-time' });
    await settle();

    expect(s.sent().at(-1)).toEqual({
      method: 'POST',
      path: CONNECT,
      query: {},
      body: { code: 'AQD-one-time', event: 'FINISH', waba_id: '102290129340398', phone_number_id: '106540352242922', business_id: '2729063490586005' },
    });
    expect(s.find('whatsapp-inbox-number-done').text()).toBe(
      'WhatsApp connected: +34910000000 (Peluquería Ana). Its contacts and chats arrive in the inbox in a few minutes.',
    );
  });

  it('erplora.com refusing the connection says its reason', async () => {
    const message = 'Meta did not accept the connection: This authorization code has expired.';
    const s = await setup(CHANNEL, { [PREPARE]: [200, READY], [CONNECT]: [409, { error: { code: 'whatsapp_inbox.meta_rejected', message } }] });
    await click(s.find('whatsapp-inbox-number-connect').element);
    meta('FINISH', { waba_id: '1', phone_number_id: '2' });
    back({ state: new URL(opened[0]).searchParams.get('state'), code: 'AQD' });
    await settle();
    expect(s.find('whatsapp-inbox-number-failed').text()).toBe(message);
    expect(disabled(s.find('whatsapp-inbox-number-connect').element)).toBe(false);
  });

  it('a window cancelled, refused by Meta or blocked by the browser says so', async () => {
    const cancelled = await setup(CHANNEL);
    await click(cancelled.find('whatsapp-inbox-number-connect').element);
    meta('CANCEL', { current_step: 'PHONE_NUMBER_SETUP' });
    await flush();
    expect(cancelled.find('whatsapp-inbox-number-failed').text()).toBe('Meta’s window was closed before finishing: nothing was connected.');
    cancelled.wrapper.unmount();

    const refused = await setup(CHANNEL);
    await click(refused.find('whatsapp-inbox-number-connect').element);
    meta('CANCEL', { error_message: 'Number already in use' });
    await flush();
    expect(refused.find('whatsapp-inbox-number-failed').text()).toBe('Meta did not finish the connection: Number already in use');
    refused.wrapper.unmount();

    vi.spyOn(window, 'open').mockReturnValue(null);
    const blocked = await setup(CHANNEL);
    await click(blocked.find('whatsapp-inbox-number-connect').element);
    expect(blocked.find('whatsapp-inbox-number-failed').text()).toBe(
      'The browser did not let Meta’s window open. Allow pop-up windows for this site and try again.',
    );
  });
});

describe('NumberConnection: disconnecting (WHATSAPP_INBOX-F02)', () => {
  it('«Disconnect» asks first, saying what stops and what stays, then disconnects', async () => {
    const s = await setup(CONNECTED, { [DISCONNECT]: [200, { disconnected: true }] });
    await click(s.find('whatsapp-inbox-number-disconnect').element);
    const dialog = s.inDoc('whatsapp-inbox-number-disconnect-dialog');
    expect(dialog?.getAttribute('aria-label')).toBe('Disconnect the WhatsApp number?');
    expect(dialog?.textContent).toContain('+34910000000');
    expect(dialog?.textContent).toContain('The conversations kept stay.');
    expect(s.paths()).toEqual([]);
    (s.inDoc('whatsapp-inbox-number-disconnect-dialog-submit') as HTMLElement).click();
    await settle();
    expect(s.sent()).toEqual([{ method: 'POST', path: DISCONNECT, query: {}, body: {} }]);
    expect(s.find('whatsapp-inbox-number-done').text()).toBe('WhatsApp disconnected.');
  });

  it('erplora.com without a number says it, and a refusal stays in the dialog', async () => {
    const none = await setup(CONNECTED, { [DISCONNECT]: [200, { disconnected: false }] });
    await click(none.find('whatsapp-inbox-number-disconnect').element);
    (none.inDoc('whatsapp-inbox-number-disconnect-dialog-submit') as HTMLElement).click();
    await settle();
    expect(none.find('whatsapp-inbox-number-done').text()).toBe('erplora.com had no number connected for this business.');
    none.wrapper.unmount();

    const message = 'Your hub could not reach erplora.com. Check the connection and try again.';
    const away = await setup(CONNECTED, { [DISCONNECT]: [503, { error: { code: 'whatsapp_inbox.saas_unreachable', message } }] });
    await click(away.find('whatsapp-inbox-number-disconnect').element);
    (away.inDoc('whatsapp-inbox-number-disconnect-dialog-submit') as HTMLElement).click();
    await settle();
    expect(away.inDoc('whatsapp-inbox-number-disconnect-dialog')?.textContent).toContain(message);
  });
});

describe('NumberConnection: Spanish', () => {
  it('speaks Spanish', async () => {
    const s = await setup(CHANNEL, { [PREPARE]: [200, READY] }, 'es');
    expect(s.text()).toContain('Sin conectar');
    expect(s.find('whatsapp-inbox-number-connect').text()).toBe('Conectar WhatsApp');
  });
});
