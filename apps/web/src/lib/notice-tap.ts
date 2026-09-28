// hub#2305 — **a system notice opens the screen it is about.**
//
// The kitchen order, the appointments and the bell's counters all warned the device through a
// system notice, and tapping any of them brought the app to the front on whatever screen it had
// been left on: the person had to find the conversation, the booking or the order on their own,
// with the customer waiting. Square, Shopify Inbox or Zendesk open what rang.
//
// How: every notice that names a screen is sent with an id of its own, and this door remembers
// which screen that id leads to. The notification plugin reports a tap with the notice's id — on
// Android and on iOS alike; iOS drops any extra payload on the way back — so the id is the only
// handle that works on both. The map lives in memory: a tap is always on a notice this app sent,
// and when Android has killed the app in between, the plugin fires the tap before the shell can
// listen anyway.
//
// A destination is followed only when it is a screen of the shell, by the same ANCHORED rule the
// assistant's links use (hub#2204) — a path buried in an external address is not one.
import { SCREEN_PATH } from './assistant-markdown';

/** How many notices the session remembers. A tap is on a recent notice, not on last week's. */
export const REMEMBERED_NOTICES = 50;

const SCREEN = new RegExp(`^(?:${SCREEN_PATH.source})$`);

/** Is this a screen of the shell a notice may lead to? */
export function isNoticeTarget(path: unknown): path is string {
  return typeof path === 'string' && SCREEN.test(path);
}

export interface NoticeDoorDeps {
  /** Shows the system notice under this id — `erplora_notify` in the installed app. */
  send: (title: string, body: string, id: number) => Promise<void>;
  /** The shell's router. */
  navigate: (path: string) => unknown;
  /** The first id handed out. The shell seeds it so a new session does not reuse a live one. */
  firstId: number;
}

export interface NoticeDoor {
  /** Sends a notice; tapping it opens `path` when it is a screen of the shell. Never rejects. */
  notify: (title: string, body: string, path?: string) => Promise<void>;
  /** What the plugin reports when a notice is tapped. */
  tapped: (payload: unknown) => void;
}

export function createNoticeDoor(deps: NoticeDoorDeps): NoticeDoor {
  const targets = new Map<number, string>();
  let next = deps.firstId;

  return {
    async notify(title, body, path) {
      const id = next;
      next += 1;
      try {
        await deps.send(title, body, id);
      } catch {
        // Best-effort, like every notice: what it warns about already happened either way.
        return;
      }
      if (!isNoticeTarget(path)) return;
      targets.set(id, path);
      if (targets.size > REMEMBERED_NOTICES) targets.delete(targets.keys().next().value as number);
    },
    tapped(payload) {
      const id = (payload as { notification?: { id?: unknown } } | null)?.notification?.id;
      if (typeof id !== 'number') return;
      const path = targets.get(id);
      if (!path) return;
      try {
        void Promise.resolve(deps.navigate(path)).catch((e) => console.warn('[notice-tap]', e));
      } catch (e) {
        console.warn('[notice-tap]', e);
      }
    },
  };
}

/** Subscribes to the plugin's taps; `null` when there is no such event here. */
export type NoticeTapListen = (cb: (payload: unknown) => void) => Promise<(() => void) | null>;

/**
 * Hands every tap to the door. Returns the function that stops listening.
 *
 * Never rejects: a browser has no plugin, the desktop plugin reports no taps and an installed app
 * older than this shell has no permission to listen — the notices still go out in all three.
 */
export async function listenForNoticeTaps(door: NoticeDoor, listen: NoticeTapListen): Promise<() => void> {
  try {
    const stop = await listen((payload) => door.tapped(payload));
    return stop ?? (() => {});
  } catch (e) {
    console.warn('[notice-tap] taps cannot be heard here', e);
    return () => {};
  }
}
