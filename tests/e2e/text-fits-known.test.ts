// A known site of text-fits-known.json leaves the list screen by screen: screens-text-fits.spec.ts names each screen
// where its box no longer cuts, even while it still cuts on the others.
import { describe, expect, it } from 'vitest';

import { KNOWN_SITES, staleScreens } from './text-fits-known';

const everyCut = KNOWN_SITES.flatMap((site) => site.screens.map((screen) => ({ box: site.box, screen })));
const widest = [...KNOWN_SITES].sort((a, b) => b.screens.length - a.screens.length)[0];

describe('staleScreens: the screens where a known site no longer cuts', () => {
  it('names none while each site still cuts on every one of its screens', () => {
    expect(staleScreens(everyCut)).toEqual([]);
  });

  it('names the one screen a site no longer cuts on, though it still cuts on the others', () => {
    expect(widest.screens.length, 'a site known on several screens').toBeGreaterThan(1);
    const fixed = widest.screens[0];
    const cuts = everyCut.filter((cut) => !(cut.box === widest.box && cut.screen === fixed));
    expect(staleScreens(cuts)).toEqual([`${widest.box} on ${fixed}`]);
  });

  it('does not keep a site for another box cut on its screen', () => {
    const [site] = KNOWN_SITES;
    const cuts = everyCut.map((cut) => (cut.box === site.box ? { ...cut, box: 'span.other' } : cut));
    expect(staleScreens(cuts)).toEqual(site.screens.map((screen) => `${site.box} on ${screen}`));
  });
});
