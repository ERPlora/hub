// The panel opens with the BUSINESS (hub#366, PLAN step 10) — wiring, not layout.
//
// Live it painted «Buenos días, ioanbeilic@gmail.com». The rule itself is pinned by behaviour in
// `lib/dashboard-heading.test.ts`; what this file guards is the wiring, which is where the bug
// actually lived: the header reached for the session user instead of the hub's own identity.
//
// The hub's pattern for a view contract (`dashboard-my-apps.test.ts`): read the SFC source and
// assert what it may and may not reach for.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const dashboard = readFileSync(new URL('./DashboardPage.vue', import.meta.url), 'utf8');
const app = readFileSync(new URL('../App.vue', import.meta.url), 'utf8');
const en = readFileSync(new URL('../i18n/locales/en.ts', import.meta.url), 'utf8');
const es = readFileSync(new URL('../i18n/locales/es.ts', import.meta.url), 'utf8');

describe('the header is the business, not the account', () => {
  it('resolves the heading with the shared rule instead of its own inline one', () => {
    expect(dashboard).toContain("from '../lib/dashboard-heading'");
    expect(dashboard).toContain('panelHeading(');
  });

  it('feeds it the hub identity (`business_legal_name`), the only business name the hub holds', () => {
    expect(dashboard).toContain("from '../lib/hub-settings'");
    expect(dashboard).toMatch(/panelHeading\(\s*hubSettings\.value\?\.business_legal_name/);
  });

  it('does not read the session user ANYWHERE: that is the email the panel was printing', () => {
    expect(dashboard).not.toContain("from '../lib/session'");
    expect(dashboard).not.toContain('user.value');
  });

  it('lets a long business name wrap instead of running off the screen', () => {
    // The `<h1>` now paints text the owner typed, of any length and with no guaranteed spaces
    // («Restauración y Hostelería del Mediterráneo SLU»). Wrapping is right for a business name;
    // truncating one is not.
    const css = dashboard.slice(dashboard.indexOf('.dash-hero-title {'));

    expect(css.slice(0, css.indexOf('}'))).toContain('overflow-wrap: anywhere');
  });

  it('paints the resolved heading in the `<h1>`, above the date', () => {
    const h1 = dashboard.indexOf('<h1 class="dash-hero-title">');
    const date = dashboard.indexOf('class="dash-hero-date"');

    expect(h1, 'the hero title was not found').toBeGreaterThan(-1);
    expect(dashboard.slice(h1, dashboard.indexOf('</h1>', h1))).toContain('heading');
    expect(h1).toBeLessThan(date);
  });
});

describe('the person keeps her place in the account menu', () => {
  // «The person's name goes in the account menu; the `<h1>` is the business.» Taking the name out
  // of the panel only works if it is still somewhere — otherwise this trades one bug for another.
  it('the sidebar account menu still shows who is signed in', () => {
    expect(app).toContain("from './lib/session'");
    expect(app).toContain('sidebar-user-name');
    expect(app).toContain('user?.name');
  });
});

describe('the greeting no longer interpolates anybody', () => {
  it.each([
    ['en', en],
    ['es', es],
  ])('the %s catalogue greets the hour with no name in it', (_lang, catalogue) => {
    const block = catalogue.slice(
      catalogue.indexOf('greetingMorning'),
      catalogue.indexOf('todayLabel'),
    );

    expect(block, 'the greeting strings were not found').toContain('greetingEvening');
    expect(block, '{name} is the placeholder that printed the email').not.toContain('{name}');
  });

  it('both catalogues keep the three slots, so no hour falls back to a key on screen', () => {
    for (const catalogue of [en, es]) {
      expect(catalogue).toContain('greetingMorning');
      expect(catalogue).toContain('greetingAfternoon');
      expect(catalogue).toContain('greetingEvening');
    }
  });
});
