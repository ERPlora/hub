// `erplora.deviceMode` — is the module running on the till at the counter or on somebody's own
// device? The shell resolves it server-side (`GET /api/device/mode` with the NATIVE device id,
// hub#357/#358) into its reactive `deviceMode`; a module cannot ask on its own — the device id
// lives in the Tauri app and the runtime URL is not the page origin, so a module's own
// `fetch('/api/device/mode')` always degrades to `shared`. The SDK carries the shell's answer.
//
// First consumer: the attendance time-clock, which only checks the geofence on `personal`
// devices (Square's rule: the till is already at the shop).
//
// Same leaning as the shell's `device-mode.ts`: anything that is not EXACTLY `personal` is
// `shared` — the strict mode. A module must never be handed the lax mode by accident.
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { ErploraClient, type DeviceMode } from './index.ts';

const client = (opts: ConstructorParameters<typeof ErploraClient>[1]) =>
  new ErploraClient({} as never, opts);

test('deviceMode is shared when the shell injects nothing (fail towards the strict mode)', () => {
  assert.equal(client({}).deviceMode, 'shared');
  assert.equal(new ErploraClient({} as never).deviceMode, 'shared');
});

test('deviceMode is personal when the shell says personal', () => {
  const mode: DeviceMode = 'personal';
  assert.equal(client({ deviceMode: () => mode }).deviceMode, 'personal');
});

test('deviceMode is shared when the shell says shared', () => {
  assert.equal(client({ deviceMode: () => 'shared' }).deviceMode, 'shared');
});

test('deviceMode resolves anything that is not exactly personal to shared', () => {
  // No trimming and no case folding: the same CLOSED pair as `DeviceMode::parse` in the runtime.
  for (const garbage of ['Personal', ' personal', 'kiosk', '', undefined, null, 1, {}]) {
    const c = client({ deviceMode: () => garbage as unknown as DeviceMode });
    assert.equal(c.deviceMode, 'shared', `${JSON.stringify(garbage)} must read as shared`);
  }
});

test('deviceMode is shared when the injected getter throws', () => {
  const c = client({
    deviceMode: () => {
      throw new Error('shell not ready');
    },
  });
  assert.equal(c.deviceMode, 'shared');
});

test('deviceMode is re-evaluated on every read (follows the shell after a revocation)', () => {
  let current: DeviceMode = 'shared';
  const c = client({ deviceMode: () => current });
  assert.equal(c.deviceMode, 'shared');
  current = 'personal';
  assert.equal(c.deviceMode, 'personal');
  // The trust behind `personal` is revocable (hub#357): the module must see it go back.
  current = 'shared';
  assert.equal(c.deviceMode, 'shared');
});

test('deviceMode is read-only for the module', () => {
  const c = client({ deviceMode: () => 'shared' });
  assert.throws(() => {
    (c as unknown as { deviceMode: string }).deviceMode = 'personal';
  }, TypeError);
  assert.equal(c.deviceMode, 'shared');
});
