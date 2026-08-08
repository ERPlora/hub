// The panel reacts to the progress of the business: set-up hero → apps hero → widgets (hub#368,
// PLAN step 10) — wiring and ORDER, not layout.
//
// The hub's pattern (`dashboard-my-apps.test.ts`): read the SFC source and assert the contract.
// What it protects here is the order and the source. On day one the launcher holds exactly one tile
// (＋ Add apps), so it is not the hero of that screen yet: the one press that fills the whole
// business is. The moment there ARE apps the hero is gone and hub#367 is back in force — the
// launcher first, unconditionally, for the next thirty days and beyond.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const dashboard = readFileSync(new URL('./DashboardPage.vue', import.meta.url), 'utf8');

describe('the hero of an empty business', () => {
  it('is mounted with the document of the ONE query, like every other surface', () => {
    // Not a count of its own of what is installed: `hub.setup.status` already owns «does this
    // business have apps» (ADR-0222), and a second source is the divergence hub#369 closed.
    expect(dashboard).toContain('BlueprintHeroCard');
    const start = dashboard.indexOf('<BlueprintHeroCard');
    const tag = dashboard.slice(start, dashboard.indexOf('/>', start));
    expect(tag, 'the hero card was not found in the template').toBeTruthy();
    expect(tag).toMatch(/:status="setupStatus"/);
  });

  it('decides on its own whether to be there: the panel does not gate it', () => {
    // The panel knows less than the card does — the card also weighs the permission (ADR-0248) and
    // whether there is anything published to offer. A `v-if` here would be a second, poorer gate.
    const start = dashboard.indexOf('<BlueprintHeroCard');
    const tag = dashboard.slice(start, dashboard.indexOf('/>', start));
    expect(tag).not.toContain('v-if');
    expect(tag).not.toContain('v-show');
  });

  it('goes above the launcher, and the launcher stays above everything else', () => {
    const hero = dashboard.indexOf('<BlueprintHeroCard');
    const launcher = dashboard.indexOf('<MyAppsCard');
    const checklist = dashboard.indexOf('<SetupChecklistCard');

    expect(hero).toBeGreaterThan(-1);
    expect(hero).toBeLessThan(launcher);
    // hub#367 is untouched: the launcher is still first among the things that outlive day one.
    expect(launcher).toBeLessThan(checklist);
  });

  it('never displaces the header: the business is still the first thing on the screen', () => {
    expect(dashboard.indexOf('dash-hero-title')).toBeLessThan(dashboard.indexOf('<BlueprintHeroCard'));
  });

  it('lives on the Summary tab, where the panel opens', () => {
    const summary = dashboard.indexOf("v-if=\"tab === 'resumen'\"");
    const activity = dashboard.indexOf("v-else-if=\"tab === 'actividad'\"");
    const hero = dashboard.indexOf('<BlueprintHeroCard');

    expect(hero).toBeGreaterThan(summary);
    expect(hero).toBeLessThan(activity);
  });

  it('leaves the checklist deduplicating `apps`, and only that', () => {
    // The hero offers the same item the launcher does, so the deduplication of hub#372 already
    // covers it. Adding a second key here would hide a row the checklist is the only one to own.
    const start = dashboard.indexOf('<SetupChecklistCard');
    const card = dashboard.slice(start, dashboard.indexOf('/>', start));
    expect(card).toMatch(/already-on-screen="\['apps'\]"/);
  });
});
