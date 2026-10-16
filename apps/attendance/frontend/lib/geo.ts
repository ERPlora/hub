// Reading the device's position (ATTENDANCE-F03): ONE wrapper around `navigator.geolocation`, so the
// clock and the settings read a position the same way and get the same typed failures. The distance
// to the workplace is measured by the Hub (it never trusts the device's own figure).

export interface Position {
  lat: number;
  lng: number;
  accuracy_m: number;
}

/** Why a position could not be read. Closed set: each one has its own sentence on screen. */
export type GeoErrorCode = 'denied' | 'unavailable' | 'timeout' | 'unsupported';

export class GeoError extends Error {
  readonly code: GeoErrorCode;

  constructor(code: GeoErrorCode, message?: string) {
    super(message || code);
    this.name = 'GeoError';
    this.code = code;
  }
}

/** How long the device may take to fix a position (the old module's 15 s, high accuracy). */
export const POSITION_TIMEOUT_MS = 15_000;

/** Extra time before giving up on a browser that never calls back (a permission prompt left open). */
const NO_ANSWER_GRACE_MS = 15_000;

const BROWSER_CODES: Record<number, GeoErrorCode> = { 1: 'denied', 2: 'unavailable', 3: 'timeout' };

/** The device's position, or a {@link GeoError} saying why not. */
export function getPosition(): Promise<Position> {
  const geo = (globalThis.navigator as Navigator | undefined)?.geolocation;
  if (!geo || typeof geo.getCurrentPosition !== 'function') return Promise.reject(new GeoError('unsupported'));
  return new Promise<Position>((resolve, reject) => {
    let settled = false;
    const guard = setTimeout(() => finish(() => reject(new GeoError('timeout'))), POSITION_TIMEOUT_MS + NO_ANSWER_GRACE_MS);
    function finish(fn: () => void): void {
      if (settled) return;
      settled = true;
      clearTimeout(guard);
      fn();
    }
    try {
      geo.getCurrentPosition(
        (p) => finish(() => resolve({ lat: p.coords.latitude, lng: p.coords.longitude, accuracy_m: p.coords.accuracy })),
        (e) => finish(() => reject(new GeoError(BROWSER_CODES[e?.code] ?? 'unavailable', e?.message))),
        { enableHighAccuracy: true, timeout: POSITION_TIMEOUT_MS, maximumAge: 0 },
      );
    } catch (e) {
      finish(() => reject(new GeoError('unavailable', e instanceof Error ? e.message : undefined)));
    }
  });
}
