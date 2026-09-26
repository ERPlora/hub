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
// Why a sentence of ours goes first, and why only once, is the shared rule of every runtime
// permission this app asks for: it lives in `device-permission.ts` (hub#1773 put the second one,
// `ACCESS_LOCAL_NETWORK`, on the same core). What stays here is the identity of THIS permission —
// which one, where its answer is remembered, which i18n keys say it — and the one rule that is
// only true of notices: `shouldSendNotice`.
//
// The memory is its own on purpose: sharing one key with the printer primer would let «not now»
// to one sheet silence the other for the life of the install.
//
// The i18n lives with the CALLER (ADR-0055), same contract as `change-hub.ts`: this file decides
// WHEN to ask and never what it says.
import {
  devicePermissionState,
  ensureDevicePermission,
  permissionStateOf,
  shouldRunPrimer,
  type DevicePermissionState,
  type EnsureDevicePermissionDeps,
  type PermissionPrimerLabels,
} from './device-permission';

export { shouldRunPrimer };

/**
 * Mirror of `PermissionPolicy.POST_NOTIFICATIONS` (Kotlin) and `POST_NOTIFICATIONS` (Rust). The
 * key of the plugin's status map **is** the permission string, so this literal is what reads the
 * answer — and the same literal the SDK sends as the scope of the request (hub#758).
 */
export const ANDROID_NOTIFICATIONS_PERMISSION = 'android.permission.POST_NOTIFICATIONS';

/** Where the fact that the user has already been asked once survives a restart. */
export const NOTIFICATION_PRIMER_ANSWERED_KEY = 'erplora.notifications.primerAnswered';

/** What goes in front of this file's log lines. */
const TAG = 'notifications';

/**
 * What this device can do about system notices.
 *
 * `unsupported` is not a failure and must never paint a warning: it is the desktop app, a plain
 * browser, and every Android below 13, where notifications are granted at install time and
 * `PermissionPolicy.required()` leaves the key out of the map on purpose.
 */
export type NotificationPermission = DevicePermissionState;

/** The words the primer puts in front of the user. The caller owns i18n (ADR-0055). */
export type NotificationPrimerLabels = PermissionPrimerLabels;

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
  return permissionStateOf(status, ANDROID_NOTIFICATIONS_PERMISSION);
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

/** The seams of the primer, minus the two identities this file already knows. */
export type EnsureNotificationPermissionDeps = Omit<
  EnsureDevicePermissionDeps,
  'permission' | 'storageKey' | 'tag'
>;

/**
 * Puts the explanation and then Android's dialog in front of the user — at most once — and
 * resolves with the state the system actually ended up in.
 *
 * **Never propagates.** It is called from the print-host alta and from the kitchen-order notice,
 * and neither can fail because a permission could not be asked for: the order still has to print.
 * Everything that goes wrong is logged and answered with the honest state.
 */
export function ensureNotificationPermission(
  deps: EnsureNotificationPermissionDeps,
): Promise<NotificationPermission> {
  return ensureDevicePermission({
    ...deps,
    permission: ANDROID_NOTIFICATIONS_PERMISSION,
    storageKey: NOTIFICATION_PRIMER_ANSWERED_KEY,
    tag: TAG,
  });
}

/**
 * What the screen shows: the state of the notices on this device, asked without disturbing anyone.
 *
 * Same reading as everywhere else — `unsupported` on desktop and in a browser, so the row that
 * consumes this simply is not there.
 */
export function notificationPermissionState(
  check?: () => Promise<Record<string, boolean> | null>,
): Promise<NotificationPermission> {
  return devicePermissionState(ANDROID_NOTIFICATIONS_PERMISSION, TAG, check);
}

/**
 * The modules the shell sends system notices for, today.
 *
 * The only notice the shell fires is the kitchen order (`print-comanda.ts`) — so a hub without an
 * active module from this list has nothing that would ever use the permission, and asking there
 * asks for nothing (hub#2046). Adding another source is a deliberate change to this list, not a
 * side effect of adding a module.
 */
export const NOTICE_SOURCE_MODULES: readonly string[] = ['kitchen'] as const;

/**
 * Does this hub have anything installed that the shell would ever send a system notice for?
 *
 * `undefined` — the installed set could not be read — answers `false`: not knowing what is
 * installed is never a reason to ask (hub#2046).
 */
export function hasNoticeSource(activeModuleIds: ReadonlySet<string> | undefined): boolean {
  if (!activeModuleIds) return false;
  return NOTICE_SOURCE_MODULES.some((id) => activeModuleIds.has(id));
}

/**
 * The print-host alta's ask, now asked in context (hub#2046): refreshes what is installed and
 * only then asks for the permission — and only when something active would ever use it. Asking on
 * every hub regardless of what it runs is what left a salon — no kitchen — accepting a permission
 * that would never fire.
 *
 * **Never propagates.** Neither a failed refresh nor a failed ask may break the alta that calls
 * this: the print host still has to register either way.
 */
export async function warnIfThereIsSomethingToTell(deps: {
  refresh: () => Promise<void>;
  activeModules: () => ReadonlySet<string> | undefined;
  ask: () => Promise<unknown>;
}): Promise<void> {
  try {
    await deps.refresh();
  } catch {
    // Not knowing what is installed is not a reason to ask, nor to fail the alta.
  }
  if (hasNoticeSource(deps.activeModules())) {
    try {
      await deps.ask();
    } catch {
      // `ask` (`ensureNotificationPermission`) already never throws, but this call must not
      // propagate either way.
    }
  }
}
