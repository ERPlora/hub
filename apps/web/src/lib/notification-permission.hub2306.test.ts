// hub#2306 — **a business that only uses WhatsApp was never asked to turn the notices on.**
//
// Since hub#2303 any module that puts a counter on the bell sends a system notice when it goes up
// (a WhatsApp customer handed over to a person). But the list of modules that count as «something
// to warn about» was fixed to the kitchen and appointments, so on a WhatsApp-only hub the ask never
// came while somebody was setting the tablet up, System never said the notices were off, and the
// first customer left waiting popped Android's question on a tablet propped on a shelf.
//
// And the ask itself only happened at the print-host alta, which a device with no printer — the
// usual WhatsApp tablet — never reaches. So the ask is ALSO made when somebody signs in on the
// device: a person is standing in front of it, which is the whole point of asking in context.
//
// What is pinned: an ACTIVE module that declares a bell counter is a notice source (without the
// core naming any module); a bell module that is not active is not; not knowing what is installed
// still never asks; a failing bell read falls back to the fixed list and never throws; and the ask
// runs on every sign-in, never while signed out.
import { describe, expect, it, vi } from 'vitest';
import { nextTick, ref } from 'vue';

import { askWhenSomeoneSignsIn, hasNoticeSource, warnIfThereIsSomethingToTell } from './notification-permission';

describe('a module with a bell counter is something to warn about', () => {
  it('a WhatsApp-only hub (its inbox puts a counter on the bell) does', () => {
    expect(hasNoticeSource(new Set(['whatsapp_inbox', 'customers']), new Set(['whatsapp_inbox']))).toBe(true);
  });

  it('a bell module that is installed but not active does not', () => {
    expect(hasNoticeSource(new Set(['customers', 'sales']), new Set(['whatsapp_inbox']))).toBe(false);
  });

  it('not knowing what is active is still not a reason to ask', () => {
    expect(hasNoticeSource(undefined, new Set(['whatsapp_inbox']))).toBe(false);
  });

  it('a hub with no bell module keeps the fixed sources', () => {
    expect(hasNoticeSource(new Set(['kitchen']), new Set())).toBe(true);
    expect(hasNoticeSource(new Set(['sales']), new Set())).toBe(false);
  });
});

describe('the ask on a WhatsApp-only hub', () => {
  it('asks, after refreshing what is active', async () => {
    let ids: ReadonlySet<string> | undefined;
    const ask = vi.fn(async () => {});

    await warnIfThereIsSomethingToTell({
      refresh: async () => {
        ids = new Set(['whatsapp_inbox', 'customers']);
      },
      activeModules: () => ids,
      bellModules: async () => new Set(['whatsapp_inbox']),
      ask,
    });

    expect(ask).toHaveBeenCalledTimes(1);
  });

  it('a bell read that fails falls back to the fixed list, and never throws', async () => {
    const ask = vi.fn(async () => {});
    await expect(
      warnIfThereIsSomethingToTell({
        refresh: async () => {},
        activeModules: () => new Set(['whatsapp_inbox']),
        bellModules: async () => {
          throw new Error('offline');
        },
        ask,
      }),
    ).resolves.toBeUndefined();
    expect(ask).not.toHaveBeenCalled();

    await warnIfThereIsSomethingToTell({
      refresh: async () => {},
      activeModules: () => new Set(['kitchen']),
      bellModules: async () => {
        throw new Error('offline');
      },
      ask,
    });
    expect(ask).toHaveBeenCalledTimes(1);
  });
});

describe('the ask when somebody signs in on this device', () => {
  it('runs when a session opens, and again on the next sign-in', async () => {
    const signedIn = ref(false);
    const warn = vi.fn(async () => {});
    const stop = askWhenSomeoneSignsIn(signedIn, warn);

    await nextTick();
    expect(warn).not.toHaveBeenCalled();

    signedIn.value = true;
    await nextTick();
    expect(warn).toHaveBeenCalledTimes(1);

    signedIn.value = false;
    await nextTick();
    expect(warn).toHaveBeenCalledTimes(1);

    signedIn.value = true;
    await nextTick();
    expect(warn).toHaveBeenCalledTimes(2);
    stop();
  });

  it('runs at boot when the device already has a session', async () => {
    const warn = vi.fn(async () => {});
    const stop = askWhenSomeoneSignsIn(ref(true), warn);
    await nextTick();
    expect(warn).toHaveBeenCalledTimes(1);
    stop();
  });

  it('a failing ask never escapes', async () => {
    const signedIn = ref(true);
    const failure = new Error('boom');
    const warn = vi.fn(async () => {
      throw failure;
    });
    // The rejection is CAUGHT (and logged), not left loose: a loose one is what vitest and the
    // browser report as unhandled, and the only trace of it being handled is the log.
    const logged = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const stop = askWhenSomeoneSignsIn(signedIn, warn);
    await nextTick();
    await new Promise((r) => setTimeout(r, 0));
    expect(warn).toHaveBeenCalledTimes(1);
    expect(logged).toHaveBeenCalledWith(expect.any(String), failure);
    logged.mockRestore();
    stop();
  });
});
