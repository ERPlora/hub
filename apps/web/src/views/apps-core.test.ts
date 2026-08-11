import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('./AppsPage.vue', import.meta.url), 'utf8');

describe('Apps destructive actions', () => {
  it('confirms uninstall before asking the runtime to remove a module', () => {
    const start = source.indexOf('async function removeModule');
    const end = source.indexOf('function toViewModule', start);
    const implementation = source.slice(start, end);

    expect(implementation).toContain('alertController.create');
    expect(implementation.indexOf('onDidDismiss')).toBeLessThan(
      implementation.indexOf('uninstallModule'),
    );
  });

  it('keeps module management read-only for non-admin users', () => {
    expect(source).toContain("import { isAdmin } from '../lib/session'");
    expect(source).toContain("v-if=\"!isAdmin\"");
    expect(source).toContain('isAdmin.value');
  });

  // hub#314 (ADR-0202 R2): the runtime refuses to disable/uninstall a module that still owes
  // records to the AEAT, and says how many are left. That reason travels in the error message —
  // collapsing it into a generic "could not do it" toast turns the guard back into a mute no-op.
  it('shows the runtime reason when a module refuses to be disabled or removed', () => {
    for (const fn of ['async function toggleModule', 'async function removeModule']) {
      const start = source.indexOf(fn);
      expect(start, `${fn} must exist`).toBeGreaterThan(-1);
      const implementation = source.slice(start, source.indexOf('\n}', start));
      expect(implementation, `${fn} must capture the error`).toMatch(/catch\s*\(/);
      expect(implementation, `${fn} must surface the reason`).toContain('reasonOf(');
    }
    expect(source).toContain('function reasonOf');
  });

  it('never falls back to a locally invented demo catalog', () => {
    expect(source).not.toContain('MODULES_DEMO');
    expect(source).not.toContain('config.demo ? MODULES_DEMO');
    expect(source).toContain('modules.value = []');
    expect(source).toContain('catalogError.value = true');
  });
});

// hub#773 — a card of an installed app ended in two unnamed pictograms and no way in.
//
// The screen is `ok-data-table` in cards mode: what it paints for a row is decided by the `actions`
// this file declares, and the actions are icon-only by rule (Ioan, 2026-07-16, on top of ADR-0133 —
// the `label` is the accessible name and the tooltip, never visible text). So the questions a person
// has before pressing cannot be answered by the button face; they have to be answered by the action
// SET being right and by what the confirmation says. That is what these read.
describe('Apps · what an installed app card offers', () => {
  const start = source.indexOf('const mineActions');
  const mineActions = source.slice(start, source.indexOf('const catalogColumns', start));

  it('offers OPEN as the first action — the one thing a person came to the card for', () => {
    expect(start, 'mineActions must exist').toBeGreaterThan(-1);
    expect(mineActions).toContain("id: 'open'");
    expect(mineActions).toContain("t('apps.actionOpen')");
    // First in the list = first button on the card. The primary action does not sit behind the bin.
    expect(mineActions.indexOf("id: 'open'")).toBeLessThan(mineActions.indexOf("id: 'toggle'"));
    // Only when there is a screen to open: `canOpenModule` is the one that decides, and it is
    // covered by its own tests. Here we only check the card asks it.
    expect(mineActions).toContain('canOpenModule(');
    expect(source).toContain("import { canOpenModule, dependentsOf, moduleRoutePath, toggleIntent } from '../lib/installed-app-actions'");
  });

  it('always asks before flipping the switch, and the question names the future state', () => {
    const fn = source.slice(
      source.indexOf('async function toggleModule'),
      source.indexOf('async function removeModule'),
    );
    // Not only when the cascade drags others down: a press that changes whether the till can sell
    // must say so first, and say which direction it goes in.
    expect(fn).toContain('toggleIntent(');
    expect(fn).toContain('confirmToggle');
    expect(source).toContain('apps.toggleOffTitle');
    expect(source).toContain('apps.toggleOnTitle');
    // And the answer still gates the call: no confirmation, no runtime call.
    expect(fn.indexOf('confirmToggle')).toBeLessThan(fn.indexOf('deactivateModule('));
  });

  // hub#795 — the status column said «Update to 1.2.22» and the button on the same row was still
  // called «Install». Icon-only actions mean the label is the accessible name: a keyboard and a
  // screen reader were told the wrong verb for the operation about to run.
  it('offers UPDATE and INSTALL as two actions, so the name matches the operation', () => {
    const start = source.indexOf('const catalogActions');
    const catalogActions = source.slice(start, source.indexOf('// --- Handlers ---', start));
    expect(start, 'catalogActions must exist').toBeGreaterThan(-1);
    expect(catalogActions).toContain("id: 'install'");
    expect(catalogActions).toContain("id: 'update'");
    // Each one lives exactly where its own operation applies — never both on the same row.
    expect(catalogActions).toContain("catalogActionFor(row.state as CatalogRowState) !== 'install'");
    expect(catalogActions).toContain("catalogActionFor(row.state as CatalogRowState) !== 'update'");
  });

  it('routes the catalog press by the ROW state, not by the Cloud flag', () => {
    const fn = source.slice(
      source.indexOf('function handleCatalogAction'),
      source.indexOf('function wireTable'),
    );
    expect(fn).toContain("actionId === 'update'");
    expect(fn).toContain('updateInstalledModule(');
    // And the state itself comes from the one function that crosses Cloud with the runtime.
    expect(source).toContain('catalogRowState(');
    // `mark_installed` is best-effort: right after installing, the Cloud still says false while the
    // runtime already has the module. Deciding install-or-update off that flag is hub#795 itself.
    expect(source).not.toContain('if (mod.installed) {');
  });

  it('names the apps that uninstalling would break, before uninstalling', () => {
    const fn = source.slice(
      source.indexOf('async function removeModule'),
      source.indexOf('function toViewModule'),
    );
    expect(fn).toContain('dependentsOf(');
    expect(fn.indexOf('dependentsOf(')).toBeLessThan(fn.indexOf('uninstallModule('));
    expect(source).toContain('apps.uninstallBreaks');
  });
});
