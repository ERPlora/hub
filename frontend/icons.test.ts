// Icon guardrail of the hub (PLAN §16.4): an icon that is not registered in @erplora/ui's shell
// paints NOTHING (no network for icons, by CSP), so a page, a component or an app's menu that names
// one must fail a test, not a till. `scanIcons` is the reader @erplora/ui runs on itself; here it
// reads the hub's own sources. It resolves icons through the baked `~icons/*` modules, so it needs
// the `erploraVite()` plugins of vite.config.ts.
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { scanIcons } from '@erplora/ui/testing';
import { describe, expect, it } from 'vitest';

/** The root of hub-next: the globs below are relative to it. */
const HUB_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');
/** Where the hub names icons: the apps' pages and components, the shell entry and each app's menu. */
const SOURCES = ['apps/*/frontend/**/*.vue', 'apps/*/frontend/**/*.ts', 'frontend/**/*.ts', 'apps/*/apps.py'];

describe('guardrail: every icon the hub names is registered', () => {
  it('every icon named in the apps, the entry and the menus is registered, and every glob reads something', () => {
    expect(scanIcons({ root: HUB_DIR, sources: SOURCES })).toEqual({ unregistered: [], emptyGlobs: [] });
  });
});
