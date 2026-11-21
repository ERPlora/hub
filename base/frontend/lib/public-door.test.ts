// A public page's way to base's public door (`base/public_door.py`): each operation the page names posted to
// `/p/<slug>/api/<operation>` with its input as the JSON body (never the query string: a personal link's token travels
// in it), the page's CSRF token sent back, and the business's money read from the page's own HTML.
import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';

import { DOOR_CONFIG as CONFIG, doorDeps as deps, doorDocument as doc, jsonAnswer as json } from '../__tests__/public-door-deps';
import { doorRoutes, openPublicDoor } from './public-door';

const OPERATIONS = ['invoice.public.ticket', 'invoice.public.substitute'] as const;
const PAGE = { slug: 'salon-lucia', operations: OPERATIONS };

describe('the public door of a page without a session', () => {
  it('posts each operation the page names to its address under the business’s slug, and nothing else', () => {
    const routes = doorRoutes('salon-lucia', OPERATIONS);
    expect(routes).toEqual({
      'invoice.public.ticket': { method: 'post', path: '/p/salon-lucia/api/invoice.public.ticket' },
      'invoice.public.substitute': { method: 'post', path: '/p/salon-lucia/api/invoice.public.substitute' },
    });
  });

  it('sends the input as the JSON body with the page’s CSRF token, and reads the answer', async () => {
    const ticket = { ticket: { number: 'T-1' }, invoice: null, record: null };
    const d = deps(json(200, ticket));
    const door = openPublicDoor(CONFIG, PAGE, d);
    const answer = await door.api.call('invoice.public.ticket', { code: '20261119-0001-K7Q2M9XD3FPA' });
    expect(answer).toEqual(ticket);
    const [url, init] = d.fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/p/salon-lucia/api/invoice.public.ticket');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ code: '20261119-0001-K7Q2M9XD3FPA' });
    expect(init.headers).toMatchObject({ 'X-CSRFToken': 'tok', 'Content-Type': 'application/json' });
  });

  it('a refusal is the API’s error, with its code and message', async () => {
    const message = 'This code opens no ticket.';
    const d = deps(json(404, { error: { code: 'invoice.code_not_found', message } }));
    const door = openPublicDoor(CONFIG, PAGE, d);
    const refused = await door.api.call('invoice.public.ticket', { code: 'x' }).catch((error: unknown) => error);
    expect(refused).toBeInstanceOf(ApiError);
    expect(refused).toMatchObject({ status: 404, code: 'invoice.code_not_found', message });
  });

  it('the amounts are in the business’s money the page’s HTML carries', () => {
    const block = JSON.stringify({ currency: 'PLN', currency_decimals: 2 });
    const door = openPublicDoor(CONFIG, PAGE, deps(json(200, {}), doc(block)));
    expect(door.money.value).toEqual({ currency: 'PLN', decimals: 2 });
  });

  it('without that block the money is unknown, never euros by default', () => {
    expect(openPublicDoor(CONFIG, PAGE, deps(json(200, {}))).money.value).toBeUndefined();
  });
});
