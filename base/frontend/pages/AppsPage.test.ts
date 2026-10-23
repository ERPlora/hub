// Apps (BASE-G67…G74; the old hub's AppsPage): «My apps», «Add apps» and «Paid» over the live `base.app.list`, in
// the address (`/apps`, `#all`, `#paid`). «Open» leads to the app's first screen; a paid app without its right says
// it needs a subscription and, for whoever runs the business and only on the web, links to erplora.com's Store
// (buying is never inside the Hub). A failed read says so with «Retry» and keeps the rows; it is never «no apps».
import { AppPage, applySurface } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { EMPLOYEE, errorFrame, flush, mountBase, OWNER, subId } from '../__tests__/mount-base';
import type { AppList, AppRow } from '../operations';
import AppsPage from './AppsPage.vue';

function app(id: string, fields: Partial<AppRow> = {}): AppRow {
  return {
    id,
    name: id[0].toUpperCase() + id.slice(1),
    icon: 'ion:cube-outline',
    category: 'sales',
    category_label: 'Sales, payments and tax',
    summary: `What ${id} does.`,
    premium: false,
    right: 'free',
    state: 'on',
    path: `/${id}/home`,
    requires: [],
    required_by: [],
    ...fields,
  };
}

const STORE = 'https://erplora.com/store/modules?business=h1';
const TAX = app('tax', { name: 'Taxes', required_by: ['invoice'] });
const INVOICE = app('invoice', { name: 'Invoicing', requires: ['tax'], category: 'sales' });
const REPORTS = app('reports', { name: 'Reports', path: null, category: 'organization', category_label: 'Organization' });
const STOCK = app('stock', { name: 'Stock', premium: true, right: 'missing', state: 'blocked', path: null, category: 'catalog', category_label: 'Catalog and stock' });
const LIST: AppList = { apps: [TAX, INVOICE, REPORTS, STOCK], store_url: STORE };

async function open(path = '/apps', options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(AppsPage, { path, routes: ['/apps', '/tax/home', '/invoice/home'], ...options });
  const call = await m.live();
  return { ...m, call };
}

function ids(wrapper: Awaited<ReturnType<typeof open>>['wrapper']) {
  return wrapper.findAll('[data-testid="apps-row"]').map((row) => row.attributes('data-id'));
}

beforeEach(() => applySurface('web'));
afterEach(() => {
  document.body.innerHTML = '';
});

