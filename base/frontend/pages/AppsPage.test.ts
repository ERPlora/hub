// Apps (BASE-G67…G74; the old hub's AppsPage): «My apps», «Add apps» and «Paid» over the live `base.app.list`, in
// the address (`/apps`, `#all`, `#paid`). «Open» leads to the app's first screen; a paid app without its right says
// it needs a subscription and, for whoever runs the business and only on the web, links to erplora.com's Store
// (buying is never inside the Hub). A failed read says so with «Retry» and keeps the rows; it is never «no apps».
// Whoever runs the business turns an app on or off (PLAN-HUB §9): the dialog names what comes along or goes with it,
// a refusal says why (another app needs it, the app itself, or the plan's limit, with «Upgrade plan»), and the
// counter says how many of the plan's apps are on.
import { AppPage, applySurface, toastError, toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { sessionChanged } from '../lib/access';

import { EMPLOYEE, errorFrame, flush, mountBase, OWNER, subId } from '../__tests__/mount-base';
import type { AppList, AppRow } from '../operations';
import AppsPage from './AppsPage.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));
vi.mock('../lib/access', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/access')>()),
  sessionChanged: vi.fn(),
}));

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
    chosen: true,
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
const PLANS = 'https://erplora.com/store/plans?business=h1';
const LIST: AppList = { apps: [TAX, INVOICE, REPORTS, STOCK], store_url: STORE, plan_url: PLANS, max_apps: null, enabled: 3 };

async function open(path = '/apps', options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(AppsPage, { path, routes: ['/apps', '/tax/home', '/invoice/home'], ...options });
  const call = await m.live();
  return { ...m, call };
}

function ids(wrapper: Awaited<ReturnType<typeof open>>['wrapper']) {
  return wrapper.findAll('[data-testid="apps-row"]').map((row) => row.attributes('data-id'));
}

