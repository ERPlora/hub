// The panel mounts the `hub.setup.status` checklist (hub#372) — wiring, not layout.
//
// The hub's pattern (`dashboard-import-refresh.test.ts`): read the SFC source and assert the
// contract. What it protects: that the panel passes the document of the one query, that it applies
// decision 1 (do not duplicate the apps card) and that the checklist is re-read when the set of
// installed modules changes — installing an app is exactly what ticks the first item.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const dashboard = readFileSync(new URL('./DashboardPage.vue', import.meta.url), 'utf8');

describe('the panel reads the one query', () => {
  it('mounts the checklist card with the `hub.setup.status` document', () => {
    expect(dashboard).toContain('SetupChecklistCard');
    expect(dashboard).toMatch(/:status="setupStatus"/);
    expect(dashboard).toContain("from '../lib/setup-status'");
  });

  it('no longer paints the unconfigured-modules banner the browser loop fed', () => {
    expect(dashboard).not.toContain('pendingSetups');
    expect(dashboard).not.toContain('setup-banner');
  });

  it('decision 1: the apps card is on this screen, so the checklist does not repeat it', () => {
    const start = dashboard.indexOf('<SetupChecklistCard');
    const card = dashboard.slice(start, dashboard.indexOf('/>', start));
    expect(card, 'the card was not found in the template').toBeTruthy();

    // The deduplication has no condition left to depend on: since hub#367 the apps card is the
    // panel's first widget and cannot be removed, so the item it offers is ALWAYS on this screen.
    // That is also the row this card buys back to keep both ⛔ in sight (`setup-blocking.test.ts`).
    expect(card).toMatch(/already-on-screen="\['apps'\]"/);
    expect(dashboard, 'the card that justifies deduplicating `apps`').toContain('<MyAppsCard');
  });

  it('re-reads the checklist when the set of installed modules changes (#267)', () => {
    const start = dashboard.indexOf('function onModulesChanged');
    const block = dashboard.slice(start, dashboard.indexOf('\n}', start));
    expect(block, 'onModulesChanged was not found').toBeTruthy();
    expect(block, 'installing an app changes item 1: the checklist has to be re-read').toContain(
      'refreshSetupStatus',
    );
  });
});
