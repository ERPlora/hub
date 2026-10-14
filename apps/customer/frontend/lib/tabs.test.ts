// The four sections of Customers (WORKBOOK «Pantallas»: Customers, Groups, Tags, Fields), painted as
// the footer tabbar of every customer page, as the product's module tabs were. Same paths and icons
// as the menu of apps.py, so the menu and the tabbar never disagree.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import en from '../locale/en.json';
import { customerTabs } from './tabs';

const APPS_PY = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'apps.py'), 'utf8');

const t = (key: string): string =>
  key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown>)[part], en) as string;

describe('customerTabs', () => {
  it('lists Customers, Groups, Tags and Fields, each following its route', () => {
    expect(customerTabs(t).map(({ id, label, to }) => [id, label, to])).toEqual([
      ['customers', 'Customers', '/customer/customers'],
      ['groups', 'Groups', '/customer/groups'],
      ['tags', 'Tags', '/customer/tags'],
      ['fields', 'Fields', '/customer/fields'],
    ]);
  });

  it('uses the product\'s icons where the shell registers them (Fields: layers-outline; Tags waits for pricetags)', () => {
    expect(customerTabs(t).map((tab) => tab.icon)).toEqual([
      'ion:people-outline',
      'ion:people-outline',
      'ion:list-outline',
      'ion:layers-outline',
    ]);
  });

  it('uses the icon of each menu entry in apps.py', () => {
    const menu = [...APPS_PY.matchAll(/Nav\(\s*id="(\w+)",[\s\S]*?icon="([^"]+)",[\s\S]*?path="([^"]+)"/g)].map((m) => [
      m[1],
      m[2],
      m[3],
    ]);
    expect(menu).toHaveLength(4);
    expect(customerTabs(t).map((tab) => [tab.id, tab.icon, tab.to])).toEqual(menu);
  });
});
