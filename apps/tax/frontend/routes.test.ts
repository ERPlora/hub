// The tax app's `routes.ts`: its three sections → their pages, behind a session, and nothing else
// (main.ts reads the default export; menu, permissions and active apps come from the server).
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it, vi } from 'vitest';

import { menuPaths, routeChecks } from '../../../base/frontend/__tests__/app-routes';
import routes from './routes';

// The pages, stubbed: `routeChecks` checks which one each route loads (app-routes.ts says why).
vi.mock('./pages/CategoriesPage.vue', () => ({ default: { name: 'CategoriesPage' } }));
vi.mock('./pages/RulesPage.vue', () => ({ default: { name: 'RulesPage' } }));
vi.mock('./pages/AliasesPage.vue', () => ({ default: { name: 'AliasesPage' } }));
vi.mock('./pages/SettingsPage.vue', () => ({ default: { name: 'SettingsPage' } }));

const HERE = dirname(fileURLToPath(import.meta.url));

describe('tax routes.ts', () => {
  it('maps Categories, Rules, Aliases and Settings (the paths of the menu in apps.py), all behind a session', () => {
    expect(routes.map((r) => [r.path, r.meta?.auth])).toEqual([
      ['/tax/categories', true],
      ['/tax/rules', true],
      ['/tax/aliases', true],
      ['/tax/settings', true],
    ]);
  });

  routeChecks(import.meta.url, routes, ['CategoriesPage', 'RulesPage', 'AliasesPage', 'SettingsPage']);

  it('matches the navigation of apps.py, entry for entry', () => {
    expect(menuPaths('tax')).toEqual(routes.map((r) => r.path));
  });

  it('has a page where the Home sends its step «Your taxes» (the `route` of apps.py)', () => {
    const appsPy = readFileSync(join(HERE, '..', 'apps.py'), 'utf8');
    const sent = [...appsPy.matchAll(/route="(\/tax\/[a-z]+)"/g)].map((m) => m[1]);
    expect(sent).toEqual(['/tax/rules']);
    expect(routes.map((r) => r.path)).toContain(sent[0]);
  });
});
