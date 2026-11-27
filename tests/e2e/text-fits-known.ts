// The sites screens-text-fits.spec.ts already knows cut a text (text-fits-known.json), each with what it is and the
// issue that fixes it. A site is a box on the screens listed, at whatever size. The spec fails on a text cut anywhere
// else, and on a site that no longer cuts on one of its screens until that screen leaves the list;
// tests/test_guardrails_text_fits.py refuses a box or a screen the list did not have on main.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export interface KnownSite {
  box: string;
  screens: readonly string[];
  issue: string;
  what: string;
}

export const KNOWN_SITES: readonly KnownSite[] = JSON.parse(
  readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'text-fits-known.json'), 'utf8'),
) as KnownSite[];

/** The screens of each known site where it no longer cuts, as `<box> on <screen>`. */
export function staleScreens(cuts: readonly { box: string; screen: string }[]): string[] {
  return KNOWN_SITES.flatMap((site) =>
    site.screens.filter((screen) => !cuts.some((cut) => cut.box === site.box && cut.screen === screen)).map((screen) => `${site.box} on ${screen}`),
  );
}
