// Employees › API keys (BASE-G146…G149, G03, G05; the old hub's ApiKeysPanel): the live `base.api_key.list` — each key
// with the start of its token, what it may do, its state, when it was made and last used and its pace —, «New API
// key» (name, pace, what it may do: all, read, write or per app with the apps that publish their API), its token shown
// once with «Copy», «Rotate» and «Revoke» (both asked first, with their consequence). A business that cannot have keys
// yet is told so; a list that cannot be read is never «no keys».
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import type { ApiKeyList, ApiKeyRow } from '../operations';
import ApiKeysPanel from './ApiKeysPanel.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));
vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const TOKEN = 'erpk_live_AbCdEfGh0123456789abcdefghijklmnopqrstuvwxy';

function key(fields: Partial<ApiKeyRow> = {}): ApiKeyRow {
  return {
    id: '0199aaaa-0000-7000-8000-000000000001',
    name: 'Gestoría',
    prefix: 'erpk_live_AbCdEfGh',
    mode: 'read',
    scopes: {},
    rate_per_minute: 60,
    created_by: 'Olga',
    created_at: '2026-10-20T09:00:00Z',
    rotated_at: null,
    last_used_at: null,
    revoked_at: null,
    ...fields,
  };
}

const APPS = [
  { id: 'cart_checkout', name: 'Online shop', read: true, write: true },
  { id: 'tax', name: 'Taxes', read: true, write: true },
];
const LIST: ApiKeyList = {
  available: true,
  keys: [
    key(),
    key({ id: '0199aaaa-0000-7000-8000-000000000002', name: 'Tienda', mode: 'per_app', scopes: { cart_checkout: ['read', 'write'] }, last_used_at: '2026-10-23T10:00:00Z' }),
    key({ id: '0199aaaa-0000-7000-8000-000000000003', name: 'Vieja', mode: 'full', revoked_at: '2026-10-22T10:00:00Z' }),
  ],
  apps: APPS,
};

/** What the panel posted: [path, body]. */
function posted(m: { net: { api: { url: string; init: RequestInit }[] } }) {
  return m.net.api.map((call) => [new URL(call.url, 'http://a.localhost').pathname, JSON.parse(String(call.init.body))]);
}

function type(field: Element, value: string) {
  field.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
}

async function open(options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(ApiKeysPanel, { path: '/employees#apikeys', routes: ['/employees'], ...options });
  const call = await m.live();
  return { ...m, call };
}

const byTestId = (id: string) => document.querySelector(`[data-testid="${id}"]`) as HTMLElement | null;

beforeEach(() => {
  Object.defineProperty(navigator, 'clipboard', { value: { writeText: vi.fn(() => Promise.resolve()) }, configurable: true });
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = '';
});

