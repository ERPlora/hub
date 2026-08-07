// **Device mode** in the web (hub#358) — is this the till at the counter or somebody's own device?
//
// The hub answers (`GET /api/device/mode`, hub#357) and the login screen obeys: `shared` gets the
// pinpad, `personal` gets email + password and the long session. The mode is a decision an
// administrator recorded server-side about a device that already proved itself online; this module
// only reads it and, for the settings card, writes it back through the admin door.
//
// **Everything here fails towards the pinpad.** The one thing this client must never do is decide
// on its own that the friction can come off:
//
//   - the value starts at `shared` and only an explicit `personal` from the hub moves it;
//   - anything else — a dead runtime, a 500, a spelling this build does not know, a client that
//     cannot even name its device — resolves to `shared`, and a later failure takes a previously
//     granted `personal` back with it (the trust behind it is revocable: `untrust_device` drops
//     the row, hub#357);
//   - **it is never cached in `localStorage`.** A stored `personal` would be a pinpad switch
//     sitting inside devtools, editable by whoever is holding the device.
//
// None of this is the authorisation boundary — the runtime revalidates every call, and what the
// mode changes is *friction*, never permission. It is the boundary of what the user is ASKED, and
// getting that wrong on the lax side is how a counter till stops attributing sales to a person.
import { ref } from 'vue';

import { resolveDeviceId } from './device';
import { asksForPin, publishPinPolicy, type PinPolicy } from './pin-policy';
import { RUNTIME_URL, runtimeHeaders } from './runtime';

/** How much identity friction a device asks for. The pair is CLOSED (mirror of the runtime). */
export type DeviceMode = 'shared' | 'personal';

/** The strict mode: the counter till, where the hub asks who is standing at it. */
const STRICT: DeviceMode = 'shared';

/**
 * Mode of THIS device as the hub last answered. Starts strict on purpose: the window between
 * mounting the login screen and the answer arriving is not a grey area, it is a device the hub has
 * not vouched for yet.
 */
export const deviceMode = ref<DeviceMode>(STRICT);

/** `true` once the hub answered at least once (the UI can tell "strict" from "not asked yet"). */
export const deviceModeReady = ref(false);

/** A refused write of the mode, carrying the runtime's stable `code` so the reason survives. */
export class DeviceModeError extends Error {
  readonly code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = 'DeviceModeError';
    this.code = code;
  }
}

/**
 * The two spellings the hub knows, and nothing near them — no trimming and no case folding, the
 * same closed set as `DeviceMode::parse` in the runtime. Two spellings on the wire would mean the
 * one that slips through is always the lax one.
 */
function parseMode(value: unknown): DeviceMode | null {
  return value === 'shared' || value === 'personal' ? value : null;
}

/** The reason a runtime rejection gives, from either shape of the error body (object or string). */
function rejection(body: unknown, status: number): DeviceModeError {
  const error = (body as { error?: unknown } | null)?.error;
  if (typeof error === 'string') return new DeviceModeError(error);
  if (error && typeof error === 'object') {
    const { code, message } = error as { code?: unknown; message?: unknown };
    return new DeviceModeError(
      typeof message === 'string' ? message : `device mode → ${status}`,
      typeof code === 'string' ? code : undefined,
    );
  }
  return new DeviceModeError(`device mode → ${status}`);
}

/**
 * Ask the hub what kind of device this is and publish the answer in {@link deviceMode}.
 *
 * **Never throws and never leaves the lax mode standing on a failure.** It is called from the login
 * screen, before any session exists (the `GET` takes none, by design: it is what decides whether
 * the pinpad is painted). A client that cannot name a device does not even ask — an unnamed device
 * is answered `shared` anyway, and asking would only invite reading something into the silence.
 */
