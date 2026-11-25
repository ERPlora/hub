import { describe, expect, it } from 'vitest';

import { askedScopes, modeOf } from './api-key-scopes';

const GRANTABLE = { '*': ['read', 'create', 'update'], shop: ['read', 'create', 'update', 'delete'], tax: ['read'] } as const;

describe('api-key-scopes', () => {
  it('on every app, what is ticked there and nothing of what is ticked app by app', () => {
    expect(askedScopes({ '*': ['read', 'update'], shop: ['delete'] }, GRANTABLE, true)).toEqual({ '*': ['read', 'update'] });
  });

  it('on chosen apps, what is ticked on each and nothing on every app; an app with nothing ticked is left out', () => {
    expect(askedScopes({ '*': ['read'], shop: ['read', 'delete'], tax: [] }, GRANTABLE, false)).toEqual({ shop: ['read', 'delete'] });
  });

  it('never what who asks may not give there (any more)', () => {
    expect(askedScopes({ shop: ['read', 'delete'], tax: ['update'], gone: ['read'] }, { ...GRANTABLE, shop: ['read'] }, false)).toEqual({
      shop: ['read'],
    });
    expect(askedScopes({ '*': ['read', 'delete'] }, GRANTABLE, true)).toEqual({ '*': ['read'] });
    expect(askedScopes({ '*': ['read'] }, {}, true)).toEqual({});
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
