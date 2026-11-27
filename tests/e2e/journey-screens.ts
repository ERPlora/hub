// The screens of the salon's and the restaurant's QA journeys (qa/journeys/), for screens-text-fits.spec.ts: the apps
// whose flows those journeys cite, and of the routes the Hub registers, each page of theirs that opens behind a session
// with no parameter. Base's pages are those under no app's path.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page } from '@playwright/test';

const HUB_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const JOURNEYS = join(HUB_DIR, 'qa', 'journeys');
/** The journeys of the two kinds of business the product sells to. */
const KINDS = /^(salon|restaurant)-.+\.md$/;

/** A route as the Hub's router has it. */
export interface RouteInfo {
  path: string;
  redirect: boolean;
  meta: Record<string | number | symbol, unknown>;
}

/** The apps whose flows (`<APP>-F<nn>`) the salon and restaurant journeys cite, in alphabetical order. */
export function journeyApps(): string[] {
  const apps = new Set<string>();
  for (const file of readdirSync(JOURNEYS).filter((name) => KINDS.test(name))) {
    for (const flow of readFileSync(join(JOURNEYS, file), 'utf8').matchAll(/\b([A-Z][A-Z_]*)-F\d+\b/g)) apps.add(flow[1].toLowerCase());
  }
  return [...apps].sort();
}

/** The apps of the Hub: each folder of `apps/`. */
const APPS = new Set(readdirSync(join(HUB_DIR, 'apps'), { withFileTypes: true }).filter((entry) => entry.isDirectory()).map((entry) => entry.name));

/** The app a path belongs to (`/sale/pos` → `sale`), or `base` when it is under no app. */
const appOf = (path: string): string => {
  const first = path.split('/')[1] ?? '';
  return APPS.has(first) ? first : 'base';
};

/** The pages of `apps` among `routes`: behind a session, in the app's frame, with no parameter and no redirect. */
export function screensAmong(routes: RouteInfo[], apps: string[]): string[] {
  const wanted = new Set(apps);
  const screens = routes.filter(
    (route) =>
      route.meta.auth === true && route.meta.chrome !== false && !route.redirect && !route.path.includes(':') && wanted.has(appOf(route.path)),
  );
  return [...new Set(screens.map((route) => route.path))];
}

/** The routes the Hub's router registered, read from the mounted app in the page. */
export async function registeredRoutes(page: Page): Promise<RouteInfo[]> {
  await page.waitForFunction(() => !!(document.querySelector('#app') as { __vue_app__?: unknown } | null)?.__vue_app__);
  return page.evaluate(() => {
    const mounted = document.querySelector('#app') as (Element & { __vue_app__?: { config: { globalProperties: Record<string, unknown> } } }) | null;
    const router = mounted?.__vue_app__?.config.globalProperties.$router as
      | { getRoutes(): { path: string; redirect?: unknown; meta: Record<string, unknown> }[] }
      | undefined;
    if (!router) throw new Error('registeredRoutes: the Hub’s router is not mounted on #app');
    return router.getRoutes().map((route) => ({ path: route.path, redirect: !!route.redirect, meta: { ...route.meta } }));
  });
}
