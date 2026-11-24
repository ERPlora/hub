import { describe, expect, it } from 'vitest';

import { mayTick, modeOf, scopesOfApps, scopesOfMode } from './api-key-scopes';

const GRANTABLE = { '*': ['read', 'create', 'update'], shop: ['read', 'create', 'update', 'delete'], tax: ['read'] } as const;

describe('api-key-scopes', () => {
  it('a general mode is its actions on every app', () => {
    expect(scopesOfMode('full')).toEqual({ '*': ['read', 'create', 'update', 'delete'] });
    expect(scopesOfMode('read')).toEqual({ '*': ['read'] });
    expect(scopesOfMode('write')).toEqual({ '*': ['create', 'update', 'delete'] });
  });

  it('per app, «Write» is the creating, changing and deleting who asks may give there', () => {
    const perApp = { shop: ['read', 'write'], tax: ['read'], gone: [] } as const;
    expect(scopesOfApps(perApp, { ...GRANTABLE, shop: ['read', 'create', 'update'] })).toEqual({
      shop: ['read', 'create', 'update'],
      tax: ['read'],
    });
  });

  it('a box is there only for what who asks may give on that app', () => {
    expect([mayTick(GRANTABLE, 'shop', 'read'), mayTick(GRANTABLE, 'shop', 'write')]).toEqual([true, true]);
    expect([mayTick(GRANTABLE, 'tax', 'read'), mayTick(GRANTABLE, 'tax', 'write')]).toEqual([true, false]);
    expect(mayTick(GRANTABLE, 'other', 'read')).toBe(false);
  });

  it('a key on every app reads as its general mode; any other, as none', () => {
    expect(modeOf({ '*': ['read', 'create', 'update', 'delete'] })).toBe('full');
    expect(modeOf({ '*': ['read'] })).toBe('read');
    expect(modeOf({ '*': ['create', 'update', 'delete'] })).toBe('write');
    expect(modeOf({ '*': ['read', 'create'] })).toBeNull();
    expect(modeOf({ shop: ['read'] })).toBeNull();
    expect(modeOf({ '*': ['read'], shop: ['delete'] })).toBeNull();
  });
});
