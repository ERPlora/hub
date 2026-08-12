// **The devices of a business** in the web (hub#455) — and the gesture "somebody walked off with
// the tablet".
//
// The runtime has been able to revoke a device since hub#15 and nothing in the product could ask it
// to, nor even list the devices to name the one that went missing. With hub#358 in production that
// gap has a price: a device marked `personal` carries a session that lasts **thirty days** and asks
// for no PIN.
//
// **What can be believed about a row.** `deviceId` and `label` are chosen by the device itself —
// the browser mints its own id (`dev_` + 128 random bits, ADR-0257) and the label is the `name` the
// cloud-login body carried, overwritten on every online login. They are here so a person can point
// at the right one **by eye**; nothing in this client decides anything from them. The rest
// (`trustedAt`, the mode, the session counts) the hub wrote itself.
//
// **Nothing is optimistic.** A revocation that was refused must never look like one that happened:
// the owner has just told the hub a device was stolen, and "done" when it was not is the worst
// outcome this screen can produce. Every non-2xx throws, carrying the runtime's own reason.
import { resolveDeviceId } from './device';
import { RUNTIME_URL, runtimeHeaders } from './runtime';

/** How much identity friction a device asks for (mirror of the runtime's closed pair). */
export type DeviceMode = 'shared' | 'personal';

/** A device this business has signed in on, as the owner's list paints it. */
export interface HubDevice {
  /** The `X-Device-Id` it presents. **Chosen by the device**: it names, it never grants. */
  deviceId: string;
  /**
   * What the **business** calls it — "Barra", "Cocina" (hub#494). Written only by an administrator
   * and never by a login, so it is the one field on this row worth deciding from. `''` = nobody has
   * named it yet, which the screen says out loud instead of filling in.
   */
  name: string;
  /** Name of the last account that signed in online on it. Chosen by the device too. */
  label: string;
  /** When this hub first trusted it. Written by the hub. */
  trustedAt: string;
  /** What the login will actually do on it — read strictly, see {@link readMode}. */
  mode: DeviceMode;
  /** How many sessions are open on it right now. */
  openSessions: number;
  /** When the most recent of those sessions was opened; `''` when nobody is signed in. */
  lastSignIn: string;
  /** When the longest-lived of those runs out; `''` when nobody is signed in. */
  signedInUntil: string;
  /** `true` when this is the device the owner is holding right now. Decided by the **hub**. */
  current: boolean;
}

/** What a revocation actually did, as the hub reports it. */
export interface Revocation {
  /** `false` when the hub no longer knew the device — not an error, see the runtime. */
  wasKnown: boolean;
  /** Sessions that stopped working because of this. */
  sessionsClosed: number;
  /** `true` when the device just cut off is the one making the request. */
  wasCurrent: boolean;
}

/** A refused read or write, carrying the runtime's own reason so the screen can show it. */
export class DevicesError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DevicesError';
  }
}

/** The reason a rejection gives, from either shape of the error body (string or object). */
function rejection(body: unknown, status: number): DevicesError {
  const error = (body as { error?: unknown } | null)?.error;
  if (typeof error === 'string') return new DevicesError(error);
  if (error && typeof error === 'object') {
    const { message } = error as { message?: unknown };
    if (typeof message === 'string') return new DevicesError(message);
  }
  return new DevicesError(`devices → ${status}`);
}

/**
 * The mode of a row, read the same way the login reads it: **fail-closed**.
 *
 * The one direction that matters — a value this build cannot read is `shared`. A list that showed
 * `personal` for something the hub treats as `shared` would contradict the login screen on exactly
 * the question the owner came to answer.
 */
