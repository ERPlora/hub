// hub#2360 — **clicking a notice on the computer, or after Android had closed the app, opened the
// app wherever it was.**
//
// hub#2305 made a tap open its screen, but only where the notification plugin reports taps to a page
// that is already listening: Android and iOS with the app alive. On the computer the plugin reports
// no click at all, and on Android a tap that has to START the app is fired before the page listens —
// and even if it arrived, the page that remembered `id → screen` is a new one with an empty memory.
//
// What is pinned here, on the page's side:
//  * the notice carries its own destination (`path`) to the shell, so a tap can come back with it
//    and a page that never sent that notice can still follow it;
//  * a tap the shell kept for the page (the computer's click, Android's cold start) is CLAIMED —
//    once at boot and again every time the shell says one is waiting — and handed to the door;
//  * a destination the tap brings back obeys the same anchored screen rule as everything else
//    (hub#2204): the shell hands back what the page sent, but the page does not trust it blindly.
import { describe, expect, it, vi } from 'vitest';

import { claimNoticeTaps, createNoticeDoor, type NoticeTapPoke } from './notice-tap';

/** What the shell hands back for a tap it kept: the notification plugin's shape, with the path. */
function keptTap(id: unknown, path?: unknown) {
  return { notification: { id, extra: path === undefined ? {} : { path } } };
}

function door(firstId = 500) {
  const send = vi.fn(async (_title: string, _body: string, _id: number, _path: string | null) => {});
  const navigate = vi.fn((_path: string) => undefined);
  return { send, navigate, notices: createNoticeDoor({ send, navigate, firstId }) };
}

describe('the notice carries its destination to the shell (hub#2360)', () => {
  it('a notice that leads to a screen hands the shell that screen with its id', async () => {
    const { send, notices } = door();

    await notices.notify('New booking', 'Cut · 10:00', '/m/appointments');

    expect(send).toHaveBeenCalledWith('New booking', 'Cut · 10:00', 500, '/m/appointments');
  });

  it('a notice with no screen, or with something that is not one, hands the shell no path', async () => {
    const { send, notices } = door();

    await notices.notify('Printer', 'Out of paper');
    await notices.notify('t', 'b', 'https://evil.example/m/kitchen');

    expect(send.mock.calls.map((c) => c[3])).toEqual([null, null]);
  });
});

describe('a tap the page did not see being sent still opens its screen (hub#2360)', () => {
  it('follows the path the tap brings back when this page never sent that notice (cold start)', () => {
    const { navigate, notices } = door();

    notices.tapped(keptTap(123_456, '/m/whatsapp_inbox/inbox'));

    expect(navigate).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenCalledWith('/m/whatsapp_inbox/inbox');
  });

  it('the screen this page remembered for the id wins over what the tap brings back', async () => {
    const { navigate, notices } = door();
    await notices.notify('Kitchen order', 'A-12', '/m/kitchen');

    notices.tapped(keptTap(500, '/m/appointments'));

    expect(navigate.mock.calls).toEqual([['/m/kitchen']]);
  });

  for (const hostile of ['https://evil.example/m/kitchen', '//evil.example/m/kitchen', 'javascript:alert(1)', '/m/../settings', 42, '']) {
    it(`a path brought back that is not a screen of the shell is never followed: ${JSON.stringify(hostile)}`, () => {
      const { navigate, notices } = door();

      notices.tapped(keptTap(9, hostile));

      expect(navigate).not.toHaveBeenCalled();
    });
  }

  it('a tap with neither a remembered id nor a path goes nowhere', () => {
    const { navigate, notices } = door();

    notices.tapped(keptTap(77));
    notices.tapped({ notification: { id: 77, extra: null } });

    expect(navigate).not.toHaveBeenCalled();
  });
});

describe('claiming the tap the shell kept (hub#2360)', () => {
  function shell(kept: unknown[]) {
    const take = vi.fn(async () => (kept.length ? kept.shift() : null));
    let poke: (() => void) | undefined;
    const stop = vi.fn();
    const onPoke: NoticeTapPoke = vi.fn(async (cb) => {
      poke = cb;
      return stop;
    });
    return { take, onPoke, stop, poke: () => poke!() };
  }

  it('claims at boot: the tap that started the app opens its screen', async () => {
    const { navigate, notices } = door();
    const s = shell([keptTap(31, '/m/appointments')]);

    await claimNoticeTaps(notices, { take: s.take, onPoke: s.onPoke });

    expect(s.take).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenCalledWith('/m/appointments');
  });

  it('claims again every time the shell says a tap is waiting (a click on the computer)', async () => {
    const { send, navigate, notices } = door();
    const s = shell([]);
    await claimNoticeTaps(notices, { take: s.take, onPoke: s.onPoke });
    await notices.notify('Kitchen order', 'A-12', '/m/kitchen');

    s.take.mockResolvedValueOnce(keptTap(send.mock.calls[0]![2], '/m/kitchen'));
    s.poke();
    await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith('/m/kitchen'));

    expect(s.take).toHaveBeenCalledTimes(2);
    expect(navigate).toHaveBeenCalledTimes(1);
  });

  it('nothing kept is nothing to open', async () => {
    const { navigate, notices } = door();
    const s = shell([]);

    await claimNoticeTaps(notices, { take: s.take, onPoke: s.onPoke });

    expect(navigate).not.toHaveBeenCalled();
  });

  // A browser has no shell, an installed app older than this page has no such command, and a shell
  // that refuses must not take the boot down: the notices still go out in all of them.
  it('a shell that cannot hand a tap over, or cannot say one is waiting, is not an error', async () => {
    const { notices } = door();

    await expect(
      claimNoticeTaps(notices, {
        take: async () => {
          throw new Error('command erplora_take_notice_tap not found');
        },
        onPoke: async () => {
          throw new Error('event.listen not allowed');
        },
      }),
    ).resolves.toBeTypeOf('function');
    await expect(claimNoticeTaps(notices, { take: async () => null, onPoke: async () => null })).resolves.toBeTypeOf(
      'function',
    );
  });

  it('a claim that fails after a poke does not escape', async () => {
    const { notices } = door();
    const s = shell([]);
    await claimNoticeTaps(notices, { take: s.take, onPoke: s.onPoke });
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});

    s.take.mockRejectedValueOnce(new Error('gone'));
    expect(() => s.poke()).not.toThrow();
    await vi.waitFor(() => expect(warn).toHaveBeenCalled());
    warn.mockRestore();
  });

  it('the function it returns stops listening for pokes', async () => {
    const { notices } = door();
    const s = shell([]);

    const off = await claimNoticeTaps(notices, { take: s.take, onPoke: s.onPoke });
    off();

    expect(s.stop).toHaveBeenCalledTimes(1);
  });
});
