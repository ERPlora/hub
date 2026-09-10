// hub#1732 — **asking for the permission that lets the till warn anybody.**
//
// `POST_NOTIFICATIONS` has been declared in both Android manifests and listed by
// `PermissionPolicy.required()` since hub#337, and the plugin has been able to ask for it in a
// scope since hub#758. What was missing was somebody asking. The only caller was
// `peripherals.notify()` — the kitchen-order path — so on a clean install used for 40 minutes
// (business setup, sector template, till, appointment, sale, charge, printing) `dumpsys` reported:
//
//     android.permission.POST_NOTIFICATIONS: granted=false,
//         flags=[ USER_SENSITIVE_WHEN_GRANTED|USER_SENSITIVE_WHEN_DENIED ]
//
// with no `USER_SET` — the fingerprint of a permission the user was never shown. The other two
// dangerous ones carry it, because their dialog does get shown. And "denied" on Android is close
// to permanent: after two refusals the system stops presenting the dialog at all, so the app
// cannot show a single notice for the life of the install and nothing anywhere says so.
//
// ## Why a sentence of ours goes first
//
// Android's dialog says «Allow ERPlora to send you notifications?» and nothing about what for.
// Asked cold it reads as opportunistic and gets refused — which is why Google's own guidance, and
// every POS that does this well, puts an in-app explanation in front of it and only calls the
// system dialog when the user says yes. The refusal that costs nothing is the one to OUR sheet;
// the refusal that is nearly irreversible is the one to Android's.
//
// ## Why once
//
// «Not now» is an answer. Re-asking every heartbeat is the nagging the guidance exists to prevent,
// and it burns the two chances the system gives us. The way back is the screen — System › your
// printer says the notices are off and offers the ask again (`force`), which is where somebody
// looking for the missing warning would go.
//
// The i18n lives with the CALLER (ADR-0055), same contract as `change-hub.ts`: this file decides
// WHEN to ask and never what it says.
import { alertController } from '@ionic/vue';

import { invokeTauri } from './device';

/**
 * Mirror of `PermissionPolicy.POST_NOTIFICATIONS` (Kotlin) and `POST_NOTIFICATIONS` (Rust). The
 * key of the plugin's status map **is** the permission string, so this literal is what reads the
 * answer — and the same literal the SDK sends as the scope of the request (hub#758).
 */
export const ANDROID_NOTIFICATIONS_PERMISSION = 'android.permission.POST_NOTIFICATIONS';

/** Where the fact that the user has already been asked once survives a restart. */
export const NOTIFICATION_PRIMER_ANSWERED_KEY = 'erplora.notifications.primerAnswered';

/**
 * What this device can do about system notices.
 *
 * `unsupported` is not a failure and must never paint a warning: it is the desktop app, a plain
 * browser, and every Android below 13, where notifications are granted at install time and
 * `PermissionPolicy.required()` leaves the key out of the map on purpose.
 */
export type NotificationPermission = 'unsupported' | 'granted' | 'denied';

/** The words the primer puts in front of the user. The caller owns i18n (ADR-0055). */
export interface NotificationPrimerLabels {
  header: string;
  message: string;
  later: string;
  allow: string;
}

/**
 * Reads the notification permission out of the plugin's status map
 * (`plugin:erplora-android|check_permissions`).
 *
 * An ABSENT key is `unsupported`, never `denied`: the plugin reports only the permissions this
 * Android knows (`PermissionPolicy.statusOf`), and on desktop the whole map is empty. Reading the
 * absence as a refusal would put a "notices are blocked" warning on a Mac that notifies fine.
 */
export function notificationPermission(
  status: Record<string, boolean> | null | undefined,
): NotificationPermission {
  if (!status || !(ANDROID_NOTIFICATIONS_PERMISSION in status)) return 'unsupported';
  return status[ANDROID_NOTIFICATIONS_PERMISSION] ? 'granted' : 'denied';
}

/**
 * Should the explanation go in front of the user right now? Pure, so the rule is one line to read.
 *
 * `force` is the screen asking on the user's behalf after they said no — the only way back, since
 * we deliberately never re-ask on our own. It still cannot bother a device that is already
 * notifying, or one where there is nothing to ask for.
 */
export function shouldRunPrimer(input: {
  permission: NotificationPermission;
  alreadyAnswered: boolean;
  force?: boolean;
}): boolean {
  if (input.permission !== 'denied') return false;
  return input.force === true || !input.alreadyAnswered;
}

/**
 * The i18n keys of the sheet and of the row that reports a refusal, in ONE place.
 *
 * The strings stay with the caller (ADR-0055) — what lives here is the list of keys, so the test
 * next to this file can check every one of them resolves in `en` **and** in `es`. A renamed key
 * would otherwise ship as raw `system.notices.primerHeader` text inside the dialog, which is
 * exactly what nobody sees until a customer does.
 */
export const NOTICE_COPY_KEYS = [
  'system.notices.primerHeader',
  'system.notices.primerMessage',
  'system.notices.primerLater',
  'system.notices.primerAllow',
  'system.notices.blockedTitle',
  'system.notices.blockedDetail',
  'system.notices.blockedAction',
  'system.notices.blockedInSettings',
  'system.notices.turnedOn',
] as const;

/** Binds the four strings of the sheet through the caller's `t`. */
export function primerLabelsFrom(t: (key: string) => string): NotificationPrimerLabels {
  return {
    header: t('system.notices.primerHeader'),
    message: t('system.notices.primerMessage'),
    later: t('system.notices.primerLater'),
    allow: t('system.notices.primerAllow'),
  };
}

