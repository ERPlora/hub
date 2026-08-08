// @vitest-environment node
// **A waiter halfway through an order keeps the order** — the one guarantee hub#400 owes the floor.
//
// The update entry sits in the sidebar of a till that is used standing up, next to the order the
// person is taking. Ask what happens when it is pressed mid-service and the answer has to be:
// nothing to the order. There is no way for this shell to KNOW whether a sale is open — the POS is
// a module behind its own Web Component and it publishes no such signal (searched: no `cart`, no
// `currentSale`, no `beforeunload`, anywhere in the repo) — so the protection cannot be a check.
// It has to be a property of the action itself: **the update never destroys this page**.
//
// It hands the address to the user's OWN browser and stops. Nothing reloads, nothing navigates,
// nothing closes, nothing relaunches. The moment the till actually goes down is the moment somebody
// double-clicks an installer they downloaded — a moment a human picks, after the confirmation says
// so in words.
//
// This is a source test because that is where the property lives: one `location.assign` added
// tomorrow by someone wiring "restart after update" would pass every behavioural test in the suite
// and lose a table's order the first Friday night. It is the same shape as the guard ADR-0255 put
// on `openExternal`'s callers, and for the same reason: the person who breaks it has not read this.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..');

const read = (relative: string): string => readFileSync(join(SRC, relative), 'utf8');

/** Everything that would take the till down, or take it somewhere else, without being asked. */
const DESTROYS_THE_PAGE: readonly RegExp[] = [
  /location\s*\.\s*(assign|replace|reload)\s*\(/,
  /location\s*\.\s*href\s*=/,
  /window\s*\.\s*close\s*\(/,
  // Tauri's own ways of ending the process. None is wired today (there is no updater without the
  // signing key of hub#394) and none may arrive here without this file being read first.
  /\b(relaunch|restart|exit)\s*\(/,
  /process\s*\.\s*exit/,
];

/** The whole of the update path: the state, and the control that acts on it. */
const THE_UPDATE_PATH = ['lib/app-update.ts', 'components/SidebarAppUpdate.vue'] as const;

describe('pressing Update with a sale open', () => {
  it.each(THE_UPDATE_PATH)('never destroys the page from %s', (file) => {
    const source = read(file);
    const offenders = DESTROYS_THE_PAGE.filter((pattern) => pattern.test(source)).map(
      (pattern) => pattern.source,
    );
    expect(offenders, `${file} can take the till down under the person using it`).toEqual([]);
  });

  it('leaves through the one door that comes BACK — the user own browser', () => {
    // `openExternal` is `_blank` in a browser and the SYSTEM browser inside the installed app
    // (ADR-0255). Either way THIS page survives, which is the entire point: five other callers
    // already depend on that same property to re-check a purchase on focus.
    expect(read('components/SidebarAppUpdate.vue')).toContain('await openExternal(destination)');
  });

  it('asks before it does anything at all', () => {
    // Not a nicety: the confirmation is where the product says out loud that this downloads an
    // installer the user has to run. Without it the honest sentence never reaches anyone.
    const source = read('components/SidebarAppUpdate.vue');
    expect(source).toContain('alertController.create');
    expect(source).toContain("role !== 'confirm'");
  });
});

describe('where the entry lives', () => {
  it('is in the LEFT sidebar, not buried in settings', () => {
    // hub#400, word for word: «botón Actualizar en el sidebar IZQUIERDO (visible, no enterrado en
    // ajustes)». The sidebar is inlined in App.vue, and the footer is the half that never scrolls.
    const app = read('App.vue');
    expect(app).toContain('<SidebarAppUpdate />');
    expect(app.indexOf('<SidebarAppUpdate />')).toBeGreaterThan(app.indexOf('<ion-footer'));
    expect(app.indexOf('<SidebarAppUpdate />')).toBeLessThan(app.indexOf('</ion-menu>'));
  });

  it('is asked for after the session, so the sidebar it feeds exists', () => {
    expect(read('App.vue')).toContain('bootAppUpdateWatch()');
  });
});
