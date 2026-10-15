// The three sections of Invoicing (the WORKBOOK's screens; the old manifest's `navigation` plus the new
// Issuer): Invoices, Series and Issuer, as the footer tabbar of every invoice page. Each tab follows its
// route, has its icon (a registered one: an unregistered icon paints nothing) and its label in the
// reader's language.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { ION_ICONS } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { INVOICE_TABS, invoiceTabs } from './tabs';

function tabsIn(locale: 'en' | 'es') {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return invoiceTabs((key) => i18n.global.t(key));
}

describe('the invoice tabbar', () => {
  it('is Invoices, Series and Issuer, each on its own route, the order of the menu (apps.py)', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['invoices', 'Invoices', '/invoice/invoices'],
      ['series', 'Series', '/invoice/series'],
      ['issuer', 'Issuer', '/invoice/issuer'],
    ]);
  });

  it('speaks Spanish', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Facturas', 'Series', 'Emisor']);
  });

  it('gives every tab a registered icon', () => {
    for (const tab of INVOICE_TABS) expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
  });

  it('wears the same icons and paths as the menu entries of apps.py (one icon per section everywhere)', () => {
    const appsPy = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'apps.py'), 'utf8');
    const menu = [...appsPy.matchAll(/Nav\(\s*"([a-z]+)",\s*_\("[^"]+"\),\s*"([^"]+)",\s*"([^"]+)"\s*\)/g)].map((m) => [m[1], m[2], m[3]]);
    expect(menu).toEqual(INVOICE_TABS.map((tab) => [tab.id, tab.icon, tab.to]));
  });
});
