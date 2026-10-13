// `pnpm gen:app-icons` (scripts/app-icons.mjs) bakes the `icon` of every module's apps.py into
// frontend/generated/app-icons.json (round 16, spec §4.6): `register_apps` copies each one into
// `shared.app.icon_svg`, which the SaaS paints inline after cleaning it with nh3. It is versioned,
// not a build output: register_apps needs it locally without building the frontend, and in the
// image's Python stage, which has no node_modules. The sources are the shell's own icon packages,
// resolved from @erplora/ui: `ionicons/icons` for `ion:`, `@iconify-json/*` for the other sets.
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { APP_ICONS_PATH, bakeIcon, buildAppIcons, moduleIcons, renderAppIcons } from '../../scripts/app-icons.mjs';

const HUB_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

function hubWith(files: Record<string, string>): string {
  const root = mkdtempSync(join(tmpdir(), 'app-icons-'));
  for (const [name, source] of Object.entries(files)) {
    const path = join(root, name);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, source);
  }
  return root;
}

describe('app-icons', () => {
  it('writes frontend/generated/app-icons.json, next to operations.json', () => {
    expect(APP_ICONS_PATH).toBe(join(HUB_DIR, 'frontend', 'generated', 'app-icons.json'));
  });

  it('keeps the committed JSON in step with the apps.py files and their packages (run `pnpm gen:app-icons`)', () => {
    // A missing icon, an extra one or an SVG that is not the package's all break this equality.
    expect(readFileSync(APP_ICONS_PATH, 'utf8')).toBe(renderAppIcons(buildAppIcons(HUB_DIR)));
    expect(Object.keys(JSON.parse(readFileSync(APP_ICONS_PATH, 'utf8')))).toEqual(moduleIcons(HUB_DIR));
  });

  it("reads each module's `icon = \"…\"`, not its menu's icons, sorted and once each", () => {
    const root = hubWith({
      'apps/stock/apps.py': 'class StockConfig(LiveAppConfig):\n    icon = "ion:cube-outline"\n    navigation = [Nav(id="s", label=_("S"), icon="ion:list-outline", path="/s")]\n',
      'apps/cart/apps.py': "class CartConfig(LiveAppConfig):\n    icon = 'mdi:cart'\n",
      'apps/same/apps.py': 'class SameConfig(LiveAppConfig):\n    icon="ion:cube-outline"\n',
      'apps/empty/__init__.py': '',
      'base/apps.py': 'class BaseConfig(LiveAppConfig):\n    icon = "ion:home-outline"\n',
    });

    expect(moduleIcons(root)).toEqual(['ion:cube-outline', 'mdi:cart']);
  });

  it('bakes an Ionicon self-contained: a whole SVG, its classes as attributes, painted in currentColor', () => {
    // ion-icon's shadow CSS gives `.ionicon-fill-none` fill none, `.ionicon-stroke-width` 32px and the
    // root fill and stroke currentColor; the SaaS has no such CSS, so the attributes carry it.
    const svg = bakeIcon('ion:flask-outline');
    expect(svg.startsWith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" fill="currentColor">')).toBe(true);
    expect(svg.endsWith('</svg>')).toBe(true);
    expect(svg).toContain("<g stroke='currentColor'><path ");
    expect(svg).toContain("fill='none' stroke-width='32'");
    expect(svg).not.toContain('class=');
  });

  it('bakes an icon of the other Iconify sets from @iconify-json with its own viewBox', () => {
    const svg = bakeIcon('mdi:cart');
    expect(svg.startsWith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path ')).toBe(
      true,
    );
    expect(bakeIcon('lucide:box')).toContain('stroke="currentColor"');
  });

  it('fails on an icon or a set the shell does not have', () => {
    expect(() => bakeIcon('ion:no-such-icon')).toThrow('ion:no-such-icon');
    expect(() => bakeIcon('mdi:no-such-icon')).toThrow('mdi:no-such-icon');
    expect(() => bakeIcon('heroicons:home')).toThrow('heroicons:home');
  });

  it('bakes no class and no script into any committed icon', () => {
    for (const svg of Object.values(JSON.parse(readFileSync(APP_ICONS_PATH, 'utf8')) as Record<string, string>)) {
      expect(svg).not.toMatch(/class=|<script|\son[a-z]+=|href=/i);
    }
  });
});
