// @vitest-environment node
// Guardrail of the way out of the Hub (gh:hub#439): a link that opens another page in a new tab (`target="_blank"`)
// works in a browser by itself, but the installed app opens nothing on `_blank` (its webview spawns no window): the
// owner tapped «Invite on erplora.com» and «Change on erplora.com» on the tablet and nothing happened. The one way
// out is `openExternalLink` of `@erplora/ui/shell` on the link's click (TopbarChrome's «erplora.com»): in the app it
// hands the address to the system browser (`open_external_url`) and says so when it cannot. Every `_blank` link of
// base and of the apps goes that way, called on its `@click` or from the function its `@click` names; a
// `window.open(…, '_blank')` has no such way and is not written. The files still waiting, each with its issue, are
// listed below; a fixed one leaves the list (the test fails while it stays).
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

/** The root of the hub: the folders below are relative to it. */
const HUB_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');

/** What the SPA paints: base's frontend and every app's (not the apps' public pages for visitors, never in the app). */
function sources(): string[] {
  const roots = [join(HUB_DIR, 'base', 'frontend')];
  for (const app of readdirSync(join(HUB_DIR, 'apps'), { withFileTypes: true })) {
    if (app.isDirectory()) roots.push(join(HUB_DIR, 'apps', app.name, 'frontend'));
  }
  return roots
    .flatMap((root) => {
      try {
        return readdirSync(root, { recursive: true, encoding: 'utf8' }).map((file) => join(root, file));
      } catch {
        return [];
      }
    })
    .filter((file) => /\.(vue|ts)$/.test(file) && !/\.(test|spec)\.ts$/.test(file) && !/\.d\.ts$/.test(file))
    .filter((file) => !file.includes(`${join('frontend', 'public')}/`) && !file.includes('__tests__'))
    .map((file) => relative(HUB_DIR, file))
    .sort();
}

/** The files whose `_blank` links still wait for the common way, and why (each one, an issue). */
const WAITING: Readonly<Record<string, string>> = {};

