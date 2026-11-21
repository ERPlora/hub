// The booking page's way to base's public door: its own operations, posted under the business's slug. How the door
// sends an input, reads a refusal and the business's money is base's (`base/frontend/lib/public-door.test.ts`).
import type { SpaConfig } from '@erplora/ui/sdk';
import { describe, expect, it, vi } from 'vitest';

import type { DoorDeps } from '../../../../base/frontend/lib/public-door';
import { openDoor, PUBLIC_OPERATIONS } from './door';

const CONFIG = {
  csrfCookieName: 'hub_csrftoken',
  csrfHeader: 'X-CSRFToken',
  liveUrl: '/api/live',
  apiBase: '/api',
  lang: 'en',
  deviceIdStorageKey: 'hub.device',
} satisfies SpaConfig;

function deps(answer: Response): DoorDeps & { fetchImpl: ReturnType<typeof vi.fn> } {
  const store = new Map<string, string>();
  return {
    fetchImpl: vi.fn(async () => answer),
    storage: { getItem: (key) => store.get(key) ?? null, setItem: (key, value) => void store.set(key, value) },
    cookies: () => 'hub_csrftoken=tok',
    randomUUID: () => '00000000-0000-4000-8000-000000000000',
    doc: document.implementation.createHTMLDocument('booking'),
  };
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

describe('the public door of the booking page', () => {
  it('posts every public operation of the page to its address under the business’s slug', async () => {
    const d = deps(json(200, {}));
    d.fetchImpl.mockImplementation(async () => json(200, {}));
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
