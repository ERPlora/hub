// hub#2305 — **tapping a system notice opened the app wherever it was.**
//
// «WhatsApp customers waiting for an answer (2)», «New booking», «Kitchen order — Table 4»: the
// notice reached the tablet, and tapping it brought the app to the front on whatever screen it had
// been left on. The person then had to hunt for the bell or the diary with the customer waiting.
// Square, Shopify Inbox or Zendesk open the conversation, the booking or the order that rang.
//
// What is pinned: every notice that names a screen of the shell is sent with an id of its own, and
// the tap on THAT id — the only thing the plugin hands back on Android and on iOS alike — leads to
// that screen. A destination that is not a screen of the shell is never remembered (the same
// anchored screen rule as the assistant's links, hub#2204), a tap nobody asked for goes nowhere,
// and nothing here can make the notice that carries it fail.
import { describe, expect, it, vi } from 'vitest';

import {
  createNoticeDoor,
  isNoticeTarget,
  listenForNoticeTaps,
  REMEMBERED_NOTICES,
  type NoticeTapListen,
} from './notice-tap';

/** What the notification plugin hands back when a notice is tapped (Android and iOS alike). */
function tapOf(id: unknown, actionId = 'tap') {
  return { actionId, inputValue: null, notification: { id, title: 'x', body: 'y' } };
}

function door(firstId = 700) {
  const send = vi.fn(async (_title: string, _body: string, _id: number, _path: string | null) => {});
  const navigate = vi.fn((_path: string) => undefined);
  return { send, navigate, notices: createNoticeDoor({ send, navigate, firstId }) };
}

