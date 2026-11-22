// The tab bar of an app's pages is the part of its menu the person may open, as base.session.me sends it, through
// `useAppTabs(app)` (base/frontend/lib/app-tabs.ts). An app that writes its own list paints tabs its person cannot
// open, and its labels and icons drift from its menu's. This guard looks, app by app, for the two ways of writing one:
// a page whose `AppPage` takes its `tabs` from anything but `useAppTabs` of its own app, and a source that builds
// `ShellTab`s itself.
import { describe, expect, it } from 'vitest';

import { findingsByApp, hubFrontends } from './__tests__/frontend-sources';
import { NO_CLOCK } from '../../vitest.load';

/** The lines of `text` (a source of the app `app`) that give a tab bar another list than the session's. */
function ownTabLists(text: string, app: string): number[] {
  const lines = text.split('\n');
  const found: number[] = [];
  lines.forEach((line, index) => {
    const bound = /(?:^|\s)(?::|v-bind:)tabs="([^"]*)"/.exec(line);
    if (bound && !fromSession(text, bound[1].trim(), app)) found.push(index + 1);
    else if (/\bShellTab\b/.test(line)) found.push(index + 1);
  });
  return found;
}

/** Whether `name` is the result of `useAppTabs` for the app `app` in `text`. */
function fromSession(text: string, name: string, app: string): boolean {
  if (!/^[A-Za-z_$][\w$]*$/.test(name)) return false;
  return new RegExp(`\\bconst ${name} = useAppTabs\\('${app}'\\);`).test(text);
}

const APPS = hubFrontends({ ui: false }).filter((frontend) => frontend.app !== 'base');

describe('ownTabLists', () => {
  const page = (script: string, binding: string) =>
    `<script setup lang="ts">\n${script}\n</script>\n\n<template>\n  <AppPage\n    ${binding}\n  />\n</template>\n`;

  it("passes a page whose tabs are its own app's session tabs", () => {
    expect(ownTabLists(page("const tabs = useAppTabs('kitchen');", ':tabs="tabs"'), 'kitchen')).toEqual([]);
  });

  it('finds a page that writes its tabs, takes another app\'s or calls a list of its own', () => {
    expect(ownTabLists(page("const tabs = useAppTabs('sale');", ':tabs="tabs"'), 'kitchen')).toEqual([7]);
    expect(ownTabLists(page('', ':tabs="kitchenTabs($t, { settings: true })"'), 'kitchen')).toEqual([7]);
    expect(ownTabLists(page('', 'v-bind:tabs="[{ id: \'a\', label: \'A\', icon: \'ion:a\' }]"'), 'kitchen')).toEqual([7]);
  });

  it('finds a source that builds tabs itself', () => {
    const list = "import type { ShellTab } from '@erplora/ui/shell';\n\nexport const TABS: ShellTab[] = [];\n";
    expect(ownTabLists(list, 'kitchen')).toEqual([1, 3]);
  });
});

describe("every app's tab bar comes from the session", () => {
  it(
    'no app writes its own list of tabs',
    async () => {
      const found = await findingsByApp(APPS, (text, file) => {
        const app = APPS.find((frontend) => file.startsWith(`${frontend.dir}/`))?.app ?? '';
        return ownTabLists(text, app);
      });
      expect(found).toEqual({});
    },
    NO_CLOCK,
  );
});