/** An opening tag, with attribute values that may hold a `>` (`@click="a > b"`). */
const OPENING_TAG = /<([a-zA-Z][\w-]*)((?:\s+[^\s=>"'/]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>"']+))?)*)\s*\/?>/g;
/** `target="_blank"`, or a bound target whose expression can give `_blank`. */
const NEW_TAB = /(?:^|\s)(?:target\s*=\s*["']_blank["']|(?::|v-bind:)target\s*=\s*"[^"]*_blank[^"]*")/;
/** The click handler of a tag: `@click`, `@click.prevent`, `v-on:click`… */
const CLICK = /(?:^|\s)(?:@|v-on:)click(?:\.[\w.]+)?\s*=\s*"([^"]*)"/;
const WINDOW_OPEN_BLANK = /\bwindow\.open\s*\([^)]*['"]_blank['"]/g;

function lineOf(source: string, index: number): number {
  return source.slice(0, index).split('\n').length;
}

/** Whether the function `name` defined in `source` (declared or as an arrow) calls `openExternalLink`. */
function handlerOpensOutside(source: string, name: string): boolean {
  const start = source.search(new RegExp(`(?:function\\s+${name}\\s*\\(|const\\s+${name}\\s*=)`));
  if (start < 0) return false;
  const end = source.indexOf('\n}', start);
  return /\bopenExternalLink\s*\(/.test(source.slice(start, end < 0 ? undefined : end));
}

/** Whether a tag's click goes the common way: `openExternalLink(…)` itself, or a function of the file that calls it. */
function clickOpensOutside(source: string, tag: string): boolean {
  const handler = CLICK.exec(tag)?.[1].trim();
  if (!handler) return false;
  if (/\bopenExternalLink\s*\(/.test(handler)) return true;
  const named = /^([A-Za-z_$][\w$]*)(?:\s*\(.*\))?$/.exec(handler)?.[1];
  return named !== undefined && handlerOpensOutside(source, named);
}

/** The `_blank` links of a source that skip the common way (`<line>`), and how many go by it. */
function scan(source: string): { stray: number[]; through: number } {
  const stray: number[] = [];
  let through = 0;
  for (const match of source.matchAll(OPENING_TAG)) {
    if (!NEW_TAB.test(match[2])) continue;
    if (clickOpensOutside(source, match[2])) through += 1;
    else stray.push(lineOf(source, match.index));
  }
  for (const match of source.matchAll(WINDOW_OPEN_BLANK)) stray.push(lineOf(source, match.index));
  return { stray: stray.sort((a, b) => a - b), through };
}

describe('the scanner of the way out', () => {
  it('catches a `_blank` link without the common way, static or bound, and a `window.open` to a new tab', () => {
    expect(scan('<a :href="url" target="_blank" rel="noopener">x</a>').stray).toEqual([1]);
    expect(scan('<ion-button\n  :href="url"\n  target="_blank"\n>x</ion-button>').stray).toEqual([1]);
    expect(scan(`<a :target="item.href ? '_blank' : undefined" :href="item.href">x</a>`).stray).toEqual([1]);
    expect(scan('<a :href="url" target="_blank" @click="track()">x</a>\nfunction track() {\n  count += 1;\n}').stray).toEqual([1]);
    expect(scan("const go = () => window.open(url, '_blank', 'noopener');").stray).toEqual([1]);
  });

  it('takes the link whose click calls `openExternalLink`, or names a function of the file that does', () => {
    expect(scan('<a :href="url" target="_blank" @click="openExternalLink(url, $event)">x</a>')).toEqual({ stray: [], through: 1 });
    const named = '<ion-item :href="url" target="_blank" @click="openIt">x</ion-item>\nfunction openIt(event: Event): void {\n  open.value = false;\n  openExternalLink(url, event);\n}';
    expect(scan(named)).toEqual({ stray: [], through: 1 });
    expect(scan('<a :href="url" @click="a > b && openExternalLink(url, $event)" target="_blank">x</a>')).toEqual({ stray: [], through: 1 });
  });

  it('leaves alone a link that stays in the page', () => {
    expect(scan('<a :href="url" rel="noopener">x</a><ion-button :href="url">y</ion-button>')).toEqual({ stray: [], through: 0 });
  });
});

describe('guardrail: every link of the Hub to another page goes by `openExternalLink`', () => {
  const found = sources().map((file) => ({ file, ...scan(readFileSync(join(HUB_DIR, file), 'utf8')) }));

  it('no `_blank` link skips it, besides the files still waiting with their issue', () => {
    const stray = found
      .filter(({ file, stray }) => stray.length > 0 && !(file in WAITING))
      .flatMap(({ file, stray }) => stray.map((line) => `${file}:${line}`));
    expect(stray).toEqual([]);
  });

  it('a file of the waiting list still waits: once fixed it leaves the list', () => {
    const fixed = Object.keys(WAITING).filter((file) => !found.some((entry) => entry.file === file && entry.stray.length > 0));
    expect(fixed).toEqual([]);
  });

  it('reads the links it guards: erplora.com of the bar, inviting, roles, the business, the plan and the apps', () => {
    const through = Object.fromEntries(found.filter((entry) => entry.through > 0).map((entry) => [entry.file, entry.through]));
    expect(through).toMatchObject({
      'base/frontend/components/TopbarChrome.vue': 2,
      'base/frontend/components/PeopleList.vue': 2,
      'base/frontend/components/RolesList.vue': 1,
      'base/frontend/components/settings/BusinessPanel.vue': 1,
      'base/frontend/pages/PersonPage.vue': 1,
      'base/frontend/components/UpgradePlanLink.vue': 1,
      'base/frontend/pages/AppsPage.vue': 2,
      'base/frontend/pages/AppBlockedPage.vue': 1,
      'base/frontend/pages/LoginPage.vue': 1,
    });
  });
});
