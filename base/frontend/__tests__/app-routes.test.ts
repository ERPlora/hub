import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { describe, expect, it } from 'vitest';
import type { RouteRecordRaw } from 'vue-router';

import { menuPaths, namedPaths, routeChecks, valueImports } from './app-routes';

/** A test beside a real `routes.ts` (Taxes', which imports types only), for the check that reads that file. */
const BESIDE_TAX_ROUTES = pathToFileURL(join(dirname(fileURLToPath(import.meta.url)), '../../../apps/tax/frontend/routes.test.ts')).href;
const page = (name: string) => () => Promise.resolve({ default: { name } });
const ROUTES: RouteRecordRaw[] = [
  { path: '/stock/items', component: page('ItemsPage') },
  { path: '/stock/settings', component: page('SettingsPage') },
];

describe('the checks every routes.ts shares', () => {
  routeChecks(BESIDE_TAX_ROUTES, ROUTES, ['ItemsPage', 'SettingsPage']);
});

describe('valueImports', () => {
  it('finds the imports that bring values and leaves out those of types only', () => {
    const source = "import type { RouteRecordRaw } from 'vue-router';\nimport routes from './routes';\nconst x = 1;\n";
    expect(valueImports(source)).toEqual(["import routes from './routes';"]);
  });
});

describe('what apps.py names', () => {
  it("reads the paths of an app's menu, in order", () => {
    expect(menuPaths('tax')).toEqual(['/tax/categories', '/tax/rules', '/tax/aliases', '/tax/settings']);
  });

  it('reads every path of an app that apps.py names, menu or not, once each', () => {
    expect(namedPaths('tax')).toEqual(['/tax/categories', '/tax/rules', '/tax/aliases', '/tax/settings']);
    expect(namedPaths('appointment')).toEqual(['/appointment/agenda', '/appointment/settings']);
  });
});
