// The rules of the Apps screen (BASE-G67…G74) the browser applies to `base.app.list`: which apps each tab lists,
// the tab of an address, what comes along with an app, who it comes with, and when «Open» is offered; and turning an
// app on or off (PLAN-HUB §9): when each is offered, what comes along or goes with it, and what goes off first.
import { describe, expect, it } from 'vitest';

import type { AppRow } from '../operations';
import {
  appsOfTab,
  canOpen,
  canRetry,
  canTurnOff,
  canTurnOn,
  comesWith,
  goesOffWith,
  includedWith,
  offFirst,
  sellsApart,
  tabOf,
  TAB_HASH,
  turnsOnWith,
} from './apps';

function app(id: string, fields: Partial<AppRow> = {}): AppRow {
  return {
    id,
    name: id[0].toUpperCase() + id.slice(1),
    icon: 'ion:cube-outline',
    category: 'sales',
    category_label: 'Sales',
    summary: '',
    premium: false,
    right: 'free',
    state: 'on',
    chosen: true,
    path: `/${id}`,
    requires: [],
    required_by: [],
    ...fields,
  };
}

const TAX = app('tax', { name: 'Taxes', required_by: ['invoice'] });
const CUSTOMER = app('customer', { name: 'Customers', premium: true, right: 'required', required_by: ['invoice'] });
const INVOICE = app('invoice', { name: 'Invoicing', premium: true, right: 'purchase', requires: ['tax', 'customer'] });
const STOCK = app('stock', { premium: true, right: 'missing', state: 'blocked', path: null });
const APPS = [TAX, CUSTOMER, INVOICE, STOCK];

describe('the tabs of Apps', () => {
  it('«My apps» lists the apps the business has on; «Add apps» every one; «Paid» only those bought apart', () => {
    expect(appsOfTab(APPS, 'mine').map((row) => row.id)).toEqual(['tax', 'customer', 'invoice']);
    expect(appsOfTab(APPS, 'all').map((row) => row.id)).toEqual(['tax', 'customer', 'invoice', 'stock']);
    expect(appsOfTab(APPS, 'paid').map((row) => row.id)).toEqual(['customer', 'invoice', 'stock']);
  });

  it('a free app never shows under «Paid» (hub#2655: «Free» in the paid tab)', () => {
    expect(appsOfTab([TAX, app('sale')], 'paid')).toEqual([]);
  });

  it('reads the tab from the address, the old hub’s: none is «My apps», #all and #paid the catalogue', () => {
    const tabs = (paid: boolean) => ['', '#all', '#paid', '#other'].map((hash) => tabOf(hash, paid));
    expect(tabs(true)).toEqual(['mine', 'all', 'paid', 'mine']);
    expect(TAB_HASH).toEqual({ mine: '', all: '#all', paid: '#paid' });
  });

  it('with nothing sold apart there is no «Paid»: an old link to #paid opens «Add apps» (PLAN §32)', () => {
    expect(['', '#all', '#paid', '#other'].map((hash) => tabOf(hash, false))).toEqual(['mine', 'all', 'all', 'mine']);
  });

  it('says whether the catalogue sells any app apart: every app in every plan sells none (PLAN §32)', () => {
    expect(sellsApart([TAX, app('sale')])).toBe(false);
    expect(sellsApart([])).toBe(false);
    expect(sellsApart(APPS)).toBe(true);
    expect(sellsApart([TAX, STOCK])).toBe(true);
  });
});

describe('what comes along with an app', () => {
  it('names what it needs, by name and sorted, and what it comes with, among the apps the business has', () => {
    expect(comesWith(INVOICE, APPS)).toEqual(['Customers', 'Taxes']);
    expect(comesWith(TAX, APPS)).toEqual([]);
    expect(includedWith(CUSTOMER, APPS)).toEqual(['Invoicing']);
  });

  it('an id the list does not have is named by its id, never dropped', () => {
    expect(comesWith(app('x', { requires: ['ghost'] }), APPS)).toEqual(['ghost']);
  });

  it('an app it comes with that is blocked does not count', () => {
    const blockedInvoice = { ...INVOICE, state: 'blocked' as const, right: 'missing' as const };
    expect(includedWith(CUSTOMER, [TAX, CUSTOMER, blockedInvoice])).toEqual([]);
  });
});

describe('«Open»', () => {
  it('only for an app that is on and has a screen for this person', () => {
    expect([canOpen(TAX), canOpen(STOCK), canOpen(app('reports', { path: null }))]).toEqual([true, false, false]);
  });

  it('never for an app that stopped being on, even with a screen the list still names', () => {
    expect(canOpen(app('stock', { state: 'blocked', path: '/stock' }))).toBe(false);
  });
});

