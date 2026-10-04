// A tabbed page only syncs its tab with an address that is ITS OWN (hub#2444).
//
// This is the PATTERN guard behind `lib/hash-tab.ts`. Ionic keeps every visited page mounted and
// `useRoute()` is the app's one route, so a page that watches `route.hash` without its path reads
// the NEXT page's hash as one of its own tabs and rewrites it: Settings and Employees sent a link to
// System → Updates to System → Resources, Billing/Dashboard did it from any non-default tab, and
// Apps flipped itself back to «My apps» behind the scenes. Five pages had copied the same watcher.
//
// Fixing the five files fixes today. This sweep fixes the page somebody adds next month: a raw
// `watch(() => route.hash, …)` in a view is named here, and so is a `useHashTab` that guards the
// wrong path (a copy-pasted '/settings' on a new page would never sync at all).
import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = fileURLToPath(new URL('.', import.meta.url));
const VIEWS = join(SRC, 'views');

/** A watcher whose only source is the hash: it fires for every page's address. */
const RAW_HASH_WATCH = /watch\(\s*\(\)\s*=>\s*route\.hash\s*,/;
const USE_HASH_TAB = /useHashTab(?:<[^>]*>)?\(\s*'([^']+)'/g;

function views(): Array<{ file: string; source: string }> {
  return readdirSync(VIEWS)
    .filter((f) => f.endsWith('.vue'))
    .map((file) => ({ file, source: readFileSync(join(VIEWS, file), 'utf8') }));
}

/** `/settings` → `SettingsPage.vue`, read from the router table itself. */
function routedViews(): Map<string, string> {
  const router = readFileSync(join(SRC, 'router', 'index.ts'), 'utf8');
  const out = new Map<string, string>();
  for (const m of router.matchAll(/path:\s*'([^']+)'[^\n]*?import\('\.\.\/views\/([A-Za-z]+\.vue)'\)/g)) {
    out.set(m[2], m[1]);
  }
  return out;
}

describe('tabbed pages own their address (hub#2444)', () => {
  it('no view watches the hash alone', () => {
    const offenders = views().filter((v) => RAW_HASH_WATCH.test(v.source)).map((v) => v.file);
    expect(offenders).toEqual([]);
  });

  it('every useHashTab guards the path the router gives that view', () => {
    const routes = routedViews();
    const wrong: string[] = [];
    let calls = 0;
    for (const { file, source } of views()) {
      for (const m of source.matchAll(USE_HASH_TAB)) {
        calls += 1;
        if (routes.get(file) !== m[1]) wrong.push(`${file}: '${m[1]}' (router: '${routes.get(file)}')`);
      }
    }
    expect(wrong).toEqual([]);
    // Apps, Billing, Dashboard, Employees, Settings — a sweep that matched nothing proves nothing.
    expect(calls).toBeGreaterThanOrEqual(5);
  });

  it('catches the raw watcher it is meant to catch', () => {
    expect(RAW_HASH_WATCH.test("watch(() => route.hash, (h) => {")).toBe(true);
    expect(RAW_HASH_WATCH.test('watch(\n  () => route.hash,\n  (h) => {')).toBe(true);
    expect(RAW_HASH_WATCH.test('watch([() => route.path, () => route.hash], ([path, h]) => {')).toBe(false);
  });
});
