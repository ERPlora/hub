// Reading the device's position (the old module's geo.ts, ATTENDANCE-F03): one wrapper around
// `navigator.geolocation` with typed failures, 15 s and high accuracy, and a guard for a browser that
// never answers. The distance to the workplace is the Hub's to measure, not this file's.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GeoError, getPosition, POSITION_TIMEOUT_MS } from './geo';

type Geo = Pick<Geolocation, 'getCurrentPosition'>;

function withGeolocation(geo: Geo | undefined): void {
  Object.defineProperty(globalThis.navigator, 'geolocation', { value: geo, configurable: true });
}

afterEach(() => {
  vi.useRealTimers();
  withGeolocation(undefined);
});

describe('getPosition', () => {
  it('reads latitude, longitude and accuracy with high accuracy and a 15 s timeout', async () => {
    const getCurrentPosition = vi.fn((ok: PositionCallback, _err?: PositionErrorCallback | null, options?: PositionOptions) => {
      expect(options).toEqual({ enableHighAccuracy: true, timeout: 15_000, maximumAge: 0 });
      ok({ coords: { latitude: 40.4168, longitude: -3.7038, accuracy: 9.5 } } as GeolocationPosition);
    });
    withGeolocation({ getCurrentPosition });
    await expect(getPosition()).resolves.toEqual({ lat: 40.4168, lng: -3.7038, accuracy_m: 9.5 });
    expect(POSITION_TIMEOUT_MS).toBe(15_000);
  });

  it.each([
    [1, 'denied'],
    [2, 'unavailable'],
    [3, 'timeout'],
    [9, 'unavailable'],
  ])('the browser’s code %i is «%s»', async (code, expected) => {
    withGeolocation({
      getCurrentPosition: (_ok: PositionCallback, err?: PositionErrorCallback | null) =>
        err?.({ code, message: 'no' } as GeolocationPositionError),
    });
    const error = await getPosition().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(GeoError);
    expect((error as GeoError).code).toBe(expected);
  });

  it('a device without geolocation says so', async () => {
    withGeolocation(undefined);
    await expect(getPosition()).rejects.toMatchObject({ code: 'unsupported' });
  });

  it('a browser that never answers times out instead of keeping the button busy', async () => {
    vi.useFakeTimers();
    withGeolocation({ getCurrentPosition: () => undefined });
    const pending = getPosition().catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(await pending).toMatchObject({ code: 'timeout' });
  });
});
