// What a template brings into a business, taken away again through the apps' own operations.
import { type BrowserContext, expect } from '@playwright/test';

import { api } from './hub-api';

/** What a template brings, last first (tables before their zones, products before their categories), each with
 * the operation's route that lists it and the one that takes a row away: the server's own (`base.blueprint`). */
const TEMPLATE_DATA = [
  ['/table/tables', '/table/tables/delete'],
  ['/table/zones', '/table/zones/delete'],
  ['/service/services', '/service/services/archive'],
  ['/service/categories', '/service/categories/delete'],
  ['/inventory/products', '/inventory/products/delete'],
  ['/inventory/categories', '/inventory/categories/delete'],
] as const;

/**
 * Takes away every row a template brings from the business at `origin`, through the apps' operations (their apps
 * on), until the server says the business is empty.
 */
export async function emptyOfTemplateData(context: BrowserContext, origin: string): Promise<void> {
  for (let pass = 0; pass < 5; pass += 1) {
    for (const [list, remove] of TEMPLATE_DATA) {
      const rows = await api<{ rows: { id: string }[] }>(context, origin, 'GET', `${list}?limit=100&offset=0`);
      expect(rows.status, list).toBe(200);
      for (const row of rows.data.rows) {
        const res = await api(context, origin, 'POST', remove, { id: row.id });
        expect(res.status, `${remove} ${row.id}`).toBeLessThan(300);
      }
    }
    const catalogue = await api<{ empty: boolean }>(context, origin, 'GET', '/settings/data/blueprints');
    if (catalogue.data.empty) return;
  }
  throw new Error('the business could not be emptied of what a template brings');
}
