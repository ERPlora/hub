import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { accessibleName, errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import type { ApiAction, ApiKeyList, ApiKeyRow } from '../operations/api_keys';
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
  { id: 'invoice', name: 'Invoices', actions: ['read'] },
  { id: 'tax', name: 'Taxes', actions: ['read', 'update'] },
];
/** Who asks may give everything but deleting in the online shop, only reading the taxes, and nothing on the invoices. */
const GRANTABLE: ApiKeyList['grantable'] = {
  '*': ['read', 'create', 'update'],
  cart_checkout: ['read', 'create', 'update'],
  tax: ['read'],
};
const LIST: ApiKeyList = {
  keys: [
    key(),
    key({ id: '0199aaaa-0000-7000-8000-000000000002', name: 'Tienda', scopes: { cart_checkout: ALL }, created_by: '', last_used_at: '2026-10-23T10:00:00Z' }),
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

const submit = () => byTestId('api-key-form-submit') as HTMLButtonElement;
const submitOff = () => submit().hasAttribute('disabled') || submit().getAttribute('disabled') === 'true';

/** The box of `action` on `app` (`'*'`: every app), ticked or unticked. */
async function tick(app: string, action: ApiAction, checked = true): Promise<void> {
  byTestId(`api-key-form-${app}-${action}`)!.dispatchEvent(new CustomEvent('ionChange', { detail: { checked } }));
  await flush();
}

/** «All apps» or «Choose apps». */
async function where(value: 'all' | 'apps'): Promise<void> {
  byTestId('api-key-form-where')!.dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
  await flush();
}

/** The actions the form offers on `app`. */
const offered = (app: string) => ALL.filter((action) => byTestId(`api-key-form-${app}-${action}`) !== null);

async function named(name: string): Promise<void> {
  type(byTestId('api-key-form-name')!, name);
  await flush();
}

async function create(): Promise<void> {
  submit().click();
  await flush();
}

/** The panel with its keys and «New API key» open. */
async function newKeyForm(options: Parameters<typeof mountBase>[1] = {}, list: ApiKeyList = LIST) {
  const m = await open(options);
  await m.result(m.call, 'base.api_key.list', list);
  await m.wrapper.get('[data-testid="api-keys-new"]').trigger('click');
  await flush();
  return m;
}

/** «Create key» on every app, with `actions` ticked. */
async function createOnEveryApp(name: string, actions: readonly ApiAction[]): Promise<void> {
  await named(name);
  await where('all');
  for (const action of actions) await tick('*', action);
  await create();
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

  it('a row per key: name, the start of its token, what it may do, who made it, state, last use and pace', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, 'base.api_key.list', LIST);
    const rows = m.wrapper.findAll('[data-testid="api-keys-row"]');
    expect(rows).toHaveLength(3);
    expect(rows[0].text()).toContain('erpk_live_AbCdEfGh…');
    expect(rows[0].text()).toContain('Solo lectura');
    expect(m.wrapper.text()).toContain('Creada por');
    expect(rows[0].text()).toContain('Olga');
    expect(rows[1].text()).toContain('—');
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

  it('«New API key» on chosen apps: «Create key» only with a name and a box ticked, and each box gives its own action', async () => {
    const m = await newKeyForm({ onApi: () => Response.json({ key: key({ name: 'Tienda' }), token: TOKEN }) });
    expect(submitOff()).toBe(true);
    await named('Tienda');
    expect(submitOff()).toBe(true);
    await tick('cart_checkout', 'create');
    await tick('cart_checkout', 'read');
    await tick('tax', 'read');
    expect(submitOff()).toBe(false);
    await tick('tax', 'read', false);
    await create();
    expect(posted(m)).toEqual([['/api/keys', { name: 'Tienda', rate_per_minute: 60, scopes: { cart_checkout: ['read', 'create'] } }]]);
  });

  it('a box is there only for what who asks may give, and an app they may give nothing on is not listed', async () => {
    await newKeyForm();
    expect(offered('cart_checkout')).toEqual(['read', 'create', 'update']);
    expect(offered('tax')).toEqual(['read']);
    expect([...document.querySelectorAll('[data-testid="api-key-form-apps"] tbody th')].map((th) => th.textContent?.trim())).toEqual([
      'Online shop',
      'Taxes',
    ]);
  });

  it('the boxes say their app and their action to a screen reader, under «Leer», «Crear», «Modificar» and «Borrar»', async () => {
    await newKeyForm({ locale: 'es' });
    const heads = [...document.querySelectorAll('[data-testid="api-key-form-apps"] thead th')].map((th) => th.textContent?.trim());
    expect(heads).toEqual(['App', 'Leer', 'Crear', 'Modificar', 'Borrar']);
    expect(byTestId('api-key-form-cart_checkout-update')?.getAttribute('aria-label')).toBe('Online shop · Modificar');
    await where('all');
    expect(byTestId('api-key-form-*-read')?.getAttribute('aria-label')).toBe('Todas las apps · Leer');
  });

  it('«All apps»: the same boxes once, for every app, also the ones added later', async () => {
    const m = await newKeyForm({ onApi: () => Response.json({ key: key(), token: TOKEN }) });
    await named('Gestoría');
    await tick('cart_checkout', 'update');
    await where('all');
    expect(byTestId('api-key-form')?.textContent).toContain('also the ones you add later');
    expect([offered('*'), offered('cart_checkout')]).toEqual([['read', 'create', 'update'], []]);
    expect(submitOff()).toBe(true);
    await tick('*', 'create');
    await tick('*', 'read');
    await create();
    expect(posted(m)).toEqual([['/api/keys', { name: 'Gestoría', rate_per_minute: 60, scopes: { '*': ['read', 'create'] } }]]);
  });

  it('back on «Choose apps», what was ticked there is kept and what was ticked on every app is not given', async () => {
    const m = await newKeyForm({ onApi: () => Response.json({ key: key(), token: TOKEN }) });
    await named('Tienda');
    await tick('tax', 'read');
    await where('all');
    await tick('*', 'update');
    await where('apps');
    await create();
    expect(posted(m)).toEqual([['/api/keys', { name: 'Tienda', rate_per_minute: 60, scopes: { tax: ['read'] } }]]);
  });

  it('who may give nothing on every app chooses among the apps, with no «All apps»', async () => {
    await newKeyForm({}, { ...LIST, grantable: { tax: ['read'] } });
    expect(byTestId('api-key-form-where')).toBeNull();
    expect(offered('tax')).toEqual(['read']);
  });

  it('who may give nothing on any app is told so', async () => {
    await newKeyForm({ locale: 'es' }, { ...LIST, grantable: {} });
    await named('Tienda');
    expect(byTestId('api-key-form-apps')?.textContent).toContain('No hay ninguna app a la que puedas dar acceso.');
    expect(submitOff()).toBe(true);
  });

  it('what who asks may no longer give, while the form is open, is neither offered nor given', async () => {
    const m = await newKeyForm({ onApi: () => Response.json({ key: key(), token: TOKEN }) });
    await named('Tienda');
    await tick('cart_checkout', 'create');
    await tick('cart_checkout', 'read');
    await m.result(m.call, 'base.api_key.list', { ...LIST, grantable: { tax: ['read'] } });
    expect(submitOff()).toBe(true);
    await m.result(m.call, 'base.api_key.list', { ...LIST, grantable: { cart_checkout: ['read'] } });
    expect(offered('cart_checkout')).toEqual(['read']);
    await create();
    expect(posted(m)).toEqual([['/api/keys', { name: 'Tienda', rate_per_minute: 60, scopes: { cart_checkout: ['read'] } }]]);
  });

  it('more than who asks may do is refused in words', async () => {
    const reason = 'Una key no puede hacer más de lo que puedes hacer tú.';
    await newKeyForm({
      locale: 'es',
      onApi: () => Response.json({ error: { code: 'base.api_key_beyond_maker', message: reason, fields: { scopes: reason } } }, { status: 403 }),
    });
    await createOnEveryApp('Gestoría', ['read']);
    expect(byTestId('api-key-form-error')?.textContent?.trim()).toBe(reason);
  });

  it('the token once, with «Copy» that says «Copied» for two seconds', async () => {
    await newKeyForm({ onApi: () => Response.json({ key: key(), token: TOKEN }) });
    await createOnEveryApp('Gestoría', ['read']);
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
    await newKeyForm({
      onApi: () => Response.json({ error: { code: 'base.api_key_scope_unknown', message: reason, fields: { scopes: reason } } }, { status: 422 }),
    });
    await named('Tienda');
    await tick('cart_checkout', 'read');
    await create();
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
  it('as opened closes; a name, a box ticked or «All apps» asks; restored as opened closes again', async () => {
    await newKeyForm();
    const { expectUnsavedFormAsksBeforeClosing } = await import('../__tests__/unsaved-form');
    const overlay = () => byTestId('api-key-form');
    await expectUnsavedFormAsksBeforeClosing({ overlay, change: () => named('Tienda'), restore: () => named('') });
    await expectUnsavedFormAsksBeforeClosing({
      overlay,
      change: () => tick('cart_checkout', 'read'),
      restore: () => tick('cart_checkout', 'read', false),
    });
    await expectUnsavedFormAsksBeforeClosing({ overlay, change: () => where('all'), restore: () => where('apps') });
  });
});
