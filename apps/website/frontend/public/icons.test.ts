// The public page's icons (the contact's chips, WhatsApp, the social profiles, the opening hours, the map, the stars of
// the Google reviews): Ionicons
// (`ion:`, the default set, MIT) exactly as @erplora/ui ships them (`ionicons/icons`), baked into site.css as CSS
// masks: the page has no script to paint them and no network for them (CSP `img-src 'self' data:`). Each
// `.ws-icon-<name>` sets `--ws-icon` to that icon's own data URL, and only filled shapes qualify: an outline icon draws
// its strokes through ion-icon's CSS classes (`ionicon-stroke-width`), which a mask never sees (X's mark carries
// `ionicon-fill-none` but no stroke: in a mask it is its filled letter, as the brand draws it).
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { describe, expect, it } from 'vitest';

const HERE = dirname(fileURLToPath(import.meta.url));
const SITE_CSS = readFileSync(join(HERE, 'site.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
const UI_PACKAGE = join(HERE, '..', '..', '..', '..', 'packages', 'ui', 'package.json');

/** Each hook and the Ionicons icon it is. */
const ICONS: Record<string, string> = {
  call: 'call',
  mail: 'mail',
  time: 'time',
  location: 'location',
  navigate: 'navigate',
  whatsapp: 'logoWhatsapp',
  instagram: 'logoInstagram',
  facebook: 'logoFacebook',
  tiktok: 'logoTiktok',
  x: 'logoX',
  star: 'star',
};

async function ionicons(): Promise<Record<string, string>> {
  const entry = createRequire(UI_PACKAGE).resolve('ionicons/icons');
  return (await import(pathToFileURL(entry).href)) as Record<string, string>;
}

const written = new Map(
  [...SITE_CSS.matchAll(/\.ws-icon-([a-z]+)\s*\{\s*--ws-icon:\s*url\("([^"]+)"\);?\s*\}/g)].map(([, name, url]) => [name, url]),
);

describe('the public website’s icons', () => {
  it('site.css has each icon the templates paint, and no other', () => {
    expect([...written.keys()].sort()).toEqual(Object.keys(ICONS).sort());
    const hooks = [...SITE_CSS.matchAll(/\.(ws-icon-[a-z0-9-]+)/g)].map(([, hook]) => hook);
    expect(new Set(hooks)).toEqual(new Set(Object.keys(ICONS).map((name) => `ws-icon-${name}`)));
  });

  it.each(Object.entries(ICONS))('ws-icon-%s is Ionicons’ «%s», filled, as @erplora/ui ships it', async (name, icon) => {
    const ion = await ionicons();
    expect(written.get(name)).toBe(ion[icon]);
    expect(ion[icon]).toMatch(/^data:image\/svg\+xml;utf8,<svg /);
    expect(ion[icon]).not.toMatch(/ionicon-stroke-width|"/);
  });
});
