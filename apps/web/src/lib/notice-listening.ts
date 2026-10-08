// hub#2307 — **keeping the installed app listening for notices while nobody looks at it.**
//
// Every notice this shell sends is born in this page: the bell polls its counters (hub#2303), the
// kitchen order and the diary listen to the event socket (hub#2168). On Android, with the screen
// off, the app in the background or the system reclaiming it, neither the poll nor the socket keeps
// running — so the business that turned the notices on was warned only while it did not need it.
//
// The installed app keeps itself running with a foreground service and the ongoing notification
// Android requires for one («ERPlora is listening»), the way the order-taking apps for merchants do
// (Uber Eats Orders, Glovo Partners, Deliveroo Restaurant Hub). This file is the page's half:
// WHEN to ask for it and with which words. The native half is `NoticeListening.kt`.
//
// It listens while somebody is signed in, the hub has something that would ever send a notice
// (the same rule as the permission ask, `hasNoticeSource`) and the notices are not refused —
// otherwise it stops, so a salon without any source is never kept awake for nothing. On desktop
// the command is a no-op and in a browser there is nothing to invoke.
//
// The words live with the catalogue (ADR-0055): the notification is sent in the app's language.
import { watch, type WatchSource, type WatchStopHandle } from 'vue';

import { shouldSendNotice, type NotificationPermission } from './notification-permission';

/** The Android plugin's command; `erplora-android:default` grants it. */
export const KEEP_LISTENING_COMMAND = 'plugin:erplora-android|keep_listening';

/** The i18n keys of the ongoing notification, in ONE place so the test checks `en` and `es`. */
export const NOTICE_LISTENING_COPY_KEYS = [
  'system.notices.listeningTitle',
  'system.notices.listeningBody',
  'system.notices.listeningChannel',
] as const;

export interface NoticeListeningDeps {
  /** Does this hub have anything the shell would ever send a notice for? */
  hasSomethingToTell: () => Promise<boolean>;
  /** The state of the notices on this device, asked without disturbing anyone. */
  permission: () => Promise<NotificationPermission>;
  /** The caller owns i18n (ADR-0055). */
  t: (key: string) => string;
  /** `invokeTauri`: resolves `null` in a browser. */
  invoke: (cmd: string, args: Record<string, unknown>) => Promise<unknown>;
}

export interface NoticeListening {
  /** Brings the listening in line with the session. **Never throws.** */
  sync: (signedIn: boolean) => Promise<void>;
}

const TAG = '[notice-listening]';

export function createNoticeListening(deps: NoticeListeningDeps): NoticeListening {
  async function shouldListen(): Promise<boolean> {
    try {
      if (!(await deps.hasSomethingToTell())) return false;
      return shouldSendNotice(await deps.permission());
    } catch (e) {
      // Not knowing is not a reason to keep the device awake.
      console.warn(TAG, 'could not decide', e);
      return false;
    }
  }

  // Deciding waits for the hub, and the session can close meanwhile: only the last request is
  // carried out, so a slow «start» never lands after the «stop» of the sign-out that followed it.
  let latest = 0;

  return {
    async sync(signedIn) {
      const request = ++latest;
      const on = signedIn && (await shouldListen());
      if (request !== latest) return;
      const args: Record<string, unknown> = on
        ? {
            on: true,
            title: deps.t('system.notices.listeningTitle'),
            body: deps.t('system.notices.listeningBody'),
            channel: deps.t('system.notices.listeningChannel'),
          }
        : { on: false };
      try {
        await deps.invoke(KEEP_LISTENING_COMMAND, args);
      } catch (e) {
        // An app older than the command refuses it, and Android may refuse a start: the notices
        // keep working while the app is on screen, as before.
        console.warn(TAG, on ? 'could not start' : 'could not stop', e);
      }
    },
  };
}

/** Stops the listening when the session closes. Opening one is decided after its ask (`main.ts`). */
export function stopListeningWhenSignedOut(
  signedIn: WatchSource<boolean>,
  listening: NoticeListening,
): WatchStopHandle {
  return watch(signedIn, (now) => {
    if (!now) void listening.sync(false);
  });
}

let registered: NoticeListening | null = null;

/** The boot hands its instance over, so the System screen can reach it. */
export function registerNoticeListening(listening: NoticeListening): void {
  registered = listening;
}

/**
 * The notices were just turned on again from the System screen: listen now, not at the next
 * sign-in. Only reachable signed in. A no-op before the boot registered anything.
 */
export async function resyncNoticeListening(): Promise<void> {
  await registered?.sync(true);
}

/**
 * Stops the listening NOW and waits for the app to say so (hub#2503): «switch business» calls it
 * before forgetting the hub, because afterwards this page is no longer the linked business and the
 * app refuses the order (hub#2642). Never throws; a no-op before the boot registered anything.
 */
export async function stopNoticeListening(): Promise<void> {
  await registered?.sync(false);
}
