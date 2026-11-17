// The booking page's way to base's public door (`base/public_door.py`): each public operation posted to
// `/p/<slug>/api/<operation>` with its input as the JSON body (never the query string: the personal link's token
// travels in it), the page's CSRF token sent back, and the business's money read from the page's own HTML.
import { ApiError, type SpaConfig } from '@erplora/ui/sdk';
import { describe, expect, it, vi } from 'vitest';

import { type DoorDeps, doorRoutes, openDoor, PUBLIC_OPERATIONS } from './door';

const CONFIG = {
  csrfCookieName: 'hub_csrftoken',
  csrfHeader: 'X-CSRFToken',
  liveUrl: '/api/live',
  apiBase: '/api',
  lang: 'en',
  deviceIdStorageKey: 'hub.device',
} satisfies SpaConfig;

function doc(block?: string): Document {
  const page = document.implementation.createHTMLDocument('booking');
  if (block !== undefined) {
    const script = page.createElement('script');
    script.id = 'public-door';
    script.type = 'application/json';
    script.textContent = block;
    page.body.append(script);
  }
  return page;
}

function deps(answer: Response, page = doc()): DoorDeps & { fetchImpl: ReturnType<typeof vi.fn> } {
  const store = new Map<string, string>();
  return {
    fetchImpl: vi.fn(async () => answer),
    storage: { getItem: (key) => store.get(key) ?? null, setItem: (key, value) => void store.set(key, value) },
    cookies: () => 'hub_csrftoken=tok',
    randomUUID: () => '00000000-0000-4000-8000-000000000000',
    doc: page,
  };
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

describe('the public door of the booking page', () => {
  it('posts every public operation of the page to its address under the business’s slug', () => {
    const routes = doorRoutes('salon-lucia');
    expect(Object.keys(routes)).toEqual([...PUBLIC_OPERATIONS]);
    for (const op of PUBLIC_OPERATIONS) {
      expect(routes[op]).toEqual({ method: 'post', path: `/p/salon-lucia/api/${op}` });
    }
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

  it('a refusal is the API’s error, with its code and message', async () => {
    const message = 'This business does not take online bookings right now.';
    const door = openDoor(CONFIG, 'salon-lucia', deps(json(404, { error: { code: 'online_booking.page_disabled', message } })));
    const refused = await door.api.call('online_booking.public.page', {}).catch((error: unknown) => error);
    expect(refused).toBeInstanceOf(ApiError);
    expect(refused).toMatchObject({ status: 404, code: 'online_booking.page_disabled', message });
  });

  it('the prices are in the business’s money the page’s HTML carries', () => {
    const block = JSON.stringify({ currency: 'PLN', currency_decimals: 2 });
    const door = openDoor(CONFIG, 'salon-lucia', deps(json(200, {}), doc(block)));
    expect(door.money.value).toEqual({ currency: 'PLN', decimals: 2 });
  });

  it('without that block the money is unknown, never euros by default', () => {
    expect(openDoor(CONFIG, 'salon-lucia', deps(json(200, {}))).money.value).toBeUndefined();
  });
});