describe('turning an app on or off (PLAN-HUB §9)', () => {
  // sale needs tax and customer; both came along with it, and the business chose task itself.
  const SALE = app('sale', { name: 'Sales', requires: ['customer', 'tax'] });
  const TAX_ = app('tax', { name: 'Taxes', chosen: false, required_by: ['sale'] });
  const CUSTOMER_ = app('customer', { name: 'Customers', chosen: false, required_by: ['sale'] });
  const TASK = app('task', { name: 'Tasks' });
  const FLOW = app('flow', { name: 'Flows', state: 'off', chosen: false, path: null });
  const PAID = app('stock', { premium: true, right: 'missing', state: 'blocked', path: null });
  const ON = [SALE, TAX_, CUSTOMER_, TASK, FLOW, PAID];

  it('«Turn on» for an app that is off; «Turn off» for one that is on; neither for one without its right', () => {
    expect(ON.map((row) => [row.id, canTurnOn(row), canTurnOff(row)])).toEqual([
      ['sale', false, true],
      ['tax', false, true],
      ['customer', false, true],
      ['task', false, true],
      ['flow', true, false],
      ['stock', false, false],
    ]);
  });

  it('names what turns on with an app: what it needs that is off, by name', () => {
    const off = [{ ...SALE, state: 'off' as const, chosen: false }, { ...TAX_, state: 'off' as const }, CUSTOMER_];
    expect(turnsOnWith(off[0], off)).toEqual(['Taxes']);
    expect(turnsOnWith(TASK, ON)).toEqual([]);
  });

  it('names what goes off with an app: what came along with it and nothing else on needs', () => {
    expect(goesOffWith(SALE, ON)).toEqual(['Customers', 'Taxes']);
    const chosenTax = { ...TAX_, chosen: true };
    expect(goesOffWith(SALE, [SALE, chosenTax, CUSTOMER_])).toEqual(['Customers']);
    const invoice = app('invoice', { name: 'Invoicing', requires: ['customer', 'sale', 'tax'] });
    const needed = [SALE, { ...TAX_, required_by: ['invoice', 'sale'] }, { ...CUSTOMER_, required_by: ['invoice', 'sale'] }, invoice];
    expect(goesOffWith(invoice, needed)).toEqual([]);
  });

  it('names the apps to turn off first: the chosen ones on that need it, else every one that does', () => {
    expect(offFirst(TAX_, ON)).toEqual(['Sales']);
    const verifactu = app('verifactu', { name: 'VeriFactu', requires: ['invoice', 'sale', 'tax'] });
    const invoice = app('invoice', { name: 'Invoicing', chosen: false, requires: ['sale', 'tax'] });
    const tax = app('tax', { name: 'Taxes', chosen: false, required_by: ['invoice', 'sale', 'verifactu'] });
    expect(offFirst(tax, [verifactu, invoice, { ...SALE, chosen: false }, tax])).toEqual(['VeriFactu']);
    expect(offFirst(TASK, ON)).toEqual([]);
  });

  it('«My apps» lists only the apps on: one turned off is in «Add apps», with its icon and name', () => {
    expect(appsOfTab(ON, 'mine').map((row) => row.id)).toEqual(['sale', 'tax', 'customer', 'task']);
    expect(appsOfTab(ON, 'all').map((row) => row.id)).toContain('flow');
  });
});

describe('an app whose tables the business’s database is still getting (S3)', () => {
  // flow is being set up; website could not be; sale (being set up) needs customer, which came along with it.
  const FLOW = app('flow', { name: 'Flows', state: 'creating', path: null });
  const WEBSITE = app('website', { name: 'Website', state: 'failed', path: null });
  const SALE = app('sale', { name: 'Sales', state: 'creating', path: null, requires: ['customer'] });
  const CUSTOMER = app('customer', { name: 'Customers', state: 'creating', chosen: false, path: null, required_by: ['sale'] });
  const TASK = app('task', { name: 'Tasks' });
  const APPS = [FLOW, WEBSITE, SALE, CUSTOMER, TASK];

  it('«My apps» lists them with the ones on: the business turned them on', () => {
    expect(appsOfTab(APPS, 'mine').map((row) => row.id)).toEqual(['flow', 'website', 'sale', 'customer', 'task']);
  });

  it('nothing to turn on or open while one is being set up, but it can be turned off; one that failed is tried again or turned off', () => {
    expect(APPS.map((row) => [row.id, canTurnOn(row), canTurnOff(row), canRetry(row), canOpen(row)])).toEqual([
      ['flow', false, true, false, false],
      ['website', false, true, true, false],
      ['sale', false, true, false, false],
      ['customer', false, true, false, false],
      ['task', false, true, false, true],
    ]);
  });

  it('one being set up that needs another keeps it from going off, as one on does', () => {
    expect(offFirst(CUSTOMER, APPS)).toEqual(['Sales']);
    expect(includedWith(CUSTOMER, APPS)).toEqual(['Sales']);
  });
});

