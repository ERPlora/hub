import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

// The other half of hub#794: that the heading reaches EVERY screen, and lands twice on none.
//
// `AppTopbar.heading.test.ts` mounts the toolbar and checks it announces itself as the level-1
// heading. This one checks the wiring that carries that to the ten screens — and it reads the
// source rather than mounting each view, because the thing to defend is a DEFAULT: a screen has to
// opt OUT of the heading, never opt in. Opt-in is what left eight screens without one, each waiting
// for somebody to remember it.
const COMPONENTS = fileURLToPath(new URL('.', import.meta.url));
const appPage = readFileSync(join(COMPONENTS, 'AppPage.vue'), 'utf8');

describe('the layout carries the heading to every screen', () => {
  it('AppPage hands the toolbar the answer, defaulting to «this screen has no heading of its own»', () => {
    expect(appPage).toContain(':title-is-heading="!headingOnScreen"');
    expect(appPage).toContain('headingOnScreen?: boolean');
    expect(appPage).toContain('headingOnScreen: false');
  });

  it('and the ONLY two screens that opt out are the two with their own <h1>', () => {
    // Who knows a screen already paints a heading is the VIEW, never the toolbar — the same
    // reasoning `AppPage` applies to `setupChecklistOnScreen`. A toolbar guessing by route would be
    // a second truth about one screen, and the two would drift.
    for (const view of ['DashboardPage.vue', 'ProfilePage.vue']) {
      const source = readFileSync(join(COMPONENTS, '..', 'views', view), 'utf8');
      expect(source, `${view} paints its own <h1>`).toContain('<h1');
      expect(source, `${view} must opt out of the toolbar heading`).toContain('heading-on-screen');
    }
  });

  it('nobody else opts out: a third one would be a screen quietly losing its heading', () => {
    const views = join(COMPONENTS, '..', 'views');
    const optedOut = readdirSync(views)
      .filter((f) => f.endsWith('.vue'))
      .filter((f) => readFileSync(join(views, f), 'utf8').includes('heading-on-screen'))
      .sort();

    expect(optedOut).toEqual(['DashboardPage.vue', 'ProfilePage.vue']);
  });
});
