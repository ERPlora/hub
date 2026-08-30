// hub#1317 (spin-off of the hub#1311 review): activate/deactivate/uninstall broadcast NOTHING of
// their own — unlike install (`module.installed`, hub#631) and update (`module.updated` +
// `module.installed`). Another tab/device of the same hub that (de)activates or uninstalls a
// module leaves every OTHER open tab/device blind until it reloads.
//
// Same fix, same place `module.installed` already lives (`module-installed-refreshes-nav.test.ts`):
// App.vue — always mounted — also listens for `module.activated` / `module.deactivated` /
// `module.uninstalled` and refreshes the nav.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const app = readFileSync(new URL('../App.vue', import.meta.url), 'utf8');

describe.each([
  ['module.activated'],
  ['module.deactivated'],
  ['module.uninstalled'],
])('%s → nav global (hub#1317)', (event) => {
  it(`App.vue escucha ${event}`, () => {
    expect(app).toContain(`'${event}'`);
  });
  it('y refresca la nav al recibirlo', () => {
    const idx = app.indexOf(`'${event}'`);
    expect(idx, `${event} debe existir en App.vue`).toBeGreaterThan(-1);
    const after = app.slice(idx, idx + 400);
    expect(after).toContain('refreshModuleNav');
  });
});
