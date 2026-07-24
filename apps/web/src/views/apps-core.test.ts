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

  it('never falls back to a locally invented demo catalog', () => {
    expect(source).not.toContain('MODULES_DEMO');
    expect(source).not.toContain('config.demo ? MODULES_DEMO');
    expect(source).toContain('modules.value = []');
    expect(source).toContain('catalogError.value = true');
  });
});
