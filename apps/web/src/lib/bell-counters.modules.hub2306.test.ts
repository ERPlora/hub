// @vitest-environment happy-dom
// hub#2306 — which installed modules put a counter on the bell, read with the SAME rules the bell
// uses to run it. The notice permission is asked only when something would ever use it (hub#2046);
// since hub#2303 a bell counter does, so the ask needs to know which modules have one — and a
// counter the bell would refuse to run (no label, another module's query) must not count.
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { InstalledManifest } from './module-loader';

let installed: InstalledManifest[] = [];
let manifestsFail = false;

vi.mock('./session', () => ({ isAuthed: { value: true }, user: { value: null }, hasPermission: () => true }));
vi.mock('./runtime', () => ({ getClient: () => ({ query: vi.fn() }) }));
vi.mock('./module-loader', () => ({
  loadInstalledManifests: async () => {
    if (manifestsFail) throw new Error('offline');
    return installed;
  },
}));

const { bellCounterModuleIds, loadBellCounterModuleIds } = await import('./bell-counters');

function mod(moduleId: string, bell?: Record<string, unknown>): InstalledManifest {
  return {
    moduleId,
    manifest: { id: moduleId, name: moduleId, version: '1.0.0', ui: { entry: 'x.js' }, bell } as never,
    entryUrl: `/modules/${moduleId}/x.js`,
  };
}

const INBOX = mod('whatsapp_inbox', {
  'whatsapp_inbox.needs_attention': {
    label: 'WhatsApp customers waiting for a reply',
    query: 'whatsapp_inbox.conversations.count_needs_attention',
    nav: 'inbox',
  },
});

beforeEach(() => {
  installed = [];
  manifestsFail = false;
});

describe('modules with a counter on the bell', () => {
  it('a module that declares a counter of its own has one', () => {
    expect([...bellCounterModuleIds([INBOX, mod('customers')])]).toEqual(['whatsapp_inbox']);
  });

  it('a counter that reads another module’s data does not count (the bell refuses to run it)', () => {
    const intruder = mod('marketing', {
      'marketing.waiting': { label: 'Waiting', query: 'whatsapp_inbox.conversations.count_needs_attention' },
    });
    expect(bellCounterModuleIds([intruder]).size).toBe(0);
  });

  it('a counter without a label or a query does not count', () => {
    const broken = mod('reservations', {
      'reservations.a': { query: 'reservations.pending.count' },
      'reservations.b': { label: 'Pending' },
    });
    expect(bellCounterModuleIds([broken]).size).toBe(0);
  });
});

describe('reading them from what is installed', () => {
  it('reads the installed manifests', async () => {
    installed = [INBOX, mod('sales')];
    expect([...(await loadBellCounterModuleIds())]).toEqual(['whatsapp_inbox']);
  });

  it('manifests that cannot be read answer «none», never throw', async () => {
    manifestsFail = true;
    await expect(loadBellCounterModuleIds()).resolves.toEqual(new Set());
  });
});
