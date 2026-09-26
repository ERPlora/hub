// hub#2046 — **a salon was asked to turn on notices that nothing would ever send.**
//
// The print-host alta asked for the notification permission on every device that registered,
// whatever the hub had installed. The only notice the shell sends today is the kitchen order
// (`print-comanda.ts`), so a hair salon — no kitchen — accepted a permission that never fired, and
// the owner was left waiting for booking alerts that do not exist. Android's own guidance (and
// Square, Fresha, Booksy) ask for it in context, when the feature that uses it is there.
//
// What is pinned: the ask happens only when an ACTIVE module the shell sends notices for is
// installed, the answer is read fresh (the alta can come before the post-login refresh landed),
// and "not known" never asks — the kitchen notice itself stays the fallback trigger.
import { describe, expect, it, vi } from 'vitest';

import { NOTICE_SOURCE_MODULES, hasNoticeSource, warnIfThereIsSomethingToTell } from './notification-permission';

describe('which hubs have something to warn about', () => {
  it('a hub with the kitchen active does', () => {
    expect(hasNoticeSource(new Set(['sales', 'kitchen']))).toBe(true);
  });

  it('a salon — appointments, sales, customers — does not', () => {
    expect(hasNoticeSource(new Set(['sales', 'appointments', 'customers', 'whatsapp_inbox']))).toBe(false);
  });

  it('not knowing what is installed is not a reason to ask', () => {
    expect(hasNoticeSource(undefined)).toBe(false);
  });

  it('the kitchen is the only source today (a new one is a deliberate change here)', () => {
    expect([...NOTICE_SOURCE_MODULES]).toEqual(['kitchen']);
  });
});

describe('the ask at the print-host alta', () => {
  it('asks on a hub with a kitchen, after refreshing what is installed', async () => {
    const order: string[] = [];
    let ids: ReadonlySet<string> | undefined;
    const ask = vi.fn(async () => {
      order.push('ask');
    });

    await warnIfThereIsSomethingToTell({
      refresh: async () => {
        order.push('refresh');
        ids = new Set(['kitchen']);
      },
      activeModules: () => ids,
      ask,
    });

    expect(order).toEqual(['refresh', 'ask']);
  });

  it('does not ask on a salon', async () => {
    const ask = vi.fn(async () => {});
    await warnIfThereIsSomethingToTell({
      refresh: async () => {},
      activeModules: () => new Set(['appointments', 'sales']),
      ask,
    });
    expect(ask).not.toHaveBeenCalled();
  });

  it('does not ask when the installed list could not be read, and never throws', async () => {
    const ask = vi.fn(async () => {});
    await expect(
      warnIfThereIsSomethingToTell({
        refresh: async () => {
          throw new Error('offline');
        },
        activeModules: () => undefined,
        ask,
      }),
    ).resolves.toBeUndefined();
    expect(ask).not.toHaveBeenCalled();
  });
});
