// The panel puts the launcher FIRST (hub#367, PLAN step 10) — wiring and ORDER, not layout.
//
// The hub's pattern (`dashboard-setup-checklist.test.ts`): read the SFC source and assert the
// contract. The order is the contract here: «launcher first, report after». The report (KPIs,
// activity) needs a history the owner does not have on day one and does not need on day thirty;
// the launcher works at both ends, so it is the one that cannot end up below the fold.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const dashboard = readFileSync(new URL('./DashboardPage.vue', import.meta.url), 'utf8');
const en = readFileSync(new URL('../i18n/locales/en.ts', import.meta.url), 'utf8');
const es = readFileSync(new URL('../i18n/locales/es.ts', import.meta.url), 'utf8');

describe('the launcher goes first', () => {
  it('mounts the «My apps» card fed by the apps the runtime reports', () => {
    expect(dashboard).toContain('MyAppsCard');
    // The SAME source as the topbar launcher (`/api/navigation`): two lists of installed apps on
    // one screen would drift the day one of them forgets to refresh.
    expect(dashboard).toMatch(/:apps="moduleNav"/);
    expect(dashboard).toContain("from '../lib/nav'");
  });

  it('is above the checklist card and above the widget board', () => {
    const launcher = dashboard.indexOf('<MyAppsCard');
    const checklist = dashboard.indexOf('<SetupChecklistCard');
    const board = dashboard.indexOf('<ok-widget-board');

    expect(launcher, 'the launcher card was not found in the template').toBeGreaterThan(-1);
    expect(launcher).toBeLessThan(checklist);
    expect(launcher).toBeLessThan(board);
  });

  it('lives on the Summary tab, where the panel opens', () => {
    const summary = dashboard.indexOf("v-if=\"tab === 'resumen'\"");
    const activity = dashboard.indexOf("v-else-if=\"tab === 'actividad'\"");

    expect(dashboard.indexOf('<MyAppsCard')).toBeGreaterThan(summary);
    expect(dashboard.indexOf('<MyAppsCard')).toBeLessThan(activity);
  });

  it('is unconditional: the launcher is the widget that works with zero data', () => {
    const start = dashboard.indexOf('<MyAppsCard');
    const tag = dashboard.slice(start, dashboard.indexOf('/>', start));

    expect(tag.startsWith('<MyAppsCard'), 'the launcher card was not found in the template').toBe(true);
    expect(tag).not.toContain('v-if');
    expect(tag).not.toContain('v-show');
  });
});

describe('«install your first module» is gone', () => {
  it('the panel no longer paints the empty-hub onboarding block', () => {
    expect(dashboard).not.toContain('dash-onboarding');
    expect(dashboard).not.toContain('onboardingTitle');
  });

  it('and its strings left with it, in both catalogues', () => {
    // The plan's rule: the empty state of the panel is the configuration card, never «install your
    // first module» — a sentence that asks a bar owner to understand our architecture first.
    for (const catalogue of [en, es]) {
      expect(catalogue).not.toContain('onboardingTitle');
      expect(catalogue).not.toContain('onboardingBody');
      expect(catalogue).not.toContain('onboardingCta');
    }
  });
});
