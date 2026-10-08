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
// handle that works on both.
//
// hub#2360 — and the notice carries its screen too (`path`), because not every tap reaches the page
// that sent it. On the computer the notification plugin reports no click, and on Android a tap that
// has to START the app fires before any page listens: in both the shell keeps the tap, with the
// screen it was sent with, until the page claims it (`claimNoticeTaps`). The page that claims it may
// be a new one whose memory of ids is empty, so a tap that brings its screen back is followed on its
// own — through the same screen rule, since what comes back is not trusted blindly.
//
// A destination is followed only when it is a screen of the shell, by the same ANCHORED rule the
// assistant's links use (hub#2204) — a path buried in an external address is not one.
import { SCREEN_PATH } from './assistant-markdown';
import { whileTheHubLands } from './device';

/** How many notices the session remembers. A tap is on a recent notice, not on last week's. */
export const REMEMBERED_NOTICES = 50;

const SCREEN = new RegExp(`^(?:${SCREEN_PATH.source})$`);

/** Is this a screen of the shell a notice may lead to? */
export function isNoticeTarget(path: unknown): path is string {
  return typeof path === 'string' && SCREEN.test(path);
}

export interface NoticeDoorDeps {
  /**
   * Shows the system notice under this id — `erplora_notify` in the installed app — with the
   * screen it leads to, or `null` when it leads to none (hub#2360).
   */
  send: (title: string, body: string, id: number, path: string | null) => Promise<void>;
  /** The shell's router. */
  navigate: (path: string) => unknown;
  /** The first id handed out. The shell seeds it so a new session does not reuse a live one. */
  firstId: number;
}

export interface NoticeDoor {
  /** Sends a notice; tapping it opens `path` when it is a screen of the shell. Never rejects. */
  notify: (title: string, body: string, path?: string) => Promise<void>;
  /** What the plugin reports when a notice is tapped, or the tap the shell kept (hub#2360). */
  tapped: (payload: unknown) => void;
}

export function createNoticeDoor(deps: NoticeDoorDeps): NoticeDoor {
  const targets = new Map<number, string>();
  let next = deps.firstId;

  return {
    async notify(title, body, path) {
      const id = next;
      next += 1;
      const target = isNoticeTarget(path) ? path : null;
      try {
        await deps.send(title, body, id, target);
      } catch {
        // Best-effort, like every notice: what it warns about already happened either way.
        return;
      }
      if (target === null) return;
      targets.set(id, target);
      if (targets.size > REMEMBERED_NOTICES) targets.delete(targets.keys().next().value as number);
    },
    tapped(payload) {
      const notification = (payload as { notification?: { id?: unknown; extra?: { path?: unknown } | null } } | null)
        ?.notification;
      const id = notification?.id;
      if (typeof id !== 'number') return;
      // What this page remembers wins; a tap it did not see being sent brings its own screen back.
      const brought = notification?.extra?.path;
      const path = targets.get(id) ?? (isNoticeTarget(brought) ? brought : undefined);
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
 * Never rejects: a browser has no plugin, the desktop plugin reports no taps (the shell keeps those,
 * `claimNoticeTaps`) and an installed app older than this shell has no permission to listen — the
 * notices still go out in all three.
 */
export async function listenForNoticeTaps(
  door: NoticeDoor,
  listen: NoticeTapListen,
  wait?: (ms: number) => Promise<void>,
): Promise<() => void> {
  try {
    // The installed app hears the linked hub only once its page has loaded (hub#2658), and this runs
    // at boot: right after the SaaS sends the window here, the first answers are `not_the_linked_hub`.
    const stop = await whileTheHubLands(() => listen((payload) => door.tapped(payload)), wait);
    return stop ?? (() => {});
  } catch (e) {
    console.warn('[notice-tap] taps cannot be heard here', e);
    return () => {};
  }
}

/** Subscribes to the shell's «a tap is waiting»; `null` when there is no such event here. */
export type NoticeTapPoke = (cb: () => void) => Promise<(() => void) | null>;

export interface KeptTapDeps {
  /** Hands over the tap the shell kept, once — `erplora_take_notice_tap` in the installed app. */
  take: () => Promise<unknown>;
  /** The shell's event that says a tap is waiting to be claimed. */
  onPoke: NoticeTapPoke;
}

/**
 * Claims the tap the shell kept for the page (hub#2360) — at boot, for the tap that started the app,
 * and again every time the shell says one is waiting, for a click on the computer. The shell hands
 * each tap over once, so claiming twice never opens a screen twice.
 *
 * Never rejects: a browser has no shell, and an installed app older than this page has no such
 * command — the notices still go out and a click still brings the app to the front.
 */
export async function claimNoticeTaps(door: NoticeDoor, deps: KeptTapDeps): Promise<() => void> {
  const claim = async (): Promise<void> => {
    try {
      const kept = await deps.take();
      if (kept) door.tapped(kept);
    } catch (e) {
      console.warn('[notice-tap] the kept tap cannot be claimed here', e);
    }
  };
  let stop: (() => void) | null = null;
  try {
    stop = await deps.onPoke(() => void claim());
  } catch (e) {
    console.warn('[notice-tap] the shell cannot say a tap is waiting here', e);
  }
  await claim();
  return stop ?? (() => {});
}
