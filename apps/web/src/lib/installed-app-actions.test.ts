import { describe, expect, it } from 'vitest';

import {
  canOpenModule,
  dependentsOf,
  hidesUpdateAction,
  moduleRoutePath,
  toggleIntent,
} from './installed-app-actions';
import type { InstalledModule } from './runtime';
import type { ModuleNavItem } from './nav';

// What «Apps → My apps» is allowed to say about an installed app before it does anything to it
// (hub#773).
//
// The card used to end in two unnamed pictograms: a power symbol and a bin. Nothing on the screen
// said whether the first one turns the app on or off, the bin destroyed things without saying which,
// and the one action a person actually came for — OPEN the app — was not there at all. This module
// holds the three questions the screen has to answer, apart from the screen, so they can be answered
// with a test instead of with a screenshot.

function mod(over: Partial<InstalledModule> & { id: string }): InstalledModule {
  return { name: over.id, status: 'active', version: '1.0.0', ...over };
}

describe('moduleRoutePath', () => {
  it('is the shell route that mounts a module', () => {
    expect(moduleRoutePath('sales')).toBe('/m/sales');
  });
});

describe('canOpenModule', () => {
  const nav: ModuleNavItem[] = [{ path: '/m/sales', label: 'Sales', icon: '' }];

  it('opens a module the runtime publishes navigation for', () => {
    expect(canOpenModule(mod({ id: 'sales' }), nav)).toBe(true);
  });

  it('does not open a module with no screen of its own', () => {
    // A module can be pure back-office — migrations, events, a scheduled task — and never paint
    // anything. Offering «Open» there is a button that leads to an empty page.
    expect(canOpenModule(mod({ id: 'core-tax' }), nav)).toBe(false);
  });

  it('does not open a module that is switched off', () => {
    // `/api/navigation` only reports ACTIVE modules, so an inactive one is already absent from
    // `nav`. Asserting on the status too keeps the answer right the moment the nav is stale — the
    // list is refreshed asynchronously, and a card must never offer a door that is bolted.
    expect(canOpenModule(mod({ id: 'sales', status: 'inactive' }), nav)).toBe(false);
    expect(canOpenModule(mod({ id: 'sales', status: 'inactive_auto' }), nav)).toBe(false);
  });
});

describe('toggleIntent', () => {
  it('names what the press will DO, not what the app currently is', () => {
    expect(toggleIntent('active')).toBe('deactivate');
    expect(toggleIntent('inactive')).toBe('activate');
  });

  it('offers to switch back on a module the cascade dragged down', () => {
    // `inactive_auto` (ADR-0128) is «off because a dependency of mine went off». The switch still
    // reads «turn on»: it is the direction the press moves in, and the cascade will bring the
    // dependency with it.
    expect(toggleIntent('inactive_auto')).toBe('activate');
  });
});

describe('dependentsOf — what uninstalling this app would break', () => {
  const installed = [
    mod({ id: 'core' }),
    mod({ id: 'sales', depends_on: ['core'] }),
    mod({ id: 'reports', depends_on: ['sales'] }),
    mod({ id: 'files' }),
  ];

  it('is transitive: the app that depends on the app that depends on this one', () => {
    // Uninstalling `core` breaks `sales` directly and `reports` through it. A confirmation that
    // named only the direct one would still be a surprise, one screen later.
    expect(dependentsOf('core', installed).map((m) => m.id)).toEqual(['sales', 'reports']);
  });

  it('counts a module that is switched off — uninstalling is not deactivating', () => {
    // The deactivation cascade only looks at ACTIVE dependants, because switching off something
    // already off changes nothing. Uninstalling is the opposite: the package goes away, so an
    // inactive dependant can never be switched back on. It has to be named.
    const withInactive = [mod({ id: 'core' }), mod({ id: 'sales', depends_on: ['core'], status: 'inactive' })];
    expect(dependentsOf('core', withInactive).map((m) => m.id)).toEqual(['sales']);
  });

  it('is empty when nothing needs it', () => {
    expect(dependentsOf('files', installed)).toEqual([]);
  });

  it('never returns the module itself, and survives a dependency cycle', () => {
    // A cycle should not exist — the installer resolves a DAG — but a manifest is data written by
    // somebody else, and the confirmation dialog is the last place we want an infinite loop.
    const cyclic = [mod({ id: 'a', depends_on: ['b'] }), mod({ id: 'b', depends_on: ['a'] })];
    expect(dependentsOf('a', cyclic).map((m) => m.id)).toEqual(['b']);
  });
});

// hub#2015 — a card showed «Update» greyed out whenever the app had no new version, which is almost
// always, and a person read the grey button as «something is blocked». The action is not greyed any
// more: it is simply not there. It still has to be there WHILE it runs — that is where the spinner
// lives — even if the row has already lost its pending version.
describe('hidesUpdateAction', () => {
  it('hides «Update» when there is no new version and nothing is running', () => {
    expect(hidesUpdateAction({ update: null, updating: false })).toBe(true);
    expect(hidesUpdateAction({})).toBe(true);
  });

  it('shows «Update» when a new version is waiting', () => {
    expect(hidesUpdateAction({ update: { latest: '1.2.0' }, updating: false })).toBe(false);
  });

  it('keeps «Update» on screen while it runs, so the spinner has somewhere to spin', () => {
    expect(hidesUpdateAction({ update: { latest: '1.2.0' }, updating: true })).toBe(false);
    expect(hidesUpdateAction({ update: null, updating: true })).toBe(false);
  });
});
