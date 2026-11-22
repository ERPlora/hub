import { AppPage, applySurface } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { app } from '../__tests__/app-row';
import { appActionLabel, freshEachTest, ids as idsOf, INVOICE, LIST, type Mounted, noteOf, open, PLANS, REPORTS, STOCK, STORE, TAX } from '../__tests__/apps-page';
import { ADMIN, EMPLOYEE, errorFrame, flush, OWNER, subId } from '../__tests__/mount-base';
import type { AppList, AppRow } from '../operations/apps';

const ids = (wrapper: Mounted['wrapper']) => idsOf({ wrapper } as Mounted);

vi.mock('@erplora/ui/components', async (importOriginal) => (await import('../__tests__/apps-page-spies')).componentsWithConfirmSpy(importOriginal));
vi.mock('../lib/access', async (importOriginal) => (await import('../__tests__/apps-page-spies')).accessWithSessionSpy(importOriginal));

freshEachTest();

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

  it('«Open» goes to the app’s first screen, and an app with no screen for this person has none', async () => {
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

  it('«Add apps» (#all) lists every app with what it does, its price and what comes with it', async () => {
    const m = await open('/apps#all');
    await m.result(m.call, 'base.app.list', LIST);
    expect(ids(m.wrapper)).toEqual(['tax', 'invoice', 'reports', 'stock']);
    const invoice = m.wrapper.find('[data-testid="apps-row"][data-id="invoice"]');
    expect(invoice.text()).toContain('What invoice does.');
    expect(invoice.text()).toContain('Free');
    expect(invoice.text()).toContain('Taxes');
    expect(invoice.find('[data-testid="apps-state"]').text()).toBe('Active');
    expect(m.wrapper.find('[data-testid="apps-row"][data-id="stock"]').text()).toContain('Needs a subscription');
  });

  it.each([
    ['en', 'Active'],
    ['es', 'Activa'],
  ] as const)('an app that is on reads the same in both lists and in the state filter (%s)', async (locale, active) => {
    const stateOf = (m: Mounted) => m.wrapper.find('[data-testid="apps-row"][data-id="invoice"] [data-testid="apps-state"]').text();
    const mine = await open('/apps', { locale });
    await mine.result(mine.call, 'base.app.list', LIST);
    expect(stateOf(mine)).toBe(active);
    const all = await open('/apps#all', { locale });
    await all.result(all.call, 'base.app.list', LIST);
    expect(stateOf(all)).toBe(active);
    await all.wrapper.find('[data-testid="apps-filters-toggle"]').trigger('click');
    await flush();
    const filter = all.wrapper.findAll('[data-testid="apps-filter-state"] ion-select-option').map((option) => option.text());
    expect(filter).toContain(active);
  });

  it('shows the plan under the app name, and «Open» as a named icon button in the list', async () => {
    const m = await open('/apps#all');
    await m.result(m.call, 'base.app.list', LIST);
    const invoice = m.wrapper.find('[data-testid="apps-row"][data-id="invoice"]');
    expect(invoice.find('.data-table__identity-title').text()).toContain('Invoicing');
    expect(invoice.find('[data-testid="apps-plan"]').text()).toBe('Free');
    expect(invoice.find('.data-table__identity-icon').classes()).toContain('ep-icon-tile');
    const opener = m.wrapper.find('[data-testid="apps-row-tax-open"]');
    // Its name, with the app it opens, is the title of the host and, inside, the `aria-label` Ionic moves onto its native button.
    expect([opener.text(), opener.attributes('title')]).toEqual(['', 'Open: Taxes']);
  });

  it('«Paid» (#paid) lists only what is bought apart; never a free app', async () => {
    const m = await open('/apps#paid');
    await m.result(m.call, 'base.app.list', LIST);
    expect(ids(m.wrapper)).toEqual(['stock']);
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

  it('a paid app without its right offers «Upgrade plan» to the owner, and only it', async () => {
    const m = await open('/apps#all');
    await m.result(m.call, 'base.app.list', LIST);
    expect(await appActionLabel(m, 'stock', 'plans')).toBe('Upgrade plan: Stock');
    expect(await appActionLabel(m, 'tax', 'plans')).toBeUndefined();
  });

  it('an administrator runs the business but does not buy: why and where it is bought, without the link', async () => {
    const m = await open('/apps#all', { session: ADMIN });
    await m.result(m.call, 'base.app.list', LIST);
    expect(await appActionLabel(m, 'stock', 'plans')).toBeUndefined();
    expect(noteOf(m, 'stock').text()).toBe('Subscribed to on erplora.com, from your ERPlora account.');
  });

  it('who does not run the business sees why and where it is bought, without the link', async () => {
    const m = await open('/apps#all', { session: EMPLOYEE });
    await m.result(m.call, 'base.app.list', LIST);
    expect(m.wrapper.find('[data-testid="apps-row"][data-id="stock"]').text()).toContain('Needs a subscription');
    expect(await appActionLabel(m, 'stock', 'plans')).toBeUndefined();
    expect(noteOf(m, 'stock').text()).toBe('Subscribed to on erplora.com, from your ERPlora account.');
  });

  it('inside the installed app it sells nothing: no link to the Store, it says where it is bought', async () => {
    applySurface('mobile');
    const m = await open('/apps#all', { session: OWNER });
    await m.result(m.call, 'base.app.list', LIST);
    expect(await appActionLabel(m, 'stock', 'plans')).toBeUndefined();
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

  // Every app in every plan: with nothing sold apart, «Paid» and «Price» would only say «Free» again
  // and again, so they are not there; the day an app is sold apart they come back on their own.
  describe('with no app sold apart', () => {
    const FREE_LIST: AppList = { ...LIST, apps: [TAX, INVOICE, REPORTS] };
    const tabIds = (m: Mounted) =>
      (m.wrapper.getComponent(AppPage).props('tabs') as { id: string }[]).map((tab) => tab.id);
    const headers = (m: Mounted) =>
      m.wrapper.findAll('[role="columnheader"]').map((header) => header.text());

    it('has no «Paid» tab', async () => {
      const m = await open('/apps', { locale: 'es' });
      await m.result(m.call, 'base.app.list', FREE_LIST);
      expect(m.wrapper.getComponent(AppPage).props('tabs')).toEqual([
        { id: 'mine', label: 'Mis apps', icon: 'ion:cube-outline' },
        { id: 'all', label: 'Añadir apps', icon: 'ion:storefront-outline' },
      ]);
    });

    it('«Add apps» has no «Price» column, and still names what comes with each app (BASE-F19)', async () => {
      const m = await open('/apps#all');
      await m.result(m.call, 'base.app.list', FREE_LIST);
      expect(headers(m)).not.toContain('Price');
      expect(headers(m)).toContain('Comes with');
      expect(m.wrapper.find('[data-testid="apps-price"]').exists()).toBe(false);
      const invoice = m.wrapper.find('[data-testid="apps-row"][data-id="invoice"]');
      expect(invoice.find('[data-testid="apps-plan"]').text()).toBe('Free');
      expect(invoice.text()).toContain('Taxes');
    });

    it('an old link to #paid opens «Add apps»', async () => {
      const m = await open('/apps#paid');
      await m.result(m.call, 'base.app.list', FREE_LIST);
      expect(m.wrapper.getComponent(AppPage).props('tab')).toBe('all');
      expect(ids(m.wrapper)).toEqual(['tax', 'invoice', 'reports']);
    });

    it('an app sold apart brings «Paid» and «Price» back, live', async () => {
      const m = await open('/apps#all');
      await m.result(m.call, 'base.app.list', FREE_LIST);
      expect(tabIds(m)).toEqual(['mine', 'all']);
      await m.result(m.call, 'base.app.list', LIST, 2);
      expect(tabIds(m)).toEqual(['mine', 'all', 'paid']);
      expect(headers(m)).toContain('Price');
      expect(m.wrapper.find('[data-testid="apps-row"][data-id="invoice"] [data-testid="apps-price"]').text()).toBe('Free');
    });

    describe('on a phone, the cards', () => {
      beforeEach(() => {
        vi.stubGlobal('matchMedia', (query: string) => ({
          media: query,
          matches: true,
          onchange: null,
          addListener: () => {},
          removeListener: () => {},
          addEventListener: () => {},
          removeEventListener: () => {},
          dispatchEvent: () => false,
        }));
      });
      afterEach(() => {
        vi.unstubAllGlobals();
      });
      const fields = (m: Mounted, id: string) =>
        m.wrapper.findAll(`[data-testid="apps-row"][data-id="${id}"] .data-table__card-meta-label`).map((label) => label.text());

      it('say no price either', async () => {
        const m = await open('/apps#all');
        await m.result(m.call, 'base.app.list', FREE_LIST);
        expect(m.wrapper.find('.data-table__card').exists()).toBe(true);
        expect(fields(m, 'invoice')).not.toContain('Price');
        expect(fields(m, 'invoice')).toContain('Comes with');
        expect(m.wrapper.find('[data-testid="apps-price"]').exists()).toBe(false);
      });

      it('put the slotted app identity and its plan in the card head', async () => {
        const m = await open('/apps#all');
        await m.result(m.call, 'base.app.list', FREE_LIST);
        const head = m.wrapper.find('[data-testid="apps-row"][data-id="invoice"] .data-table__card-head');
        expect(head.find('[data-testid="apps-plan"]').text()).toBe('Free');
        expect(head.find('.data-table__identity-icon').classes()).toContain('ep-icon-tile');
        expect(fields(m, 'invoice')).not.toContain('App');
      });

      it('keep category and state filters in the mobile sheet', async () => {
        const m = await open('/apps#all');
        await m.result(m.call, 'base.app.list', LIST);
        await m.wrapper.find('[data-testid="apps-filters-toggle"]').trigger('click');
        await flush();
        expect(m.wrapper.find('[data-testid="apps-filters-panel"]').attributes('aria-modal')).toBe('true');
        expect(m.wrapper.find('[data-testid="apps-filter-category"]').exists()).toBe(true);
        expect(m.wrapper.find('[data-testid="apps-filter-state"]').exists()).toBe(true);
      });

      it('say the price again once an app is sold apart', async () => {
        const m = await open('/apps#all');
        await m.result(m.call, 'base.app.list', LIST);
        expect(fields(m, 'invoice')).toContain('Price');
      });
    });
  });

  describe('the counter: the apps on, as «My apps» lists them, and the plan’s chosen ones (hub#1286)', () => {
    // Taxes is born on in every country (hub#997): on, never chosen, it takes nothing of the plan's limit.
    const BORN = app('tax', { name: 'Taxes', chosen: false, mandatory: true });
    const CHOSEN = app('task', { name: 'Tasks' });
    const OFF = app('flow', { name: 'Flows', state: 'off', chosen: false, path: null });
    // sale came with customer: both are on, and only sale is one of the plan's.
    const SALE = app('sale', { name: 'Sales', requires: ['customer'] });
    const CUSTOMER = app('customer', { name: 'Customers', chosen: false, required_by: ['sale'] });
    const listOf = (enabled: number, ...apps: AppRow[]): AppList => ({
      apps,
      country_name: 'Spain',
      store_url: STORE,
      plan_url: PLANS,
      max_apps: 20,
      enabled,
    });
    const counter = (m: Mounted) => m.wrapper.find('[data-testid="apps-counter"]').text();

    it('an app born on is turned on, and none of the plan’s', async () => {
      const m = await open();
      await m.result(m.call, 'base.app.list', listOf(0, BORN, OFF));
      expect(counter(m)).toBe('1 app turned on · 0 of 20 in your plan');
    });

    it('an app the business chose is turned on and one of the plan’s', async () => {
      const m = await open();
      await m.result(m.call, 'base.app.list', listOf(1, BORN, CHOSEN, OFF));
      expect(counter(m)).toBe('2 apps turned on · 1 of 20 in your plan');
    });

    it('an app off, or paid without its right, is not turned on', async () => {
      const m = await open();
      await m.result(m.call, 'base.app.list', listOf(0, OFF, STOCK));
      expect(counter(m)).toBe('0 apps turned on · 0 of 20 in your plan');
    });

    it('counts what came along with another app, the way «My apps» lists it', async () => {
      const m = await open();
      await m.result(m.call, 'base.app.list', listOf(2, SALE, CUSTOMER, CHOSEN, OFF));
      expect(counter(m)).toBe(`${ids(m.wrapper).length} apps turned on · 2 of 20 in your plan`);
      expect(ids(m.wrapper)).toEqual(['sale', 'customer', 'task']);
    });

    it('an app still being set up, or that failed to be, is turned on', async () => {
      const m = await open();
      const creating = { ...OFF, state: 'creating' as const, chosen: true };
      const failed = { ...CHOSEN, state: 'failed' as const };
      await m.result(m.call, 'base.app.list', listOf(2, creating, failed));
      expect(counter(m)).toBe('2 apps turned on · 2 of 20 in your plan');
    });

    it('without a limit, the apps turned on', async () => {
      const m = await open();
      await m.result(m.call, 'base.app.list', { ...listOf(0, BORN, OFF), max_apps: null });
      expect(counter(m)).toBe('1 app turned on · Unlimited');
      await m.result(m.call, 'base.app.list', { ...listOf(1, BORN, CHOSEN, OFF), max_apps: null }, 2);
      expect(counter(m)).toBe('2 apps turned on · Unlimited');
    });

    it('in Spanish', async () => {
      const m = await open('/apps', { locale: 'es' });
      await m.result(m.call, 'base.app.list', listOf(0, BORN, OFF));
      expect(counter(m)).toBe('1 app activada · 0 de 20 de tu plan');
      await m.result(m.call, 'base.app.list', listOf(1, BORN, CHOSEN, OFF), 2);
      expect(counter(m)).toBe('2 apps activadas · 1 de 20 de tu plan');
      await m.result(m.call, 'base.app.list', { ...listOf(1, BORN, CHOSEN, OFF), max_apps: null }, 3);
      expect(counter(m)).toBe('2 apps activadas · Sin límite');
      // A business just born without a limit: Taxes alone, in the singular.
      await m.result(m.call, 'base.app.list', { ...listOf(0, BORN, OFF), max_apps: null }, 4);
      expect(counter(m)).toBe('1 app activada · Sin límite');
    });
  });
});
