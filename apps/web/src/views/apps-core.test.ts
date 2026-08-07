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