describe('a system notice opens the screen it is about (hub#2305)', () => {
  it('sends the notice with an id and tapping that id opens its screen', async () => {
    const { send, navigate, notices } = door();

    await notices.notify('WhatsApp (2)', 'Tap to open it', '/m/whatsapp_inbox/inbox');

    // The screen travels too since hub#2360, for the taps the shell keeps (notice-tap.hub2360.test.ts).
    expect(send).toHaveBeenCalledWith('WhatsApp (2)', 'Tap to open it', 700, '/m/whatsapp_inbox/inbox');
    notices.tapped(tapOf(700));
    expect(navigate).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenCalledWith('/m/whatsapp_inbox/inbox');
  });

  it('each notice gets its own id, and each tap opens its own screen', async () => {
    const { send, navigate, notices } = door();

    await notices.notify('Kitchen order', 'A-12', '/m/kitchen');
    await notices.notify('New booking', 'Cut · 10:00', '/m/appointments');

    const [first, second] = send.mock.calls.map((c) => c[2]);
    expect(first).not.toBe(second);
    notices.tapped(tapOf(second));
    notices.tapped(tapOf(first));
    expect(navigate.mock.calls).toEqual([['/m/appointments'], ['/m/kitchen']]);
  });

  it('the id travels as a number, which is what Android keeps (the plugin hands it back as sent)', async () => {
    const { send, notices } = door(41);
    await notices.notify('t', 'b', '/m/kitchen');
    expect(send.mock.calls[0]![2]).toBe(41);
    expect(Number.isInteger(send.mock.calls[0]![2])).toBe(true);
  });

  it('a notice with no screen is still sent, and tapping it goes nowhere', async () => {
    const { send, navigate, notices } = door();

    await notices.notify('Printer', 'Out of paper');

    expect(send).toHaveBeenCalledTimes(1);
    notices.tapped(tapOf(send.mock.calls[0]![2]));
    expect(navigate).not.toHaveBeenCalled();
  });

  // hub#2204's lesson: a screen rule without its anchors takes the path INSIDE an external address.
  for (const hostile of [
    'https://evil.example/m/kitchen',
    'https://evil.example/?next=/m/kitchen',
    '//evil.example/m/kitchen',
    'javascript:alert(1)',
    '/m/kitchen/display/more',
    '/m/../settings',
    'm/kitchen',
    '',
  ]) {
    it(`a destination that is not a screen of the shell is never followed: ${JSON.stringify(hostile)}`, async () => {
      const { send, navigate, notices } = door();

      await notices.notify('t', 'b', hostile);

      expect(send).toHaveBeenCalledTimes(1);
      notices.tapped(tapOf(send.mock.calls[0]![2]));
      expect(navigate).not.toHaveBeenCalled();
    });
  }

  it('the screens the notices lead to are screens of the shell', () => {
    for (const path of ['/m/whatsapp_inbox/inbox', '/m/appointments', '/m/kitchen', '/settings#printers', '/system']) {
      expect(isNoticeTarget(path)).toBe(true);
    }
    expect(isNoticeTarget(undefined)).toBe(false);
    expect(isNoticeTarget(42)).toBe(false);
  });

  it('a tap on a notice this session did not send goes nowhere', async () => {
    const { navigate, notices } = door();
    await notices.notify('t', 'b', '/m/kitchen');

    notices.tapped(tapOf(12345));
    notices.tapped(tapOf('700'));
    notices.tapped({});
    notices.tapped(null);
    notices.tapped('tap');
    notices.tapped({ notification: null });

    expect(navigate).not.toHaveBeenCalled();
  });

  it('only the last notices are remembered — the session does not keep every one it ever sent', async () => {
    const { send, navigate, notices } = door(1);
    for (let i = 0; i <= REMEMBERED_NOTICES; i += 1) await notices.notify(`n${i}`, 'b', '/m/kitchen');

    const ids = send.mock.calls.map((c) => c[2]);
    notices.tapped(tapOf(ids[0]));
    expect(navigate).not.toHaveBeenCalled();
    notices.tapped(tapOf(ids[1]));
    notices.tapped(tapOf(ids[ids.length - 1]));
    expect(navigate).toHaveBeenCalledTimes(2);
  });

  it('a notice that cannot be shown never escapes, and is not remembered', async () => {
    const send = vi.fn(async () => {
      throw new Error('denied');
    });
    const navigate = vi.fn();
    const notices = createNoticeDoor({ send, navigate, firstId: 9 });

    await expect(notices.notify('t', 'b', '/m/kitchen')).resolves.toBeUndefined();
    notices.tapped(tapOf(9));
    expect(navigate).not.toHaveBeenCalled();
  });

  it('a navigation that fails does not escape the tap', async () => {
    const send = vi.fn(async () => {});
    const navigate = vi.fn(() => {
      throw new Error('router gone');
    });
    const notices = createNoticeDoor({ send, navigate, firstId: 3 });
    await notices.notify('t', 'b', '/m/kitchen');

    expect(() => notices.tapped(tapOf(3))).not.toThrow();
  });
});

describe('listening for the taps (hub#2305)', () => {
  it('hands every tap the plugin reports to the door', async () => {
    const { send, navigate, notices } = door();
    let report: ((payload: unknown) => void) | undefined;
    const listen: NoticeTapListen = vi.fn(async (cb) => {
      report = cb;
      return () => {};
    });

    await listenForNoticeTaps(notices, listen);
    await notices.notify('t', 'b', '/m/kitchen');
    report!(tapOf(send.mock.calls[0]![2]));

    expect(navigate).toHaveBeenCalledWith('/m/kitchen');
  });

  // The desktop plugin has no tap event, a browser has no plugin at all, and an installed app older
  // than this shell has no permission to listen: none of them can take the boot down.
  it('no listener to be had (browser, desktop, an older app) is not an error', async () => {
    const { notices } = door();

    await expect(listenForNoticeTaps(notices, async () => null)).resolves.toBeTypeOf('function');
    await expect(
      listenForNoticeTaps(notices, async () => {
        throw new Error('notification.register_listener not allowed');
      }),
    ).resolves.toBeTypeOf('function');
  });

  it('the function it returns stops the listener', async () => {
    const { notices } = door();
    const stop = vi.fn();

    const off = await listenForNoticeTaps(notices, async () => stop);
    off();

    expect(stop).toHaveBeenCalledTimes(1);
  });
});
