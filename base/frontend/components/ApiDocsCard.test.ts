// «API documentation» in Settings › General (BASE-G100; the old hub's HUB_SHELL-F161): «Show the API documentation»,
// off by default and saved at once (live `base.api_doc.settings`); on, «Open the API documentation». Whoever does not
// run the business sees it disabled and why; a change that cannot be saved says so and the switch shows the saved value.
import { afterEach, describe, expect, it } from 'vitest';

import { EMPLOYEE, errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import ApiDocsCard from './ApiDocsCard.vue';

async function open(options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(ApiDocsCard, { path: '/settings', routes: ['/settings', '/api-docs'], ...options });
  const call = await m.live();
  return { ...m, call };
}

const toggle = (m: { wrapper: { get: (s: string) => { element: Element } } }) =>
  m.wrapper.get('[data-testid="api-docs-toggle"]').element as HTMLElement & { checked: boolean; disabled: boolean };

function posted(m: { net: { api: { url: string; init: RequestInit }[] } }) {
  return m.net.api.map((call) => [new URL(call.url, 'http://a.localhost').pathname, JSON.parse(String(call.init.body))]);
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('ApiDocsCard', () => {
  it('follows the setting live, off by default, in the person’s language', async () => {
    const m = await open({ locale: 'es' });
    expect(m.client.stream.subscriptions('base.api_doc.settings').map((sub) => sub.params)).toEqual([{}]);
    await m.result(m.call, 'base.api_doc.settings', { docs_enabled: false, can_change: true });
    expect(m.wrapper.text()).toContain('Mostrar documentación de la API');
    expect(toggle(m).checked).toBe(false);
    expect(m.wrapper.find('[data-testid="api-docs-open"]').exists()).toBe(false);
  });

  it('turning it on saves it at once; on, it opens the documentation', async () => {
    const m = await open({ onApi: () => Response.json({ docs_enabled: true, can_change: true }) });
    await m.result(m.call, 'base.api_doc.settings', { docs_enabled: false, can_change: true });
    toggle(m).dispatchEvent(new CustomEvent('ionChange', { detail: { checked: true } }));
    await flush();
    expect(posted(m)).toEqual([['/api/api-docs/settings/update', { docs_enabled: true }]]);
    await m.result(m.call, 'base.api_doc.settings', { docs_enabled: true, can_change: true }, 2);
    expect(m.wrapper.get('[data-testid="api-docs-open"]').attributes('href')).toBe('/api-docs');
  });

  it('whoever does not run the business sees it disabled, and why', async () => {
    const m = await open({ session: EMPLOYEE });
    await m.result(m.call, 'base.api_doc.settings', { docs_enabled: true, can_change: false });
    expect(toggle(m).disabled).toBe(true);
    expect(m.wrapper.text()).toContain('Only who runs the business can change it.');
  });

  it('a change that cannot be saved says so and keeps the saved value', async () => {
    const m = await open({ onApi: () => Response.json({ error: { code: 'internal_error', message: 'x' } }, { status: 500 }) });
    await m.result(m.call, 'base.api_doc.settings', { docs_enabled: false, can_change: true });
    toggle(m).dispatchEvent(new CustomEvent('ionChange', { detail: { checked: true } }));
    await flush();
    expect(m.wrapper.text()).toContain('Could not save the change.');
    expect(toggle(m).checked).toBe(false);
  });

  it('a setting that cannot be read says so with «Retry»', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, 'base.api_doc.settings'), 'internal_error'));
    await flush();
    expect(m.wrapper.text()).toContain('Could not load the setting.');
    expect(m.wrapper.find('[data-testid="api-docs-retry"]').exists()).toBe(true);
  });
});
