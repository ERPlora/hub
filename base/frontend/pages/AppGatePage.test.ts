import type { SessionMe } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';
import { defineComponent } from 'vue';

import { EMPLOYEE, flush, mountBase } from '../__tests__/mount-base';
import AppGatePage from './AppGatePage.vue';

const SCREEN = defineComponent({ template: '<div />' });

/** Taxes' rules are locked to this person; Stock is off for the whole business. */
const LOCKED: SessionMe = {
  ...EMPLOYEE,
  apps: [{ label: 'stock', state: 'off' }],
  locked: { tax: ['/tax/rules'] },
};

async function open(path: string, session: SessionMe = LOCKED) {
  const m = await mountBase(AppGatePage, { path: '/', session });
  // The apps' own routes, which the page resolves the address against to know whose screen it is.
  m.router.addRoute({ path: '/tax/rules', component: SCREEN, meta: { auth: true, app: 'tax' } });
  m.router.addRoute({ path: '/stock/items', component: SCREEN, meta: { auth: true, app: 'stock' } });
  await m.router.replace(path);
  await flush();
  return m;
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('AppGatePage', () => {
  it('says «No access» in the address of a screen this person may not open', async () => {
    const m = await open('/tax/rules');
    expect(m.wrapper.find('[data-testid="no-access"]').exists()).toBe(true);
    expect(m.wrapper.find('[data-testid="app-blocked-checking"]').exists()).toBe(false);
  });

  it('tells why an app does not open when the app is the reason', async () => {
    const m = await open('/stock/items');
    expect(m.wrapper.find('[data-testid="app-blocked-checking"]').exists()).toBe(true);
    expect(m.wrapper.find('[data-testid="no-access"]').exists()).toBe(false);
  });
});
