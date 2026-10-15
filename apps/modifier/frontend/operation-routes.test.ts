// The modifier app's entries of the hub's op → route map (frontend/generated/operations.json, written by
// hand until V3 generates it): the fourteen routed operations of apps/modifier/api.py, queries by GET and
// commands by POST; the two reactions to Inventory have no route.
import { describe, expect, it } from 'vitest';

import { OPERATION_ROUTES } from '../../../frontend/generated/operation-routes';

describe('modifier operation routes', () => {
  it('binds the fourteen routed modifier operations to apps/modifier/api.py', () => {
    const modifier = Object.fromEntries(Object.entries(OPERATION_ROUTES).filter(([op]) => op.startsWith('modifier.')));
    expect(modifier).toEqual({
      'modifier.group.list': { method: 'get', path: '/api/modifier/groups' },
      'modifier.group.get': { method: 'get', path: '/api/modifier/groups/detail' },
      'modifier.group.for_target': { method: 'get', path: '/api/modifier/groups/for_target' },
      'modifier.group.create': { method: 'post', path: '/api/modifier/groups' },
      'modifier.group.update': { method: 'post', path: '/api/modifier/groups/update' },
      'modifier.group.delete': { method: 'post', path: '/api/modifier/groups/delete' },
      'modifier.option.list': { method: 'get', path: '/api/modifier/options' },
      'modifier.option.create': { method: 'post', path: '/api/modifier/options' },
      'modifier.option.update': { method: 'post', path: '/api/modifier/options/update' },
      'modifier.option.delete': { method: 'post', path: '/api/modifier/options/delete' },
      'modifier.link.list': { method: 'get', path: '/api/modifier/links' },
      'modifier.link.attach': { method: 'post', path: '/api/modifier/links/attach' },
      'modifier.link.detach': { method: 'post', path: '/api/modifier/links/detach' },
      'modifier.selection.resolve': { method: 'get', path: '/api/modifier/selections/resolve' },
    });
  });
});
