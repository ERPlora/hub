// The runtime-permission primer, once — the dance `POST_NOTIFICATIONS` (hub#1732) and
// `ACCESS_LOCAL_NETWORK` (hub#1773) both need, and any future dangerous permission will need too.
//
// ## Why a sentence of ours goes first
//
// Android's dialogs describe the MECHANISM, never the purpose: «send you notifications?», «find,
// connect to and determine the relative position of nearby devices?». Asked cold the second one
// reads like tracking, and both get refused. Google's own guidance — and every POS that does this
// well — puts an in-app explanation in front and only calls the system dialog once the user says
// yes. The refusal that costs nothing is the one to OUR sheet; the refusal to Android's is nearly
// irreversible, because after two the system stops presenting the dialog for the life of the
// install.
//
// ## Why once
//
// «Not now» is an answer. Re-asking on every scan or every heartbeat is the nagging the guidance
// exists to prevent, and it burns the two chances the system gives us. The way back is the
// SCREEN, which offers the ask again on purpose (`force`).
//
// ## What stays with the caller
//
// The words (ADR-0055: i18n lives with the caller, never in here) and the two identities — WHICH
// permission and WHERE its answer is remembered. That second one is load-bearing: a single shared
// memory would let the notices sheet answer for the printer sheet, silencing it for the life of
// the install.
import { alertController } from '@ionic/vue';

import { invokeTauri } from './device';

/**
 * What this device can do about a runtime permission.
 *
 * `unsupported` is not a failure and must never paint a warning: it is the desktop app, a plain
 * browser, and every Android below the API level that introduced the permission, where
 * `PermissionPolicy.statusOf` leaves the key out of the map on purpose.
 */
export type DevicePermissionState = 'unsupported' | 'granted' | 'denied';

/** The words the primer puts in front of the user. The caller owns i18n (ADR-0055). */
export interface PermissionPrimerLabels {
  header: string;
  message: string;
  later: string;
  allow: string;
}

/**
 * Reads ONE permission out of the plugin's status map
 * (`plugin:erplora-android|check_permissions`).
 *
 * An ABSENT key is `unsupported`, never `denied`: the plugin reports only the permissions this
 * Android knows, and on desktop the whole map is empty. Reading the absence as a refusal would put
 * a "this is blocked" warning on a device where it works.
 */
export function permissionStateOf(
  status: Record<string, boolean> | null | undefined,
  permission: string,
): DevicePermissionState {
  if (!status || !(permission in status)) return 'unsupported';
  return status[permission] ? 'granted' : 'denied';
}

/**
 * Should the explanation go in front of the user right now? Pure, so the rule is one line to read.
 *
 * `force` is the screen asking on the user's behalf after they said no — the only way back, since
 * we deliberately never re-ask on our own. It still cannot bother a device that already granted
 * the permission, or one where there is nothing to ask for.
 */
export function shouldRunPrimer(input: {
  permission: DevicePermissionState;
  alreadyAnswered: boolean;
  force?: boolean;
}): boolean {
  if (input.permission !== 'denied') return false;
  return input.force === true || !input.alreadyAnswered;
}

/** `check_permissions` — what is granted now, without a dialog. */
export function checkDevicePermissions(): Promise<Record<string, boolean> | null> {
  return invokeTauri<Record<string, boolean>>('plugin:erplora-android|check_permissions');
}

/**
 * `request_permissions`, scoped to ONE permission (hub#758).
 *
 * The scope is not decoration: asked without one, the plugin requested its whole batch, so tapping
 * «Re-scan» popped the local-network dialog and then, with no visible relation to anything, the
 * notifications one — an opportunistic-looking ask the user rightly denies.
 */
export function requestDevicePermission(
  permission: string,
): Promise<Record<string, boolean> | null> {
  return invokeTauri<Record<string, boolean>>('plugin:erplora-android|request_permissions', {
    permissions: [permission],
  });
}

/**
 * `open_app_settings` — opens THIS app's page in the device settings (hub#1886).
 *
 * Once Android stops showing a permission dialog, that page is the only place left to turn the
 * permission back on. Resolves `true` when the page opened and `false` when it could not — an
 * installed app older than the command (the web ships with the hub, the APK with the store) or a
 * device with no such page — so the caller can say where to go instead of leaving the tap silent.
 */
export async function openAppSettings(tag: string): Promise<boolean> {
  try {
    await invokeTauri<null>('plugin:erplora-android|open_app_settings');
    return true;
  } catch (e) {
    console.warn(`[${tag}] the device settings could not be opened`, e);
    return false;
  }
}

/**
 * The in-app sheet. A plain `ion-alert`, like every other confirmation in the shell: the system
 * dialog is what comes next, and two modals of our own before it would be one too many.
 */