function readMode(value: unknown): DeviceMode {
  return value === 'personal' ? 'personal' : 'shared';
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function count(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? Math.trunc(value) : 0;
}

/** Headers of a call to this door: the session AUTHORISES, the device id only NAMES. */
async function headers(): Promise<Record<string, string>> {
  const asking = await resolveDeviceId().catch(() => null);
  return { ...runtimeHeaders(), ...(asking ? { 'X-Device-Id': asking } : {}) };
}

/**
 * Every device this business has signed in on (`GET /api/devices`, **admin session**).
 *
 * A row with no usable `device_id` is **dropped**: it could not be revoked and could not be
 * recognised, so painting it would only offer a button that does nothing. An unreadable answer
 * throws rather than resolving to `[]` — "this business has no devices" is a claim, and making it
 * to somebody hunting for a stolen tablet is the one thing this screen must not do.
 */
export async function listDevices(): Promise<HubDevice[]> {
  let res: Response;
  try {
    res = await fetch(`${RUNTIME_URL}/api/devices`, { method: 'GET', headers: await headers() });
  } catch (error) {
    throw new DevicesError(error instanceof Error ? error.message : 'devices → offline');
  }
  const body = (await res.json().catch(() => null)) as { data?: { devices?: unknown } } | null;
  if (!res.ok) throw rejection(body, res.status);
  const rows = body?.data?.devices;
  if (!Array.isArray(rows)) throw new DevicesError('devices → unreadable answer');
  return rows
    .map((row) => row as Record<string, unknown>)
    .filter((row) => text(row?.device_id).trim() !== '')
    .map((row) => ({
      deviceId: text(row.device_id).trim(),
      name: text(row.name),
      label: text(row.label),
      trustedAt: text(row.trusted_at),
      mode: readMode(row.mode),
      openSessions: count(row.open_sessions),
      lastSignIn: text(row.last_sign_in),
      signedInUntil: text(row.signed_in_until),
      // Decided by the hub, which compares against the header it received. Guessing it here would
      // put the "this is the device you are holding" warning on the wrong row.
      current: row.current === true,
    }));
}

/**
 * Cut a device off (`DELETE /api/devices/:id`, **admin session**): its open sessions close and it
 * stops being trusted, taking a `personal` mode with it.
 *
 * The id is percent-encoded because it is a string the device chose, not a path — an id with a
 * slash addressing another route would tell the owner a device was disconnected while it kept
 * working. A blank id never leaves the browser.
 */
/**
 * Give a device the name the business chose (`PUT /api/devices/:id`, **admin session**, hub#494),
 * and answer with the name as the hub stored it.
 *
 * A **different door** from the revocation on purpose: one is undone by typing again, the other
 * signs a shift out. Blank is not an error, it takes the name back — the row returns to unnamed.
 * Nothing is optimistic here either: a refusal throws, because a name that did not stick is a name
 * the owner will later trust when pointing at the tablet to cut off.
 */
export async function renameDevice(deviceId: string, name: string): Promise<string> {
  const target = deviceId.trim();
  if (!target) throw new DevicesError('devices → no device named');
  let res: Response;
  try {
    res = await fetch(`${RUNTIME_URL}/api/devices/${encodeURIComponent(target)}`, {
      method: 'PUT',
      headers: { ...(await headers()), 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim() }),
    });
  } catch (error) {
    throw new DevicesError(error instanceof Error ? error.message : 'devices → offline');
  }
  const body = (await res.json().catch(() => null)) as { data?: Record<string, unknown> } | null;
  if (!res.ok) throw rejection(body, res.status);
  return text(body?.data?.name);
}

export async function revokeDevice(deviceId: string): Promise<Revocation> {
  const target = deviceId.trim();
  if (!target) throw new DevicesError('devices → no device named');
  let res: Response;
  try {
    res = await fetch(`${RUNTIME_URL}/api/devices/${encodeURIComponent(target)}`, {
      method: 'DELETE',
      headers: await headers(),
    });
  } catch (error) {
    throw new DevicesError(error instanceof Error ? error.message : 'devices → offline');
  }
  const body = (await res.json().catch(() => null)) as { data?: Record<string, unknown> } | null;
  if (!res.ok) throw rejection(body, res.status);
  const data = body?.data ?? {};
  return {
    wasKnown: data.was_known === true,
    sessionsClosed: count(data.sessions_closed),
    wasCurrent: data.was_current === true,
  };
}
