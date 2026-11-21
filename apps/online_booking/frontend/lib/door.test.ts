// The booking page's way to base's public door: its own operations, posted under the business's slug. How the door
// sends an input, reads a refusal and the business's money is base's (`base/frontend/lib/public-door.test.ts`).
import { describe, expect, it } from 'vitest';

import { DOOR_CONFIG as CONFIG, doorDeps as deps, jsonAnswer as json } from '../../../../base/frontend/__tests__/public-door-deps';
import { openDoor, PUBLIC_OPERATIONS } from './door';

describe('the public door of the booking page', () => {
  it('posts every public operation of the page to its address under the business’s slug', async () => {
    const d = deps(json(200, {}));
    const door = openDoor(CONFIG, 'salon-lucia', d);
    expect(door.slug).toBe('salon-lucia');
    for (const op of PUBLIC_OPERATIONS) await door.api.call(op, {} as never);
    expect(d.fetchImpl.mock.calls.map(([url]) => url)).toEqual(PUBLIC_OPERATIONS.map((op) => `/p/salon-lucia/api/${op}`));
  });

  it('sends the input as the JSON body with the page’s CSRF token, and reads the answer', async () => {
    const d = deps(json(200, { date: '2030-03-05', timezone: 'Europe/Madrid', duration_minutes: 30, slots: [] }));
    const door = openDoor(CONFIG, 'salon-lucia', d);
    const answer = await door.api.call('online_booking.public.slots', { service_ids: ['v1'], date: '2030-03-05' });
    expect(answer.slots).toEqual([]);
    const [url, init] = d.fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/p/salon-lucia/api/online_booking.public.slots');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ service_ids: ['v1'], date: '2030-03-05' });
    expect(init.headers).toMatchObject({ 'X-CSRFToken': 'tok', 'Content-Type': 'application/json' });
  });
});
