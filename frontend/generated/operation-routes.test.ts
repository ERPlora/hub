// The op → route map the SDK's API client uses. Written by hand for the PoC (V3 generates it from
// `/api/openapi.json`); these cases pin the routes the shell and the demo depend on.
import { describe, expect, it } from 'vitest';

import { OPERATION_ROUTES } from './operation-routes';

describe('OPERATION_ROUTES', () => {
  it('binds base.session.me to GET /api/me (base/api.py)', () => {
    expect(OPERATION_ROUTES['base.session.me']).toEqual({ method: 'get', path: '/api/me' });
  });

  it('binds the seven demo operations, one input each: no path parameters, the id in the query or the body', () => {
    expect(OPERATION_ROUTES).toMatchObject({
      'demo.item.list': { method: 'get', path: '/api/demo/items' },
      'demo.item.detail': { method: 'get', path: '/api/demo/items/detail' },
      'demo.item.stats': { method: 'get', path: '/api/demo/items/stats' },
      'demo.item.create': { method: 'post', path: '/api/demo/items' },
      'demo.item.update': { method: 'post', path: '/api/demo/items/update' },
      'demo.item.delete': { method: 'post', path: '/api/demo/items/delete' },
      'demo.item.add_line': { method: 'post', path: '/api/demo/items/add_line' },
    });
  });

  it('names every operation <app>.<entity>.<action> and keeps every route under /api/', () => {
    for (const [op, route] of Object.entries(OPERATION_ROUTES)) {
      expect(op).toMatch(/^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/);
      expect(route.path).toMatch(/^\/api\//);
      // ninja's parity binds one parameter (the operation's input): no `{param}` next to a body.
      expect(route.path).not.toMatch(/[{}]/);
    }
  });
});
