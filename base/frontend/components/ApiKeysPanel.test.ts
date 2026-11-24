import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { accessibleName, errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import type { ApiKeyList, ApiKeyRow } from '../operations/api_keys';
import ApiKeysPanel from './ApiKeysPanel.vue';

// Shaped like a real token (`erpk_live_` + URL-safe base64) without looking like a leaked one to the secrets hook.
const TOKEN = 'erpk_live_test-token-shown-once_0123456789-abcdefghij';

function key(fields: Partial<ApiKeyRow> = {}): ApiKeyRow {
  return {
    id: '0199aaaa-0000-7000-8000-000000000001',
    name: 'Gestoría',
    prefix: 'erpk_live_AbCdEfGh',
    scopes: { '*': ['read'] },
    rate_per_minute: 60,
    created_by: 'Olga',
    created_at: '2026-10-20T09:00:00Z',
    rotated_at: null,
    last_used_at: null,
    revoked_at: null,
    ...fields,
  };
}

const ALL = ['read', 'create', 'update', 'delete'] as const;
const APPS: ApiKeyList['apps'] = [
  { id: 'cart_checkout', name: 'Online shop', actions: [...ALL] },
  { id: 'tax', name: 'Taxes', actions: ['read', 'update'] },
];
/** Who asks may give everything but deleting in the online shop, and only reading the taxes. */
const GRANTABLE = { '*': ['read', 'create', 'update'], cart_checkout: ['read', 'create', 'update'], tax: ['read'] } as const;
const LIST: ApiKeyList = {
  keys: [
    key(),
    key({ id: '0199aaaa-0000-7000-8000-000000000002', name: 'Tienda', scopes: { cart_checkout: ALL }, last_used_at: '2026-10-23T10:00:00Z' }),
    key({ id: '0199aaaa-0000-7000-8000-000000000003', name: 'Vieja', scopes: { '*': ALL }, revoked_at: '2026-10-22T10:00:00Z' }),
  ],
  apps: APPS,
  grantable: GRANTABLE,
};

/** What the panel posted: [path, body]. */
function posted(m: { net: { api: { url: string; init: RequestInit }[] } }) {
  return m.net.api.map((call) => [new URL(call.url, 'http://a.localhost').pathname, JSON.parse(String(call.init.body))]);
}

function type(field: Element, value: string) {
  field.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
}

async function open(options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(ApiKeysPanel, { path: '/employees#apikeys', routes: ['/employees', '/api-docs'], ...options });
  const call = await m.live();
  return { ...m, call };
}

const byTestId = (id: string) => document.querySelector(`[data-testid="${id}"]`) as HTMLElement | null;

/** The least «Create key» takes: a name and a box ticked. */
async function nameAndTick(): Promise<void> {
  type(byTestId('api-key-form-name')!, 'Tienda');
  await flush();
  (byTestId('api-key-form-cart_checkout-read') as HTMLElement).dispatchEvent(new CustomEvent('ionChange', { detail: { checked: true } }));
  await flush();
}

/** The panel with its keys and «New API key» open. */
async function newKeyForm(options: Parameters<typeof mountBase>[1] = {}) {
  const m = await open(options);
  await m.result(m.call, 'base.api_key.list', LIST);
  await m.wrapper.get('[data-testid="api-keys-new"]').trigger('click');
  await flush();
  return m;
}

/** «Create key» named `name`, with a general mode. */
async function createInMode(name: string, mode: 'full' | 'read' | 'write'): Promise<void> {
  type(byTestId('api-key-form-name')!, name);
  (byTestId(`api-key-form-mode-${mode}`) as HTMLElement).click();
  await flush();
  (byTestId('api-key-form-submit') as HTMLButtonElement).click();
  await flush();
}

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
    expect(rows[1].find('[data-testid="api-keys-scopes"]').text()).toBe('Online shop L/C/M/B');
    expect(rows[2].text()).toContain('Revocada');
    expect(rows[2].text()).toContain('Acceso total');
  });

  it('a key that is no general mode says its actions on every app and app by app', async () => {
    const m = await open({ locale: 'es' });
    const keys = [key({ scopes: { '*': ['read', 'create'], tax: ['update'] } })];
    await m.result(m.call, 'base.api_key.list', { ...LIST, keys });
    expect(m.wrapper.get('[data-testid="api-keys-scopes"]').text()).toBe('Todas las apps L/C · Taxes M');
  });

  it('each key’s buttons tell a screen reader which key they are for, their short words first', async () => {
    const m = await open();
    await m.result(m.call, 'base.api_key.list', LIST);
    const named = (n: string, action: string) => accessibleName(m.wrapper.get(`[data-testid="api-keys-row-0199aaaa-0000-7000-8000-00000000000${n}-${action}"]`).element);
    expect([named('1', 'rotate'), named('1', 'revoke'), named('2', 'revoke')]).toEqual(['Rotate: Gestoría', 'Revoke: Gestoría', 'Revoke: Tienda']);
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
    await m.result(m.call, 'base.api_key.list', { ...LIST, keys: [] });
    expect(m.wrapper.text()).toContain('Aún no hay API keys. Crea una para que un sistema externo pueda leer o escribir datos de tu negocio.');
  });

  it('leads to the API’s documentation and offers a new key, with keys or with none yet', async () => {
    for (const keys of [LIST.keys, []]) {
      const m = await open();
      await m.result(m.call, 'base.api_key.list', { ...LIST, keys });
      expect(m.wrapper.get('[data-testid="api-keys-docs"]').attributes('href'), String(keys.length)).toBe('/api-docs');
      expect(m.wrapper.find('[data-testid="api-keys-new"]').exists(), String(keys.length)).toBe(true);
      m.wrapper.unmount();
    }
  });

  it('a list that cannot be read says so with «Retry», never «no keys»', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, 'base.api_key.list'), 'server_error'));
    await flush();
    expect(m.wrapper.text()).toContain('Your API keys could not be loaded.');
    expect(m.wrapper.text()).not.toContain('No API keys yet');
  });

  it('«New API key» per app: the apps that publish their API, «Create key» only with a name and a box ticked', async () => {
    const m = await newKeyForm({ onApi: () => Response.json({ key: key({ name: 'Tienda' }), token: TOKEN }) });
    const submit = () => byTestId('api-key-form-submit') as HTMLButtonElement;
    expect(byTestId('api-key-form-apps')?.textContent).toContain('Online shop');
    expect(submit().hasAttribute('disabled') || submit().getAttribute('disabled') === 'true').toBe(true);
    await nameAndTick();
    submit().click();
    await flush();
    expect(posted(m)).toEqual([
      ['/api/keys', { name: 'Tienda', rate_per_minute: 60, scopes: { cart_checkout: ['read'] } }],
    ]);
  });

  it('per app, «Write» gives the creating, changing and deleting who asks may give there', async () => {
    const m = await newKeyForm({ onApi: () => Response.json({ key: key({ name: 'Tienda' }), token: TOKEN }) });
    type(byTestId('api-key-form-name')!, 'Tienda');
    (byTestId('api-key-form-cart_checkout-write') as HTMLElement).dispatchEvent(new CustomEvent('ionChange', { detail: { checked: true } }));
    await flush();
    (byTestId('api-key-form-submit') as HTMLButtonElement).click();
    await flush();
    expect(posted(m)).toEqual([['/api/keys', { name: 'Tienda', rate_per_minute: 60, scopes: { cart_checkout: ['create', 'update'] } }]]);
  });

  it('a box is there only for what who asks may give on that app', async () => {
    await newKeyForm();
    expect([byTestId('api-key-form-tax-read'), byTestId('api-key-form-tax-write')].map(Boolean)).toEqual([true, false]);
  });

  it('a general mode is given on every app', async () => {
    const m = await newKeyForm({ onApi: () => Response.json({ key: key(), token: TOKEN }) });
    await createInMode('Gestoría', 'write');
    expect(posted(m)).toEqual([['/api/keys', { name: 'Gestoría', rate_per_minute: 60, scopes: { '*': ['create', 'update', 'delete'] } }]]);
  });

  it('more than who asks may do is refused in words', async () => {
    const reason = 'Una key no puede hacer más de lo que puedes hacer tú.';
    await newKeyForm({
      locale: 'es',
      onApi: () => Response.json({ error: { code: 'base.api_key_beyond_maker', message: reason, fields: { scopes: reason } } }, { status: 403 }),
    });
    await createInMode('Gestoría', 'full');
    expect(byTestId('api-key-form-error')?.textContent?.trim()).toBe(reason);
  });

  it('the token once, with «Copy» that says «Copied» for two seconds', async () => {
    await newKeyForm({ onApi: () => Response.json({ key: key(), token: TOKEN }) });
    await createInMode('Gestoría', 'read');
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

  it('a refused field the form does not mark is said once, in words (hub#833)', async () => {
    const reason = 'That app does not publish what the key would do on it.';
    const m = await open({
      onApi: () => Response.json({ error: { code: 'base.api_key_scope_unknown', message: reason, fields: { scopes: reason } } }, { status: 422 }),
    });
    await m.result(m.call, 'base.api_key.list', LIST);
    await m.wrapper.get('[data-testid="api-keys-new"]').trigger('click');
    await flush();
    await nameAndTick();
    (byTestId('api-key-form-submit') as HTMLButtonElement).click();
    await flush();
    expect(byTestId('api-key-form-error')?.textContent?.trim()).toBe(reason);
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

describe('ApiKeysPanel: Android Back with unsaved changes in «New API key» (hub#1020, BASE-F05, BASE-F86)', () => {
  it('as opened closes; a name or a box ticked asks; restored as opened closes again', async () => {
    const m = await open();
    await m.result(m.call, 'base.api_key.list', LIST);
    await m.wrapper.get('[data-testid="api-keys-new"]').trigger('click');
    await flush();
    const { expectUnsavedFormAsksBeforeClosing } = await import('../__tests__/unsaved-form');
    const tickRead = async (checked: boolean) => {
      (byTestId('api-key-form-cart_checkout-read') as HTMLElement).dispatchEvent(new CustomEvent('ionChange', { detail: { checked } }));
      await flush();
    };
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => byTestId('api-key-form'),
      change: async () => {
        type(byTestId('api-key-form-name')!, 'Tienda');
        await flush();
      },
      restore: async () => {
        type(byTestId('api-key-form-name')!, '');
        await flush();
      },
    });
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => byTestId('api-key-form'),
      change: () => tickRead(true),
      restore: () => tickRead(false),
    });
  });
});
