// hub#1773 — **asking for the permission that lets the till find its printer.**
//
// `ACCESS_LOCAL_NETWORK` (API 37+) gates ALL traffic to the LAN, so it is what discovery and every
// network print job need. It has been declared in both Android manifests and listed by
// `PermissionPolicy.required()` since hub#337, and the transport has asked for it in a scope since
// hub#758 — but it asked COLD, straight into `plugin:erplora-android|request_permissions`, the
// first time somebody opened the Printing screen and tapped «search».
//
// What Android then shows says the app wants to «find, connect to and determine the relative
// position of nearby devices». Nobody has explained why, so it reads like the app wants to know
// what is around you, and the normal answer is no. The refusal is close to permanent: after two
// the system stops presenting the dialog for the life of the install.
//
// So a sentence of ours goes first — «to find your printer we have to look at the devices on your
// network» — and the ask only happens if the user says yes. Same shape as hub#1732 did for the
// notices, on the shared core in `device-permission.ts`; what lives here is the identity of THIS
// permission: which one, where its answer is remembered, and which i18n keys say it.
//
// **The memory is its own on purpose.** Sharing one key with the notices would let «not now» to
// the notices sheet silence the printer sheet for the life of the install.
//
// The i18n lives with the CALLER (ADR-0055): this file decides WHEN to ask and never what it says.
import { ANDROID_LOCAL_NETWORK_PERMISSION } from '@erplora/module-sdk';

import {
  devicePermissionState,
  ensureDevicePermission,
  permissionStateOf,
  type DevicePermissionState,
  type EnsureDevicePermissionDeps,
  type PermissionPrimerLabels,
} from './device-permission';

export { ANDROID_LOCAL_NETWORK_PERMISSION };

/** Where the fact that the user has already been asked once survives a restart. */
export const LOCAL_NETWORK_PRIMER_ANSWERED_KEY = 'erplora.localNetwork.primerAnswered';

/** What goes in front of this file's log lines. */
const TAG = 'local network';

/** What this device can do about reaching printers on the venue's network. */
export type LocalNetworkPermission = DevicePermissionState;

/**
 * Reads the local-network permission out of the plugin's status map.
 *
 * An ABSENT key is `unsupported`, never `denied`: on the desktop app, in a browser and on every
 * Android below 17 there is no such runtime permission, and claiming the printer search is blocked
 * there would be a false alarm about something that works.
 */
export function localNetworkPermission(
  status: Record<string, boolean> | null | undefined,
): LocalNetworkPermission {
  return permissionStateOf(status, ANDROID_LOCAL_NETWORK_PERMISSION);
}

/**
 * The i18n keys of the sheet and of the row that reports a refusal, in ONE place.
 *
 * The strings stay with the caller (ADR-0055) — what lives here is the list of keys, so the test
 * next to this file can check every one of them resolves in `en` **and** in `es`. A renamed key
 * would otherwise ship as raw `hardware.localNetwork.primerHeader` text inside the dialog, which
 * is exactly what nobody sees until a customer does.
 */
export const LOCAL_NETWORK_COPY_KEYS = [
  'hardware.localNetwork.primerHeader',
  'hardware.localNetwork.primerMessage',
  'hardware.localNetwork.primerLater',
  'hardware.localNetwork.primerAllow',
  'hardware.localNetwork.blockedTitle',
  'hardware.localNetwork.blockedDetail',
  'hardware.localNetwork.blockedAction',
  'hardware.localNetwork.blockedInSettings',
  'hardware.localNetwork.turnedOn',
] as const;

/** Binds the four strings of the sheet through the caller's `t`. */
export function localNetworkPrimerLabelsFrom(
  t: (key: string) => string,
): PermissionPrimerLabels {
  return {
    header: t('hardware.localNetwork.primerHeader'),
    message: t('hardware.localNetwork.primerMessage'),
    later: t('hardware.localNetwork.primerLater'),
    allow: t('hardware.localNetwork.primerAllow'),
  };
}

/** The seams of the primer, minus the two identities this file already knows. */
export type EnsureLocalNetworkPermissionDeps = Omit<
  EnsureDevicePermissionDeps,
  'permission' | 'storageKey' | 'tag'
>;

/**
 * Puts the explanation and then Android's dialog in front of the user — at most once — before the
 * shell goes looking for printers.
 *
 * **Never propagates, never blocks the answer behind it.** It sits in front of a scan, and a scan
 * that cannot run still has something to tell the screen: hub#338 makes a blocked discovery come
 * back as a refusal with a sentence, not as an empty list. So a «no» here simply lets the scan
 * carry on and report what is true.
 */
export function ensureLocalNetworkPermission(
  deps: EnsureLocalNetworkPermissionDeps,
): Promise<LocalNetworkPermission> {
  return ensureDevicePermission({
    ...deps,
    permission: ANDROID_LOCAL_NETWORK_PERMISSION,
    storageKey: LOCAL_NETWORK_PRIMER_ANSWERED_KEY,
    tag: TAG,
  });
}

/**
 * What the screen shows: whether this device is allowed to reach the printers on its network,
 * asked without disturbing anyone.
 */
export function localNetworkPermissionState(
  check?: () => Promise<Record<string, boolean> | null>,
): Promise<LocalNetworkPermission> {
  return devicePermissionState(ANDROID_LOCAL_NETWORK_PERMISSION, TAG, check);
}
