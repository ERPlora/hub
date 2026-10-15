// The sections of Payments (WORKBOOK «Pantallas»): Payments and Methods, as the footer tabbar of every
// payment page. Each tab follows its route and wears a registered icon, the same as the menu's.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { resolveIcon } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { PAYMENT_TABS, paymentTabs } from './tabs';

function tabsIn(locale: 'en' | 'es') {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return paymentTabs((key) => i18n.global.t(key));
}

describe('the payment tabbar', () => {
  it('is Payments and Methods, each on its own route', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['payments', 'Payments', '/payment/payments'],
      ['methods', 'Methods', '/payment/methods'],
    ]);
  });

  it('speaks Spanish', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Pagos', 'Métodos']);
  });

  it('gives every tab a registered icon', () => {
    for (const tab of PAYMENT_TABS) expect(resolveIcon(tab.icon), tab.icon).toBeTruthy();
  });

  it('wears the same icons and paths as the menu entries of apps.py (one icon per section everywhere)', () => {
    const appsPy = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'apps.py'), 'utf8');
    const menu = [...appsPy.matchAll(/Nav\(\s*"([a-z_]+)",\s*_\("[^"]+"\),\s*"([^"]+)",\s*"([^"]+)",?\s*\)/g)].map((m) => [m[1], m[2], m[3]]);
    expect(menu).toEqual(PAYMENT_TABS.map((tab) => [tab.id, tab.icon, tab.to]));
  });
});
