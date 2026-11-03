// «Why it does not open» (BASE-G132, G134; the old hub's ModuleView states): mounted by the app gate in the address
// of a screen whose app the session gives `off`. It reads `base.app.list` to tell why: a paid app without its right
// gets «Subscription needed» (data safe; bought on erplora.com: the Store's link for whoever runs the business, on the
// web), an app the business does not have says so; both lead to Apps. Bought meanwhile (the SaaS's photo re-runs
// the list), it offers to open the app, with a full load that brings the session up to date.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { defineComponent } from 'vue';

import { EMPLOYEE, errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import type { AppList, AppRow } from '../operations';
import AppBlockedPage from './AppBlockedPage.vue';

function app(id: string, fields: Partial<AppRow> = {}): AppRow {
  return {
    id,
    name: id[0].toUpperCase() + id.slice(1),
    icon: 'ion:cube-outline',
    category: 'catalog',
    category_label: 'Catalog and stock',
    summary: '',
    premium: true,
    right: 'missing',
    state: 'blocked',
    chosen: false,
    path: null,
    requires: [],
    required_by: [],
    ...fields,
  };
}

const STORE = 'https://erplora.com/store/modules?business=h1';
const LIST: AppList = {
  apps: [app('stock', { name: 'Stock' })],
  store_url: STORE,
  plan_url: 'https://erplora.com/store/plans?business=h1',
  max_apps: null,
  enabled: 0,
};
const STOCK_PAGE = defineComponent({ template: '<div />' });

async function open(path = '/stock/items', options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(AppBlockedPage, { path, ...options });
  // The app's own route, which the page resolves the address against to know whose screen it is.
  m.router.addRoute({ path: '/stock/items', component: STOCK_PAGE, meta: { auth: true, app: 'stock' } });
  m.router.addRoute({ path: '/ghost', component: STOCK_PAGE, meta: { auth: true, app: 'ghost' } });
  await m.router.replace(path);
  await flush();
  const call = await m.live();
  return { ...m, call };
}

beforeEach(() => applySurface('web'));
afterEach(() => {
  document.body.innerHTML = '';
});

describe('AppBlockedPage', () => {
  it('says it is checking while the list comes', async () => {
    const m = await open();
    expect(m.wrapper.find('[data-testid="app-blocked-checking"]').exists()).toBe(true);
  });

  it('a paid app without its right: «Subscription needed», data safe, the Store’s link and Apps (BASE-G134)', async () => {
    const m = await open();
    await m.result(m.call, 'base.app.list', LIST);
    const card = m.wrapper.find('[data-testid="app-blocked-subscription"]');
    expect(card.text()).toContain('Subscription needed');
    expect(card.text()).toContain('Stock is disabled because this business does not have its subscription');
    expect(card.text()).toContain('Your data is safe');
    const buy = m.wrapper.find('[data-testid="app-blocked-buy"]');
    expect(buy.attributes()).toMatchObject({ href: STORE, target: '_blank' });
    // PLAN §32, point 2: every app comes with a plan, so the way to it is a better plan.
    expect(buy.text()).toBe('Upgrade plan');
    await m.wrapper.find('[data-testid="app-blocked-to-apps"]').trigger('click');
    await flush();
    expect(m.router.currentRoute.value.fullPath).toBe('/apps#all');
  });

  it('who does not run the business, or the installed app, gets no link: it says where it is bought', async () => {
    const m = await open('/stock/items', { session: EMPLOYEE });
    await m.result(m.call, 'base.app.list', LIST);
    expect(m.wrapper.find('[data-testid="app-blocked-buy"]').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="app-blocked-subscription"]').text()).toContain('erplora.com');

    applySurface('mobile');
    const inApp = await open();
    await inApp.result(inApp.call, 'base.app.list', LIST);
    expect(inApp.wrapper.find('[data-testid="app-blocked-buy"]').exists()).toBe(false);
  });

  it('bought meanwhile: it offers to open the app with a full load (the session comes up to date)', async () => {
    const m = await open();
    await m.result(m.call, 'base.app.list', LIST);
    await m.result(m.call, 'base.app.list', { ...LIST, apps: [app('stock', { name: 'Stock', state: 'on', right: 'purchase', path: '/stock/items' })] }, 2);
    expect(m.wrapper.find('[data-testid="app-blocked-subscription"]').exists()).toBe(false);
    const reopen = m.wrapper.find('[data-testid="app-blocked-open"]');
    expect(reopen.text()).toContain('Open Stock');
    expect(reopen.element.tagName).toBe('A');
    expect(reopen.attributes('href')).toBe('/stock/items');
  });

  it('«Mejorar plan» in Spanish', async () => {
    const m = await open('/stock/items', { locale: 'es' });
    await m.result(m.call, 'base.app.list', LIST);
    expect(m.wrapper.find('[data-testid="app-blocked-buy"]').text()).toBe('Mejorar plan');
  });

  it('an app the business does not have says so, in Spanish too, and leads to Apps (BASE-G132)', async () => {
    const m = await open('/ghost', { locale: 'es' });
    await m.result(m.call, 'base.app.list', LIST);
    expect(m.wrapper.find('[data-testid="app-blocked-missing"]').text()).toContain('Esta app no está disponible en este negocio');
    expect(m.wrapper.find('[data-testid="app-blocked-to-apps"]').exists()).toBe(true);
  });

  it('an app the business turned off says it is not available here and leads to Apps, where it is turned on', async () => {
    const m = await open();
    await m.result(m.call, 'base.app.list', { ...LIST, apps: [app('stock', { name: 'Stock', premium: false, right: 'free', state: 'off' })] });
    expect(m.wrapper.find('[data-testid="app-blocked-missing"]').text()).toContain('This app is not available in this business');
    expect(m.wrapper.find('[data-testid="app-blocked-subscription"]').exists()).toBe(false);
    await m.wrapper.find('[data-testid="app-blocked-to-apps"]').trigger('click');
    await flush();
    expect(m.router.currentRoute.value.fullPath).toBe('/apps#all');
  });

  it('an app being set up (S3) says so, and offers to open it once it is on, live', async () => {
    const m = await open();
    const creating = app('stock', { name: 'Stock', premium: false, right: 'free', state: 'creating', chosen: true });
    await m.result(m.call, 'base.app.list', { ...LIST, apps: [creating] });
    const setting = m.wrapper.find('[data-testid="app-blocked-creating"]');
    expect(setting.text()).toContain('Stock is being set up');
    expect(setting.text()).toContain('It opens in a moment');
    expect(m.wrapper.find('[data-testid="app-blocked-missing"]').exists()).toBe(false);
    await m.result(m.call, 'base.app.list', { ...LIST, apps: [{ ...creating, state: 'on', path: '/stock/items' }] }, 2);
    expect(m.wrapper.find('[data-testid="app-blocked-open"]').attributes('href')).toBe('/stock/items');
  });

  it('an app that could not be set up says so and leads to Apps, where it is tried again; in Spanish too', async () => {
    const m = await open('/stock/items', { locale: 'es' });
    const failed = app('stock', { name: 'Stock', premium: false, right: 'free', state: 'failed', chosen: true });
    await m.result(m.call, 'base.app.list', { ...LIST, apps: [failed] });
    expect(m.wrapper.find('[data-testid="app-blocked-failed"]').text()).toContain('No se ha podido preparar Stock');
    await m.wrapper.find('[data-testid="app-blocked-to-apps"]').trigger('click');
    await flush();
    expect(m.router.currentRoute.value.fullPath).toBe('/apps');
  });

  it('a failed check says so with «Retry», never a reason made up', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, 'base.app.list'), 'internal_error'));
    await flush();
    expect(m.wrapper.find('[data-testid="app-blocked-error"]').text()).toContain('We could not check why this app does not open');
    expect(m.wrapper.find('[data-testid="app-blocked-subscription"]').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="app-blocked-retry"]').exists()).toBe(true);
  });
});
