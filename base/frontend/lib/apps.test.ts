// The rules of the Apps screen (BASE-G67…G74) the browser applies to `base.app.list`: which apps each tab lists,
// the tab of an address, what comes along with an app, who it comes with, and when «Open» is offered.
import { describe, expect, it } from 'vitest';

import type { AppRow } from '../operations';
import { appsOfTab, canOpen, comesWith, includedWith, tabOf, TAB_HASH } from './apps';

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
    expect([tabOf(''), tabOf('#all'), tabOf('#paid'), tabOf('#other')]).toEqual(['mine', 'all', 'paid', 'mine']);
    expect(TAB_HASH).toEqual({ mine: '', all: '#all', paid: '#paid' });
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
});
