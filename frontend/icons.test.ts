// Icon guardrail of the hub (PLAN §16.4): an icon that is not registered in @erplora/ui's shell
// paints NOTHING (no network for icons, by CSP), so a page, a component or an app's menu that names
// one must fail a test, not a till. `scanIcons` is the reader @erplora/ui runs on itself; here it
// reads the hub's own sources. It resolves icons through the baked `~icons/*` modules, so it needs
// the `erploraVite()` plugins of vite.config.ts.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { isRegisteredIcon, scanIcons } from '@erplora/ui/testing';
import { describe, expect, it } from 'vitest';

/** The root of hub-next: the globs below are relative to it. */
const HUB_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');
/** Where the hub names icons: base's Home, the apps' pages and components, the shell entry and each app's menu. */
const SOURCES = [
  'base/frontend/**/*.vue',
  'base/frontend/**/*.ts',
  'apps/*/frontend/**/*.vue',
  'apps/*/frontend/**/*.ts',
  'frontend/**/*.ts',
  'apps/*/apps.py',
];

/** A Python string that names an icon of one of the sets the shell bakes (`"ion:grid-outline"`). */
const ICON_LITERAL = /"((?:ion|material-symbols|mdi|heroicons|tabler|lucide|fa):[a-z0-9-]+)"/g;

describe('guardrail: every icon the hub names is registered', () => {
  // `scanIcons` reads each of the ~700 sources once, from the disk, so its time is the machine's: with several
  // test runs on one machine (load 20–40) and every opened file scanned, it took up to 7.5 s (2026-10-21),
  // against Vitest's 5 s. 60 s, as the other guardrails that read the whole tree (tsconfig.test.ts).
  it('every icon named in the apps, the entry and the menus is registered, and every glob reads something', () => {
    expect(scanIcons({ root: HUB_DIR, sources: SOURCES })).toEqual({ unregistered: [], emptyGlobs: [] });
  }, 60_000);

  // base's Python names the icons of its platform steps and counters as plain strings (`"icon": "ion:…"` of a
  // counter, `DEFAULT_STEP_ICON`), which `scanIcons` does not read; HubIcon throws on an unknown one, so a typo
  // there would take the whole Home down.
  it('every icon base names in its Python is registered', () => {
    const base = join(HUB_DIR, 'base');
    const names = readdirSync(base)
      .filter((file) => file.endsWith('.py'))
      .flatMap((file) => [...readFileSync(join(base, file), 'utf8').matchAll(ICON_LITERAL)].map((m) => m[1]));
    expect(names.length).toBeGreaterThanOrEqual(4);
    expect(names.filter((name) => !isRegisteredIcon({ kind: 'icon', name }))).toEqual([]);
  });

  // An app's apps.py names the icons of its menu (the positional `Nav("id", _("Label"), "ion:…", "/path")`) and of
  // its Home hooks (`"icon": "ion:…"` of a setup step, a widget, a bell counter) as plain strings, which
  // `scanIcons` does not read either; the menu, the apps tiles and the Home paint them with HubIcon, so an
  // unregistered one leaves the entry without its icon (old hub#160). The module's own `icon = "…"` is not one:
  // only the store shows it, from the SVG `pnpm gen:app-icons` bakes (base/catalog.py).
  it('every icon an app names in its apps.py, but its store icon, is registered', () => {
    const apps = join(HUB_DIR, 'apps');
    const named = readdirSync(apps)
      .filter((app) => existsSync(join(apps, app, 'apps.py')))
      .flatMap((app) =>
        readFileSync(join(apps, app, 'apps.py'), 'utf8')
          .split('\n')
          .filter((line) => !/^\s*icon\s*=/.test(line))
          .flatMap((line) => [...line.matchAll(ICON_LITERAL)].map((m) => [app, m[1]])),
      );
    expect(named.length).toBeGreaterThanOrEqual(20);
    expect(named.filter(([, name]) => !isRegisteredIcon({ kind: 'icon', name }))).toEqual([]);
  });
});