/**
 * Is a system notice worth attempting on this device?
 *
 * `false` only for an explicit refusal, and it is not a micro-optimisation: `peripherals.notify()`
 * asks for the permission ITSELF before every notice (hub#758's scope), so calling it after a
 * «no» pops Android's bare dialog with no sentence of ours in front of it — the out-of-context
 * ask hub#1732 exists to remove. Android drops the notice either way, so nothing is lost; what
 * the user gets instead is the row on System › your printer, which says the notices are off and
 * offers to ask again.
 *
 * `unsupported` is a YES: that is the desktop app, a browser and every Android below 13, where
 * `erplora_notify` shows a real notification and no runtime permission gates it.
 */
export function shouldSendNotice(permission: NotificationPermission): boolean {
  return permission !== 'denied';
}

/** The seams. Every one has a production default; the tests inject instead of faking Android. */
export interface EnsureNotificationPermissionDeps {
  labels: NotificationPrimerLabels;
  /** `check_permissions` — what is granted now, without a dialog. */
  check?: () => Promise<Record<string, boolean> | null>;
  /** `request_permissions`, scoped to notifications alone (hub#758). */
  request?: () => Promise<Record<string, boolean> | null>;
  /** Our explanation. `true` = the user wants the notices. */
  confirm?: (labels: NotificationPrimerLabels) => Promise<boolean>;
  readAnswered?: () => boolean;
  writeAnswered?: () => void;
  /** Ask again even though the user already answered. Only the screen sets this. */
  force?: boolean;
}

async function defaultCheck(): Promise<Record<string, boolean> | null> {
  return invokeTauri<Record<string, boolean>>('plugin:erplora-android|check_permissions');
}

async function defaultRequest(): Promise<Record<string, boolean> | null> {
  return invokeTauri<Record<string, boolean>>('plugin:erplora-android|request_permissions', {
    permissions: [ANDROID_NOTIFICATIONS_PERMISSION],
  });
}

/**
 * The in-app sheet. A plain `ion-alert`, like every other confirmation in the shell: the system
 * dialog is what comes next, and two modals of our own before it would be one too many.
 */
async function defaultConfirm(labels: NotificationPrimerLabels): Promise<boolean> {
  const alert = await alertController.create({
    header: labels.header,
    message: labels.message,
    buttons: [
      { text: labels.later, role: 'cancel' },
      { text: labels.allow, role: 'confirm' },
    ],
  });
  await alert.present();
  const { role } = await alert.onDidDismiss();
  // Only an explicit yes counts: a backdrop tap arrives as role `backdrop` and is a "not now".
  return role === 'confirm';
}

function defaultReadAnswered(): boolean {
  try {
    return localStorage.getItem(NOTIFICATION_PRIMER_ANSWERED_KEY) === '1';
  } catch {
    // Storage that refuses to be read cannot prove we asked, and asking twice is better than a
    // till that can never notify.
    return false;
  }
}

function defaultWriteAnswered(): void {
  try {
    localStorage.setItem(NOTIFICATION_PRIMER_ANSWERED_KEY, '1');
  } catch {
    console.warn('[notifications] the answer could not be kept: the primer may appear again');
  }
}

/**
 * Puts the explanation and then Android's dialog in front of the user — at most once — and
 * resolves with the state the system actually ended up in.
 *
 * **Never propagates.** It is called from the print-host alta and from the kitchen-order notice,
 * and neither can fail because a permission could not be asked for: the order still has to print.
 * Everything that goes wrong is logged and answered with the honest state.
 */
export async function ensureNotificationPermission(
  deps: EnsureNotificationPermissionDeps,
): Promise<NotificationPermission> {
  const check = deps.check ?? defaultCheck;
  const request = deps.request ?? defaultRequest;
  const confirm = deps.confirm ?? defaultConfirm;
  const readAnswered = deps.readAnswered ?? defaultReadAnswered;
  const writeAnswered = deps.writeAnswered ?? defaultWriteAnswered;

  let permission: NotificationPermission;
  try {
    permission = notificationPermission(await check());
  } catch (e) {
    // No shell, or a plugin that could not answer. `unsupported` is the honest reading: we do not
    // know that anything is blocked, so nothing is claimed and nothing is asked.
    console.warn('[notifications] the permission state could not be read', e);
    return 'unsupported';
  }
  if (!shouldRunPrimer({ permission, alreadyAnswered: readAnswered(), force: deps.force })) {
    return permission;
  }

  let wanted = false;
  try {
    wanted = await confirm(deps.labels);
  } catch (e) {
    console.warn('[notifications] the explanation could not be shown', e);
    return permission;
  }
  // Recorded BEFORE the system dialog, and that order is load-bearing: the user has now been
  // asked. A reload while Android's dialog is up would otherwise come back and ask again, which
  // spends the second and last chance the system gives us.
  writeAnswered();
  if (!wanted) return permission;

  try {
    return notificationPermission(await request());
  } catch (e) {
    console.warn('[notifications] the permission request failed', e);
    return permission;
  }
}

/**
 * What the screen shows: the state of the notices on this device, asked without disturbing anyone.
 *
 * Same reading as everywhere else — `unsupported` on desktop and in a browser, so the row that
 * consumes this simply is not there.
 */
export async function notificationPermissionState(
  check: () => Promise<Record<string, boolean> | null> = defaultCheck,
): Promise<NotificationPermission> {
  try {
    return notificationPermission(await check());
  } catch (e) {
    console.warn('[notifications] the permission state could not be read', e);
    return 'unsupported';
  }
}
