// The two sections of the WhatsApp inbox (the WORKBOOK's screens; the old manifest's `navigation`):
// Inbox and Settings, as the footer tabbar of both pages. Each tab follows its route, has its icon (a
// registered one: an unregistered icon paints nothing) and its label in the reader's language.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { ION_ICONS } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { INBOX_TABS, inboxTabs } from './tabs';

function tabsIn(locale: 'en' | 'es') {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return inboxTabs((key) => i18n.global.t(key));
}

describe('the WhatsApp inbox tabbar', () => {
  it('is Inbox and Settings, each on its own route, the order of the menu (apps.py)', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['inbox', 'Inbox', '/whatsapp_inbox/inbox'],
      ['settings', 'Settings', '/whatsapp_inbox/settings'],
    ]);
  });

  it('speaks Spanish', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Bandeja de entrada', 'Ajustes']);
  });

  it('gives every tab a registered icon', () => {
    for (const tab of INBOX_TABS) expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
  });

  it('wears the same icons and paths as the menu entries of apps.py', () => {
    const appsPy = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'apps.py'), 'utf8');
    const menu = [...appsPy.matchAll(/"([a-z]+)",\s*pgettext_lazy\("whatsapp menu", "[^"]+"\),\s*"([^"]+)",\s*"([^"]+)"/g)].map((m) => [m[1], m[2], m[3]]);
    expect(menu).toEqual(INBOX_TABS.map((tab) => [tab.id, tab.icon, tab.to]));
  });
});
