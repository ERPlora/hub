import { createShellSession, SESSION_KEY, type SessionMe } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';
import { createApp, type Ref, ref } from 'vue';

import type { SessionMeOut } from '../../../frontend/sdk-types';
import { type Access, useAccess } from './use-access';

const VOID = 'sale.void_sale';

type Held = Pick<SessionMeOut, 'permissions' | 'approvable'>;

function session(held: Partial<Held> = {}): SessionMeOut {
  return {
    user: { id: '1', label: 'Eva' },
    permissions: [],
    approvable: [],
    menu: [],
    apps: [],
    language: 'en',
    scope: { kind: 'host', key: 'a' },
    role: 'Cashier without voids',
    demo: null,
    ...held,
  };
}

function access(me: Ref<SessionMe | undefined>, permission = VOID) {
  const app = createApp({});
  app.provide(SESSION_KEY, createShellSession(me, ref('live')));
  return app.runWithContext(() => useAccess(permission));
}

describe('useAccess', () => {
  it.each<[string, Partial<Held>, Access]>([
    ['allowed: the role does it', { permissions: ['sale.view_sale', VOID] }, 'allowed'],
    ['allowed: everything', { permissions: ['*'] }, 'allowed'],
    ['approval: a manager may approve it', { approvable: ['sale.refund_sale', VOID] }, 'approval'],
    ['no: the role neither does it nor leaves it to a manager', { permissions: ['sale.view_sale'], approvable: ['sale.refund_sale'] }, 'no'],
    ['no: the role does nothing', {}, 'no'],
    ['allowed before approval: whoever does it is never asked', { permissions: [VOID], approvable: [VOID] }, 'allowed'],
  ])('%s', (_name, held, expected) => {
    expect(access(ref(session(held))).value).toBe(expected);
  });

  it('asks for that very permission, never for one that starts like it', () => {
    const me = ref(session({ permissions: ['sale.void_sale_line'], approvable: ['sale.void'] }));
    expect(access(me).value).toBe('no');
  });

  it('is a no until the session arrives, and of somebody signed out', () => {
    expect(access(ref(undefined)).value).toBe('no');
    expect(access(ref({ ...session(), user: null, role: null })).value).toBe('no');
  });

  it('follows the role as it changes', () => {
    const me: Ref<SessionMe | undefined> = ref(session({ approvable: [VOID] }));
    const now = access(me);
    expect(now.value).toBe('approval');

    me.value = session();
    expect(now.value).toBe('no');

    me.value = session({ permissions: [VOID] });
    expect(now.value).toBe('allowed');
  });
});
