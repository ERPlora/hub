// The blocking strip is CHROME, not a page (hub#374): wiring, not layout.
//
// The strip only pays for itself if it is where the checklist card is not — above the till, above a
// module's screen, above Files. The hub's pattern for that kind of contract
// (`dashboard-setup-checklist.test.ts`, `layout-shell.test.ts`) is to read the SFC source and assert
// the wiring, because mounting the whole shell would test Ionic instead.
//
// What is protected here:
//   - every shell screen inherits the strip from the single layout, and it sits OUTSIDE the scroller
//     (a warning that scrolls away is not a warning);
//   - the screens with no session do not inherit it — there is nothing to configure before logging in;
//   - the document is read once for the whole shell and re-read as the user moves, so the strip
//     clears itself when the hub is fixed instead of waiting for a reload;
//   - on the panel it stands down under the SAME condition that paints the checklist card.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const source = (path: string): string => readFileSync(new URL(path, import.meta.url), 'utf8');

const appPage = source('../components/AppPage.vue');
const app = source('../App.vue');
const dashboard = source('./DashboardPage.vue');

describe('every screen of the shell carries it', () => {
  it('the single layout mounts the strip with the shared document', () => {
    expect(appPage).toContain('SetupBlockingStrip');
    expect(appPage).toMatch(/:status="setupStatus"/);
    expect(appPage).toContain("from '../lib/setup-status'");
  });

  it('the strip sits above the scroller, not inside it', () => {
    // Inside `ion-content` it would scroll away with the page and stop being true about the hub the
    // moment the user scrolled. It belongs to the page chrome, next to the topbar.
    const strip = appPage.indexOf('<SetupBlockingStrip');
    const topbarEnd = appPage.indexOf('</AppTopbar>');
    const content = appPage.indexOf('<ion-content');

    expect(strip, 'the strip is not in the layout').toBeGreaterThan(-1);
    expect(strip).toBeGreaterThan(topbarEnd);
    expect(strip).toBeLessThan(content);
  });

  it('the module screens inherit it — the till never opens the panel', () => {
    // `AppPage` is the only layout of the shell, so this is what actually puts the strip over the
    // POS. If a screen ever stops using it, the strip silently disappears from that screen.
    for (const page of ['ModuleView.vue', 'SettingsPage.vue', 'EmployeesPage.vue', 'FilesPage.vue']) {
      expect(source(`./${page}`), `${page} left the shared layout`).toContain('<AppPage');
    }
  });

  it('the screens without a session do not carry it', () => {
    // Nothing to configure before there is a hub session, and the query is gated on one anyway.
    for (const page of ['LoginPage.vue', 'ActivationPage.vue']) {
      expect(source(`./${page}`), `${page} took the shell layout`).not.toContain('<AppPage');
    }
  });
});

describe('the document belongs to the shell, and it stays fresh', () => {
  it('the shell reads the query itself instead of borrowing the panel read', () => {
    // Before this the only read was in `DashboardPage`: a user who went straight to the till got a
    // strip fed by nothing. The read has to happen where the session is resolved, not only when the
    // user moves — otherwise the first screen after logging in is always blind.
    expect(app).toContain("from './lib/setup-status'");
    const boot = app.slice(app.indexOf('async function gateAndRefresh'));
    expect(boot.slice(0, boot.indexOf('\n}')), 'the shell does not read the document on login').toContain(
      'refreshSetupStatus',
    );
  });

  it('re-reads as the user moves, so the strip clears itself once the hub is fixed', () => {
    // The strip cannot be dismissed, so the ONLY way it goes away is the hub being fixed. Reading it
    // again on navigation is also what catches a gate that appears mid-session (installing the
    // module that asks for a certificate adds a ⛔ that was not there at login).
    const watcher = app.slice(app.indexOf('() => route.path'));
    expect(watcher, 'nothing re-reads the document on navigation').toContain('refreshSetupStatus');
  });
});

describe('on the panel it stands down', () => {
  it('the layout is told by the SAME condition that paints the checklist card', () => {
    // One condition shared by the two surfaces, exactly like decision 1 of the plan: two separate
    // conditions for one screen end up showing the thing twice, or never.
    const layout = dashboard.slice(dashboard.indexOf('<AppPage'), dashboard.indexOf('>', dashboard.indexOf('<AppPage')));
    expect(layout).toContain('setup-checklist-on-screen');

    const tab = /:setup-checklist-on-screen="([^"]+)"/.exec(layout)?.[1];
    expect(tab, 'the panel does not say when its checklist is on screen').toBeTruthy();
    // The card lives in the summary tab only; on the other tabs the panel is a screen like any other.
    expect(tab).toContain("tab === 'resumen'");
    expect(dashboard).toMatch(/v-if="tab === 'resumen'"/);
  });
});