export async function loadDeviceMode(): Promise<DeviceMode> {
  const answer = await readDeviceAnswer();
  deviceMode.value = answer.mode;
  // The hub's dial travels on the SAME answer (hub#359) and is published from the same place, so
  // the two halves of the pinpad decision can never be out of step by one request. `publishPinPolicy`
  // overwrites unconditionally, which is what takes a previously granted `never` back on a failure.
  publishPinPolicy(answer.policy);
  deviceModeReady.value = true;
  return answer.mode;
}

/** What the hub said about this device: its mode (hub#358) and the hub's dial (hub#359). */
interface DeviceAnswer {
  mode: DeviceMode;
  /** `undefined` when the hub did not say — `publishPinPolicy` reads that as "keep asking". */
  policy?: unknown;
}

async function readDeviceAnswer(): Promise<DeviceAnswer> {
  const deviceId = await resolveDeviceId().catch(() => null);
  if (!deviceId) return { mode: STRICT };
  try {
    const res = await fetch(`${RUNTIME_URL}/api/device/mode`, {
      method: 'GET',
      headers: { 'X-Device-Id': deviceId },
    });
    // The status is checked FIRST: a 500 from a proxy or a half-written handler must not be read
    // for a mode or a policy, however valid-looking the body it carries is.
    if (!res.ok) return { mode: STRICT };
    const body = (await res.json()) as { data?: { mode?: unknown; pin_policy?: unknown } };
    return { mode: parseMode(body?.data?.mode) ?? STRICT, policy: body?.data?.pin_policy };
  } catch {
    // Offline, 502, malformed body: the hub did not say `personal` and did not say `never`.
    return { mode: STRICT };
  }
}

/**
 * Record what kind of device this is (`PUT /api/device/mode`). The runtime demands an **admin
 * session** — the same door as settings, the API keys and the role catalogue — and refuses a device
 * that never did an online login (`hub.device.unknown_device`).
 *
 * Without `deviceId` it describes the device making the request: "this device is mine", from the
 * device itself. Throws {@link DeviceModeError} on refusal, keeping the code so the screen can say
 * WHY; {@link deviceMode} only ever moves to what the server confirms, never to what was asked for.
 */
export async function setDeviceMode(mode: DeviceMode, deviceId?: string): Promise<DeviceMode> {
  const target = deviceId?.trim();
  const asking = await resolveDeviceId().catch(() => null);
  const res = await fetch(`${RUNTIME_URL}/api/device/mode`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...runtimeHeaders(),
      ...(asking ? { 'X-Device-Id': asking } : {}),
    },
    body: JSON.stringify({ ...(target ? { device_id: target } : {}), mode }),
  });
  const body = (await res.json().catch(() => null)) as { data?: { mode?: unknown } } | null;
  if (!res.ok) throw rejection(body, res.status);
  const confirmed = parseMode(body?.data?.mode);
  // A 200 whose body is not one of the two is not a success we can act on: adopting it would mean
  // guessing, and the only safe guess would be the one that contradicts what the admin just saw.
  if (!confirmed) throw new DeviceModeError(`device mode → unreadable answer`);
  deviceMode.value = confirmed;
  deviceModeReady.value = true;
  return confirmed;
}

/**
 * Does the login screen offer the pinpad? The whole decision, in one place.
 *
 * Three conditions, an AND, and none of them substitutes for another:
 *
 *  - **`shared`** is what makes four digits the right question — several people take turns at this
 *    device (hub#358);
 *  - **device-trust** is what makes them *usable at all* — a PIN only works where an online login
 *    already happened (§2.9, hub#330);
 *  - **the dial still asks** — `never` is the one-person shop that decided not to identify who
 *    sells (hub#359).
 *
 * Not offering the pinpad never grants anything: what remains is the account route, which is
 * strictly stronger. That is why this can be an AND without being a way in.
 *
 * The parameter is required on purpose. A default would let a caller keep the old, dial-blind
 * behaviour by simply not knowing about it — and the caller that forgets is the login screen.
 */
export function offersPinLogin(mode: DeviceMode, trusted: boolean, policy: PinPolicy): boolean {
  return mode === 'shared' && trusted && asksForPin(policy);
}
