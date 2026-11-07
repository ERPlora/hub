// Every settings form of the Hub ends the same way (hub#897): the refusal's red notice, «Settings saved» and «Save»
// are `SettingsFormFooter` of `@erplora/ui/components`, painted from what `useSettingsForm` gives, one line per page.
// A page that writes that end by hand has to be fixed page by page each time it changes: hub#854 changed the red
// notice by hand in six pages and hub#873 in the seventh. This guard reads every `.vue` under `apps/*/frontend`
// (tests and their helpers left out) whose script builds its form with `useSettingsForm`, and there may be none that
// does not end it with `<SettingsFormFooter`.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const BASE_FRONTEND = dirname(fileURLToPath(import.meta.url));
const HUB = resolve(BASE_FRONTEND, '..', '..');
const APPS = join(HUB, 'apps');

/** Every `.vue` below `dir`, without `node_modules` and the tests' own folders. */
function vueFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === 'node_modules' || entry.name === '__tests__' ? [] : vueFiles(path);
    return entry.name.endsWith('.vue') ? [path] : [];
  });
}

/** The `.vue` files of the apps' frontends, relative to the hub, with their source. */
function appComponents(): { file: string; source: string }[] {
  return readdirSync(APPS, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .flatMap((app) => {
      const frontend = join(APPS, app.name, 'frontend');
      try {
        return vueFiles(frontend);
      } catch {
        return []; // An app without a frontend.
      }
    })
    .map((path) => ({ file: relative(HUB, path), source: readFileSync(path, 'utf8') }));
}

describe('settings forms end with SettingsFormFooter (hub#897)', () => {
  const forms = appComponents().filter(({ source }) => /\buseSettingsForm\s*\(/.test(source));

  it('finds the settings forms it guards', () => {
    expect(forms.length).toBeGreaterThan(0);
  });

  it('every form built on useSettingsForm paints its end with SettingsFormFooter, never by hand', () => {
    const byHand = forms.filter(({ source }) => !/<SettingsFormFooter\b/.test(source)).map(({ file }) => file);
    expect(byHand, 'end the form with <SettingsFormFooter :settings="…" testid="<app>-settings" … /> of @erplora/ui/components').toEqual([]);
  });
});