describe('AppsPage', () => {
  it('follows the business’s apps live', async () => {
    const m = await open();
    expect(m.client.stream.subscriptions('base.app.list').map((sub) => sub.params)).toEqual([{}]);
  });

  it('«My apps» lists the apps that are on, with their category and «Active»', async () => {
    const m = await open();
    await m.result(m.call, 'base.app.list', LIST);
    expect(ids(m.wrapper)).toEqual(['tax', 'invoice', 'reports']);
    const first = m.wrapper.find('[data-testid="apps-row"]');
    expect(first.text()).toContain('Taxes');
    expect(first.text()).toContain('Sales, payments and tax');
    expect(m.wrapper.findAll('[data-testid="apps-state"]').map((pill) => [pill.text(), pill.attributes('data-tone')])).toEqual([
      ['Active', 'success'],
      ['Active', 'success'],
      ['Active', 'success'],
    ]);
  });

  it('«Open» goes to the app’s first screen, and an app with no screen for this person has none (BASE-G68)', async () => {
    const m = await open();
    await m.result(m.call, 'base.app.list', LIST);
    expect(m.wrapper.find('[data-testid="apps-row-reports-open"]').exists()).toBe(false);
    await m.wrapper.find('[data-testid="apps-row-tax-open"]').trigger('click');
    await flush();
    expect(m.router.currentRoute.value.path).toBe('/tax/home');
  });

  it('«Open» checks the app again when pressed: one that just stopped being on does not open', async () => {
    const m = await open();
    await m.result(m.call, 'base.app.list', LIST);
    const button = m.wrapper.find('[data-testid="apps-row-tax-open"]');
    await m.result(m.call, 'base.app.list', { ...LIST, apps: [{ ...TAX, state: 'blocked', path: null }, INVOICE] }, 2);
    await button.trigger('click');
    await flush();
    expect(m.router.currentRoute.value.path).toBe('/apps');
  });

  it('«Add apps» (#all) lists every app with what it does, its price and what comes with it (BASE-G69, G70, G73)', async () => {
    const m = await open('/apps#all');
    await m.result(m.call, 'base.app.list', LIST);
    expect(ids(m.wrapper)).toEqual(['tax', 'invoice', 'reports', 'stock']);
    const invoice = m.wrapper.find('[data-testid="apps-row"][data-id="invoice"]');
    expect(invoice.text()).toContain('What invoice does.');
    expect(invoice.text()).toContain('Free');
    expect(invoice.text()).toContain('Taxes');
    expect(invoice.text()).toContain('Installed');
    expect(m.wrapper.find('[data-testid="apps-row"][data-id="stock"]').text()).toContain('Needs a subscription');
  });

  it('«Paid» (#paid) lists only what is bought apart; never a free app (hub#2655)', async () => {
    const m = await open('/apps#paid');
    await m.result(m.call, 'base.app.list', LIST);
    expect(ids(m.wrapper)).toEqual(['stock']);
  });

  it('«Paid» with nothing bought apart says every app comes with the plan', async () => {
    const m = await open('/apps#paid', { locale: 'es' });
    await m.result(m.call, 'base.app.list', { ...LIST, apps: [TAX] });
    expect(m.wrapper.find('[data-testid="apps-empty"]').text()).toContain('Ninguna app se vende aparte');
  });

  it('says where a paid app’s right comes from', async () => {
    const m = await open('/apps#paid', { locale: 'es' });
    await m.result(m.call, 'base.app.list', {
      ...LIST,
      apps: [
        TAX,
        app('crm', { premium: true, right: 'plan' }),
        app('loyalty', { premium: true, right: 'purchase' }),
        app('customer', { name: 'Clientes', premium: true, right: 'required', required_by: ['loyalty'] }),
        STOCK,
      ],
    });
    const price = (id: string) => m.wrapper.find(`[data-testid="apps-row"][data-id="${id}"] [data-testid="apps-price"]`).text();
    expect([price('crm'), price('loyalty'), price('customer'), price('stock')]).toEqual([
      'Incluida en tu plan',
      'Contratada',
      'Incluida con Loyalty',
      'De pago',
    ]);
  });

  it('a paid app without its right links to erplora.com’s Store for whoever runs the business (BASE-G74)', async () => {
    const m = await open('/apps#all');
    await m.result(m.call, 'base.app.list', LIST);
    const buy = m.wrapper.find('[data-testid="apps-row"][data-id="stock"] [data-testid="apps-buy"]');
    expect(buy.attributes()).toMatchObject({ href: STORE, target: '_blank', rel: 'noopener' });
    expect(buy.text()).toBe('Subscribe on erplora.com');
    expect(m.wrapper.find('[data-testid="apps-row"][data-id="tax"] [data-testid="apps-buy"]').exists()).toBe(false);
  });

  it('who does not run the business sees why, without the link', async () => {
    const m = await open('/apps#all', { session: EMPLOYEE });
    await m.result(m.call, 'base.app.list', LIST);
    expect(m.wrapper.find('[data-testid="apps-row"][data-id="stock"]').text()).toContain('Needs a subscription');
    expect(m.wrapper.find('[data-testid="apps-buy"]').exists()).toBe(false);
  });

  it('inside the installed app it sells nothing: no link to the Store, it says where it is bought', async () => {
    applySurface('mobile');
    const m = await open('/apps#all', { session: OWNER });
    await m.result(m.call, 'base.app.list', LIST);
    expect(m.wrapper.find('[data-testid="apps-buy"]').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="apps-row"][data-id="stock"]').text()).toContain('erplora.com');
  });

  it('a tab changes the address, so it can be linked and Back leaves Apps', async () => {
    const m = await open();
    await m.result(m.call, 'base.app.list', LIST);
    m.wrapper.getComponent(AppPage).vm.$emit('update:tab', 'all');
    await flush();
    expect(m.router.currentRoute.value.fullPath).toBe('/apps#all');
  });

  it('a failed read says so with «Retry» and keeps the apps it had', async () => {
    const m = await open();
    await m.result(m.call, 'base.app.list', LIST);
    m.call.push(errorFrame(subId(m.client, 'base.app.list'), 'internal_error'));
    await flush();
    expect(m.wrapper.find('[data-testid="apps-error"]').text()).toContain('We could not read your apps');
    expect(ids(m.wrapper)).toEqual(['tax', 'invoice', 'reports']);
    expect(m.wrapper.find('[data-testid="apps-retry"]').exists()).toBe(true);
  });

  it('a first read that fails never says «no apps»', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, 'base.app.list'), 'internal_error'));
    await flush();
    expect(m.wrapper.find('[data-testid="apps-error"]').exists()).toBe(true);
    expect(m.wrapper.find('[data-testid="apps-empty"]').exists()).toBe(false);
  });

  it('in Spanish', async () => {
    const m = await open('/apps', { locale: 'es' });
    await m.result(m.call, 'base.app.list', LIST);
    expect(m.wrapper.find('[data-testid="apps-state"]').text()).toBe('Activa');
    expect(m.wrapper.getComponent(AppPage).props('tabs')).toEqual([
      { id: 'mine', label: 'Mis apps', icon: 'ion:cube-outline' },
      { id: 'all', label: 'Añadir apps', icon: 'ion:storefront-outline' },
      { id: 'paid', label: 'De pago', icon: 'ion:wallet-outline' },
    ]);
  });
});