export async function confirmWithSheet(labels: PermissionPrimerLabels): Promise<boolean> {
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

/** The seams. Every one has a production default; the tests inject instead of faking Android. */
export interface EnsureDevicePermissionDeps {
  /** The Android permission string — the key of the plugin's map IS the permission. */
  permission: string;
  /** Where the fact that the user has already been asked once survives a restart. */
  storageKey: string;
  labels: PermissionPrimerLabels;
  /** What goes in front of a console warning, so a log line says which permission it is about. */
  tag: string;
  check?: () => Promise<Record<string, boolean> | null>;
  request?: () => Promise<Record<string, boolean> | null>;
  /** Our explanation. `true` = the user wants it. */
  confirm?: (labels: PermissionPrimerLabels) => Promise<boolean>;
  readAnswered?: () => boolean;
  writeAnswered?: () => void;
  /** Ask again even though the user already answered. Only the screen sets this. */
  force?: boolean;
}

export function readAnsweredFlag(storageKey: string): boolean {
  try {
    return localStorage.getItem(storageKey) === '1';
  } catch {
    // Storage that refuses to be read cannot prove we asked, and asking twice is better than a
    // till that can never notify — or never find its printer.
    return false;
  }
}

export function writeAnsweredFlag(storageKey: string, tag: string): void {
  try {
    localStorage.setItem(storageKey, '1');
  } catch {
    console.warn(`[${tag}] the answer could not be kept: the primer may appear again`);
  }
}

/**
 * Puts the explanation and then Android's dialog in front of the user — at most once — and
 * resolves with the state the system actually ended up in.
 *
 * **Never propagates.** Its callers are a print-host alta, a kitchen-order notice and a printer
 * scan, and none of them can fail because a permission could not be asked for: the order still
 * has to print. Everything that goes wrong is logged and answered with the honest state.
 */
/**
 * The primer in flight, per permission. Two askers can reach it before anybody answers — a device
 * booting with a session open AND a printer runs the print-host alta and the sign-in ask together
 * (hub#2306) — and the answered flag is only written once the sheet closes, so both would open a
 * sheet and the second «yes» would spend Android's second, and last, system dialog. The late one
 * joins the sheet that is up; once it closes, the next ask starts fresh.
 */
const primerInFlight = new Map<string, Promise<DevicePermissionState>>();

export function ensureDevicePermission(deps: EnsureDevicePermissionDeps): Promise<DevicePermissionState> {
  const running = primerInFlight.get(deps.storageKey);
  if (running) return running;
  const asking = askOnce(deps).finally(() => primerInFlight.delete(deps.storageKey));
  primerInFlight.set(deps.storageKey, asking);
  return asking;
}

async function askOnce(deps: EnsureDevicePermissionDeps): Promise<DevicePermissionState> {
  const check = deps.check ?? checkDevicePermissions;
  const request = deps.request ?? (() => requestDevicePermission(deps.permission));
  const confirm = deps.confirm ?? confirmWithSheet;
  const readAnswered = deps.readAnswered ?? (() => readAnsweredFlag(deps.storageKey));
  const writeAnswered = deps.writeAnswered ?? (() => writeAnsweredFlag(deps.storageKey, deps.tag));

  let permission: DevicePermissionState;
  try {
    permission = permissionStateOf(await check(), deps.permission);
  } catch (e) {
    // No shell, or a plugin that could not answer. `unsupported` is the honest reading: we do not
    // know that anything is blocked, so nothing is claimed and nothing is asked.
    console.warn(`[${deps.tag}] the permission state could not be read`, e);
    return 'unsupported';
  }
  if (!shouldRunPrimer({ permission, alreadyAnswered: readAnswered(), force: deps.force })) {
    return permission;
  }

  let wanted = false;
  try {
    wanted = await confirm(deps.labels);
  } catch (e) {
    console.warn(`[${deps.tag}] the explanation could not be shown`, e);
    return permission;
  }
  // Recorded BEFORE the system dialog, and that order is load-bearing: the user has now been
  // asked. A reload while Android's dialog is up would otherwise come back and ask again, which
  // spends the second and last chance the system gives us.
  writeAnswered();
  if (!wanted) return permission;

  try {
    return permissionStateOf(await request(), deps.permission);
  } catch (e) {
    console.warn(`[${deps.tag}] the permission request failed`, e);
    return permission;
  }
}

/**
 * What the screen shows: the state of ONE permission on this device, asked without disturbing
 * anyone.
 *
 * Same reading as everywhere else — `unsupported` on desktop and in a browser, so the row that
 * consumes this simply is not there.
 */
export async function devicePermissionState(
  permission: string,
  tag: string,
  check: () => Promise<Record<string, boolean> | null> = checkDevicePermissions,
): Promise<DevicePermissionState> {
  try {
    return permissionStateOf(await check(), permission);
  } catch (e) {
    console.warn(`[${tag}] the permission state could not be read`, e);
    return 'unsupported';
  }
}