describe('ApiKeysPanel', () => {
  it('follows the keys live', async () => {
    const m = await open();
    expect(m.client.stream.subscriptions('base.api_key.list').map((sub) => sub.params)).toEqual([{}]);
  });

  it('a row per key: name, the start of its token, what it may do, state, last use and pace', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, 'base.api_key.list', LIST);
    const rows = m.wrapper.findAll('[data-testid="api-keys-row"]');
    expect(rows).toHaveLength(3);
    expect(rows[0].text()).toContain('erpk_live_AbCdEfGh…');
    expect(rows[0].text()).toContain('Solo lectura');
    expect(rows[0].text()).toContain('Activa');
    expect(rows[0].text()).toContain('Nunca');
    expect(rows[0].text()).toContain('60/min');
    expect(rows[1].find('[data-testid="api-keys-scopes"]').text()).toBe('Online shop L/E');
    expect(rows[2].text()).toContain('Revocada');
  });

  it('a revoked key is neither rotated nor revoked again', async () => {
    const m = await open();
    await m.result(m.call, 'base.api_key.list', LIST);
    expect(m.wrapper.find('[data-testid="api-keys-row-0199aaaa-0000-7000-8000-000000000003-rotate"]').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="api-keys-row-0199aaaa-0000-7000-8000-000000000003-revoke"]').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="api-keys-row-0199aaaa-0000-7000-8000-000000000001-revoke"]').exists()).toBe(true);
  });

  it('none yet is said, with what a key is for', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, 'base.api_key.list', { available: true, keys: [], apps: APPS });
    expect(m.wrapper.text()).toContain('Aún no hay API keys. Crea una para que un sistema externo pueda leer o escribir datos de tu negocio.');
  });

  it('a business that cannot have keys yet is told so, with nothing to create', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, 'base.api_key.list', { available: false, keys: [], apps: APPS });
    expect(m.wrapper.get('[data-testid="api-keys-unavailable"]').text()).toContain('Las API keys todavía no están disponibles en este negocio.');
    expect(m.wrapper.find('[data-testid="api-keys-new"]').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="api-keys-row"]').exists()).toBe(false);
  });

  it('a list that cannot be read says so with «Retry», never «no keys»', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, 'base.api_key.list'), 'server_error'));
    await flush();
    expect(m.wrapper.text()).toContain('Your API keys could not be loaded.');
    expect(m.wrapper.text()).not.toContain('No API keys yet');
  });

  it('«New API key» per app: the apps that publish their API, «Create key» only with a name and a box ticked', async () => {
    const m = await open({ onApi: () => Response.json({ key: key({ name: 'Tienda' }), token: TOKEN }) });
    await m.result(m.call, 'base.api_key.list', LIST);
    await m.wrapper.get('[data-testid="api-keys-new"]').trigger('click');
    await flush();
    const submit = () => byTestId('api-key-form-submit') as HTMLButtonElement;
    expect(byTestId('api-key-form-apps')?.textContent).toContain('Online shop');
    expect(submit().hasAttribute('disabled') || submit().getAttribute('disabled') === 'true').toBe(true);
    type(byTestId('api-key-form-name')!, 'Tienda');
    await flush();
    (byTestId('api-key-form-cart_checkout-read') as HTMLElement).dispatchEvent(new CustomEvent('ionChange', { detail: { checked: true } }));
    await flush();
    submit().click();
    await flush();
    expect(posted(m)).toEqual([
      ['/api/keys', { name: 'Tienda', rate_per_minute: 60, mode: 'per_app', scopes: { cart_checkout: ['read'] } }],
    ]);
  });

  it('the token once, with «Copy» that says «Copied» for two seconds', async () => {
    const m = await open({ onApi: () => Response.json({ key: key(), token: TOKEN }) });
    await m.result(m.call, 'base.api_key.list', LIST);
    await m.wrapper.get('[data-testid="api-keys-new"]').trigger('click');
    await flush();
    type(byTestId('api-key-form-name')!, 'Gestoría');
    (byTestId('api-key-form-mode-read') as HTMLElement).click();
    await flush();
    (byTestId('api-key-form-submit') as HTMLButtonElement).click();
    await flush();
    expect(byTestId('api-key-token-value')?.textContent).toBe(TOKEN);
    expect(document.body.textContent).toContain('This is the only time the whole secret is shown.');
    // Fake timers only from here: `flush` waits on real zero-delay timeouts.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    (byTestId('api-key-token-copy') as HTMLElement).click();
    await vi.advanceTimersByTimeAsync(0);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(TOKEN);
    expect(byTestId('api-key-token-copy')?.textContent).toContain('Copied');
    await vi.advanceTimersByTimeAsync(2000);
    expect(byTestId('api-key-token-copy')?.textContent).toContain('Copy');
  });

  it('«Rotate» asks first, then shows the new token', async () => {
    const m = await open({ onApi: () => Response.json({ key: key(), token: TOKEN }) });
    await m.result(m.call, 'base.api_key.list', LIST);
    await m.wrapper.get('[data-testid="api-keys-row-0199aaaa-0000-7000-8000-000000000001-rotate"]').trigger('click');
    await flush();
    expect(document.body.textContent).toContain('The current one stops working at once.');
    expect(posted(m)).toEqual([]);
    (byTestId('api-key-rotate-submit') as HTMLElement).click();
    await flush();
    expect(posted(m)).toEqual([['/api/keys/rotate', { id: '0199aaaa-0000-7000-8000-000000000001' }]]);
    expect(byTestId('api-key-token-value')?.textContent).toBe(TOKEN);
  });

  it('«Revoke» asks first, with its consequence', async () => {
    const m = await open({ locale: 'es', onApi: () => Response.json({ key: key({ revoked_at: '2026-10-24T10:00:00Z' }) }) });
    await m.result(m.call, 'base.api_key.list', LIST);
    await m.wrapper.get('[data-testid="api-keys-row-0199aaaa-0000-7000-8000-000000000001-revoke"]').trigger('click');
    await flush();
    expect(document.body.textContent).toContain('Vas a revocar «Gestoría». Cualquier sistema que use este token dejará de tener acceso de inmediato.');
    (byTestId('api-key-revoke-submit') as HTMLElement).click();
    await flush();
    expect(posted(m)).toEqual([['/api/keys/revoke', { id: '0199aaaa-0000-7000-8000-000000000001' }]]);
  });

  it('a refusal is told from its code', async () => {
    const m = await open({
      onApi: () => Response.json({ error: { code: 'base.api_key_revoked', message: 'server words' } }, { status: 409 }),
    });
    await m.result(m.call, 'base.api_key.list', LIST);
    await m.wrapper.get('[data-testid="api-keys-row-0199aaaa-0000-7000-8000-000000000001-revoke"]').trigger('click');
    await flush();
    (byTestId('api-key-revoke-submit') as HTMLElement).click();
    await flush();
    expect(document.body.textContent).toContain('That key was revoked: it never works again.');
  });
});