beforeEach(() => {
  applySurface('web');
  mocks.confirm.mockReset();
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
  vi.mocked(sessionChanged).mockClear();
});
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

  describe('turning an app on or off (PLAN-HUB §9)', () => {
    // sale came with customer; task was chosen; flow is off and needs nothing; booking (off) needs schedule (off).
    const SALE = app('sale', { name: 'Sales', requires: ['customer'] });
    const CUSTOMER = app('customer', { name: 'Customers', chosen: false, required_by: ['sale'] });
    const TASK = app('task', { name: 'Tasks' });
    const FLOW = app('flow', { name: 'Flows', state: 'off', chosen: false, path: null });
    const SCHEDULE = app('schedule', { name: 'Schedules', state: 'off', chosen: false, path: null });
    const BOOKING = app('booking', { name: 'Bookings', state: 'off', chosen: false, path: null, requires: ['schedule'] });
    const APPS: AppList = {
      apps: [SALE, CUSTOMER, TASK, FLOW, SCHEDULE, BOOKING, STOCK],
      store_url: STORE,
      plan_url: PLANS,
      max_apps: 20,
      enabled: 2,
    };
    const posted = (m: Awaited<ReturnType<typeof open>>) =>
      m.net.api.map((c) => [c.url, JSON.parse(String(c.init.body ?? '{}')) as Record<string, unknown>]);
    const refusal = (status: number, error: Record<string, unknown>) => () => Response.json({ error }, { status });

    it('«Turn off» asks with the app and what goes with it, turns it off and reads the menu again', async () => {
      mocks.confirm.mockResolvedValue(true);
      const m = await open('/apps', {
        onApi: () => Response.json({ app: 'sale', state: 'off', chosen: false, along: [{ id: 'customer', name: 'Customers' }] }),
      });
      await m.result(m.call, 'base.app.list', APPS);

      await m.wrapper.find('[data-testid="apps-row-sale-toggle"]').trigger('click');
      await flush();

      expect(mocks.confirm).toHaveBeenCalledTimes(1);
      const asked = mocks.confirm.mock.calls[0][0];
      expect(asked.title).toBe('Turn off Sales?');
      expect(asked.message).toContain('Customers');
      expect(asked.message).toContain('Nothing is deleted');
      expect(asked.tone).toBe('danger');
      expect(posted(m)).toEqual([['/api/apps/disable', { app: 'sale' }]]);
      expect(vi.mocked(toastSuccess).mock.calls[0][0]).toBe('Sales is off. Also turned off: Customers.');
      expect(sessionChanged).toHaveBeenCalledTimes(1);
    });

    it('cancelled, nothing is sent', async () => {
      mocks.confirm.mockResolvedValue(false);
      const m = await open();
      await m.result(m.call, 'base.app.list', APPS);
      await m.wrapper.find('[data-testid="apps-row-task-toggle"]').trigger('click');
      await flush();
      expect(m.net.api).toEqual([]);
      expect(sessionChanged).not.toHaveBeenCalled();
    });

    it('one another app on needs says which to turn off first, without asking or sending', async () => {
      const m = await open();
      await m.result(m.call, 'base.app.list', APPS);
      await m.wrapper.find('[data-testid="apps-row-customer-toggle"]').trigger('click');
      await flush();
      expect(mocks.confirm).not.toHaveBeenCalled();
      expect(m.net.api).toEqual([]);
      expect(vi.mocked(toastError).mock.calls[0][0]).toBe('Turn off Sales first.');
    });

    it('a 409 from the server says the same, with the apps it names', async () => {
      mocks.confirm.mockResolvedValue(true);
      const m = await open('/apps', {
        locale: 'es',
        onApi: refusal(409, { code: 'base.app_required', message: 'server words', required_by: ['sale'] }),
      });
      await m.result(m.call, 'base.app.list', APPS);
      await m.wrapper.find('[data-testid="apps-row-task-toggle"]').trigger('click');
      await flush();
      expect(vi.mocked(toastError).mock.calls[0][0]).toBe('Apaga antes Sales.');
      expect(sessionChanged).not.toHaveBeenCalled();
    });

    it('an app that refuses to go off says its reason', async () => {
      mocks.confirm.mockResolvedValue(true);
      const m = await open('/apps', {
        onApi: refusal(409, { code: 'base.app_vetoed', message: 'VeriFactu has records the AEAT has not accepted yet.', app: 'task' }),
      });
      await m.result(m.call, 'base.app.list', APPS);
      await m.wrapper.find('[data-testid="apps-row-task-toggle"]').trigger('click');
      await flush();
      expect(vi.mocked(toastError).mock.calls[0][0]).toBe('VeriFactu has records the AEAT has not accepted yet.');
    });

    it('«Turn on» an app that needs nothing turns it on at once and reads the menu again', async () => {
      const m = await open('/apps#all', { onApi: () => Response.json({ app: 'flow', state: 'on', chosen: true, along: [] }) });
      await m.result(m.call, 'base.app.list', APPS);
      const toggle = m.wrapper.find('[data-testid="apps-row-flow-toggle"]');
      expect(toggle.text()).toContain('Turn on');
      await toggle.trigger('click');
      await flush();
      expect(mocks.confirm).not.toHaveBeenCalled();
      expect(posted(m)).toEqual([['/api/apps/enable', { app: 'flow' }]]);
      expect(vi.mocked(toastSuccess).mock.calls[0][0]).toBe('Flows is on.');
      expect(sessionChanged).toHaveBeenCalledTimes(1);
    });

    it('«Turn on» an app that needs others off asks first, naming them', async () => {
      mocks.confirm.mockResolvedValue(true);
      const m = await open('/apps#all', {
        onApi: () => Response.json({ app: 'booking', state: 'on', chosen: true, along: [{ id: 'schedule', name: 'Schedules' }] }),
      });
      await m.result(m.call, 'base.app.list', APPS);
      await m.wrapper.find('[data-testid="apps-row-booking-toggle"]').trigger('click');
      await flush();
      const asked = mocks.confirm.mock.calls[0][0];
      expect([asked.title, asked.message]).toEqual(['Turn on Bookings?', 'Bookings needs Schedules: it turns on with it.']);
      expect(posted(m)).toEqual([['/api/apps/enable', { app: 'booking' }]]);
      expect(vi.mocked(toastSuccess).mock.calls[0][0]).toBe('Bookings is on. Also turned on: Schedules.');
    });

    it('at the plan’s limit it says so, with «Upgrade plan» for whoever runs the business on the web', async () => {
      const m = await open('/apps#all', {
        onApi: refusal(402, { code: 'base.app_limit_reached', message: 'server words', max_apps: 20, enabled: 20 }),
      });
      await m.result(m.call, 'base.app.list', { ...APPS, enabled: 20 });
      await m.wrapper.find('[data-testid="apps-row-flow-toggle"]').trigger('click');
      await flush();
      const notice = m.wrapper.find('[data-testid="apps-limit"]');
      expect(notice.text()).toContain('You have reached the 20-app limit of your plan. Upgrade your plan or turn one off.');
      const upgrade = notice.find('[data-testid="apps-limit-upgrade"]');
      expect(upgrade.attributes()).toMatchObject({ href: PLANS, target: '_blank', rel: 'noopener' });
      expect(upgrade.text()).toBe('Upgrade plan');
      expect(sessionChanged).not.toHaveBeenCalled();
      expect(toastError).not.toHaveBeenCalled();
    });

    it('in Spanish, and inside the installed app without the link', async () => {
      applySurface('mobile');
      const m = await open('/apps#all', {
        locale: 'es',
        onApi: refusal(402, { code: 'base.app_limit_reached', message: 'server words', max_apps: 20, enabled: 21 }),
      });
      await m.result(m.call, 'base.app.list', { ...APPS, enabled: 21 });
      await m.wrapper.find('[data-testid="apps-row-flow-toggle"]').trigger('click');
      await flush();
      const notice = m.wrapper.find('[data-testid="apps-limit"]');
      expect(notice.text()).toContain('Has llegado al límite de 20 apps de tu plan. Mejora el plan o apaga una.');
      expect(notice.find('[data-testid="apps-limit-upgrade"]').exists()).toBe(false);
    });

    it('a paid app without its right offers no «Turn on»: it is bought on erplora.com', async () => {
      const m = await open('/apps#all');
      await m.result(m.call, 'base.app.list', APPS);
      expect(m.wrapper.find('[data-testid="apps-row-stock-toggle"]').exists()).toBe(false);
      expect(m.wrapper.find('[data-testid="apps-row"][data-id="stock"] [data-testid="apps-buy"]').exists()).toBe(true);
    });

    it('any other failure says so with the server’s words, and the button waits while it is sent', async () => {
      let answer: (response: Response) => void = () => undefined;
      const m = await open('/apps#all', { onApi: () => new Promise<Response>((resolve) => (answer = resolve)) });
      await m.result(m.call, 'base.app.list', APPS);
      await m.wrapper.find('[data-testid="apps-row-flow-toggle"]').trigger('click');
      await flush();
      expect(m.wrapper.find('[data-testid="apps-row-flow-toggle"]').attributes('disabled')).toBeDefined();
      answer(Response.json({ error: { code: 'internal_error', message: 'Boom.' } }, { status: 500 }));
      await flush();
      expect(vi.mocked(toastError).mock.calls[0][0]).toBe('Flows could not be changed: Boom.');
      expect(m.wrapper.find('[data-testid="apps-row-flow-toggle"]').attributes('disabled')).toBeUndefined();
    });

    it('who does not run the business turns nothing on or off', async () => {
      const m = await open('/apps#all', { session: EMPLOYEE });
      await m.result(m.call, 'base.app.list', APPS);
      expect(m.wrapper.find('[data-testid="apps-row-flow-toggle"]').exists()).toBe(false);
      expect(m.wrapper.find('[data-testid="apps-row-task-toggle"]').exists()).toBe(false);
    });

    it('an app off is still in «Add apps» with its icon, its name and «Off»; «My apps» lists only the ones on', async () => {
      const m = await open('/apps#all');
      await m.result(m.call, 'base.app.list', APPS);
      const flow = m.wrapper.find('[data-testid="apps-row"][data-id="flow"]');
      expect(flow.text()).toContain('Flows');
      expect(flow.find('.apps-icon').exists()).toBe(true);
      expect(flow.find('[data-testid="apps-state"]').text()).toBe('Off');
      m.wrapper.getComponent(AppPage).vm.$emit('update:tab', 'mine');
      await flush();
      expect(ids(m.wrapper)).toEqual(['sale', 'customer', 'task']);
    });

    it('counts the chosen apps on against the plan’s limit, or says there is none', async () => {
      const m = await open();
      await m.result(m.call, 'base.app.list', APPS);
      expect(m.wrapper.find('[data-testid="apps-counter"]').text()).toBe('2 of 20 apps turned on');
      await m.result(m.call, 'base.app.list', { ...APPS, max_apps: null, enabled: 1 }, 2);
      expect(m.wrapper.find('[data-testid="apps-counter"]').text()).toBe('1 app turned on · Unlimited');
    });

    it('the counter in Spanish', async () => {
      const m = await open('/apps', { locale: 'es' });
      await m.result(m.call, 'base.app.list', APPS);
      expect(m.wrapper.find('[data-testid="apps-counter"]').text()).toBe('2 de 20 apps activadas');
      await m.result(m.call, 'base.app.list', { ...APPS, max_apps: null, enabled: 3 }, 2);
      expect(m.wrapper.find('[data-testid="apps-counter"]').text()).toBe('3 apps activadas · Sin límite');
    });
  });
});
