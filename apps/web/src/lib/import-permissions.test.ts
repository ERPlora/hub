// hub#1905 — what a template import leaves for the OWNER to decide.
//
// A downloaded template can never grant a permission by itself (hub#473: a grant is the owner's
// approval over the host's own primitives — the certificate, the printer — so the runtime refuses
// the grants of another hub's bundle, on purpose). That half was right. The half that was missing
// is ASKING: the salon of hub#1905 came out of the «Peluquería» template with VeriFactu and
// Printing installed and both switches off, nobody asked, and the first sale went out with no
// fiscal record and its receipt stuck in the queue.
//
// What these tests pin is the decision of WHAT to ask, kept pure so it is argued here and not in a
// browser:
//   - only the apps the import actually left installed (a blocked or failed one has no switch);
//   - only the permissions still off (the ones this hub already granted are not asked again);
//   - best-effort: an app whose permissions cannot be read is left out, never guessed;
//   - and granting reports which apps failed, so nothing is claimed that did not happen.
import { describe, expect, it, vi } from 'vitest';

import {
  appsToAsk,
  askPermissionsAfterImport,
  grantPending,
  pendingPermissions,
  templateImportReport,
  type PermissionGroup,
} from './import-permissions';
import type { ImportReport, ModuleCapability } from './runtime';

function cap(id: string, over: Partial<ModuleCapability> = {}): ModuleCapability {
  return { id, label: id, description: `${id} description`, requested: true, granted: false, ...over };
}

function report(modules: Array<[string, string]>): ImportReport {
  return {
    sections: [],
    installed_modules: modules.map(([id, status]) => ({ id, version: '1.0.0', status })),
  } as ImportReport;
}

describe('which apps are asked about', () => {
  it('the ones the import left installed, whether it installed them now or they were already here', () => {
    const r = report([
      ['verifactu', 'installed'],
      ['printing', 'already_installed'],
      ['loyalty', 'blocked'],
      ['kitchen', 'failed'],
    ]);

    expect(appsToAsk(r)).toEqual(['verifactu', 'printing']);
  });

  it('a report with no apps, or no report at all, asks about nothing', () => {
    expect(appsToAsk({ sections: [] } as ImportReport)).toEqual([]);
    expect(appsToAsk(null)).toEqual([]);
  });
});

describe('which permissions are asked for', () => {
  it('only the ones each app declares and this hub has NOT granted', async () => {
    const read = vi.fn(async (id: string) =>
      id === 'verifactu'
        ? [cap('certificate'), cap('network', { granted: true })]
        : [cap('printer'), cap('notify', { requested: false })],
    );

    const groups = await pendingPermissions(['verifactu', 'printing'], read);

    expect(groups.map((g) => [g.moduleId, g.capabilities.map((c) => c.id)])).toEqual([
      ['verifactu', ['certificate']],
      ['printing', ['printer']],
    ]);
  });

  it('an app with nothing left to grant is not in the list at all', async () => {
    const read = vi.fn(async (id: string) =>
      id === 'verifactu' ? [cap('certificate', { granted: true })] : [],
    );

    expect(await pendingPermissions(['verifactu', 'customers'], read)).toEqual([]);
  });

  it('an app whose permissions cannot be read is left out, and the others are still asked', async () => {
    const read = vi.fn(async (id: string) => {
      if (id === 'verifactu') throw new Error('capabilities verifactu → 500');
      return [cap('printer')];
    });

    const groups = await pendingPermissions(['verifactu', 'printing'], read);

    expect(groups.map((g) => g.moduleId)).toEqual(['printing']);
  });
});

describe('granting', () => {
  const groups: PermissionGroup[] = [
    { moduleId: 'verifactu', capabilities: [cap('certificate'), cap('network')] },
    { moduleId: 'printing', capabilities: [cap('printer')] },
  ];

  it('grants every listed permission of every app, one request per app', async () => {
    const put = vi.fn(async () => undefined);

    const failed = await grantPending(groups, put);

    expect(failed).toEqual([]);
    expect(put).toHaveBeenCalledWith('verifactu', { certificate: true, network: true });
    expect(put).toHaveBeenCalledWith('printing', { printer: true });
    expect(put).toHaveBeenCalledTimes(2);
  });

  it('returns the apps the runtime refused, and still grants the rest', async () => {
    const put = vi.fn(async (id: string) => {
      if (id === 'verifactu') throw new Error('put-capabilities verifactu → 401');
    });

    const failed = await grantPending(groups, put);

    expect(failed.map((g) => g.moduleId)).toEqual(['verifactu']);
    expect(put).toHaveBeenCalledWith('printing', { printer: true });
  });
});

// Three doors import a template — the hero card, Settings › Data and the assistant — and ONE
// question is asked, by the single `ImportPermissionsConsent` of App.vue. The doors say «this import
// just finished»; the question listens.
describe('the signal every door raises when a template import finishes', () => {
  it('carries the report of the import that just finished', () => {
    const r = report([['verifactu', 'installed']]);

    askPermissionsAfterImport(r);

    expect(templateImportReport.value).toBe(r);
  });
});
