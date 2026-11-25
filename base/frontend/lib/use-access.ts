// What the role of the person signed in does with a permission: it does it, it does it only if a manager approves it
// there and then (BASE-F84), or it does not. Read from the session (`base.session.me`), which follows the role as it
// changes, so a screen tells it before an action begins; the hub decides it again when the action is done.
import { type SessionMe, useSession } from '@erplora/ui/shell';
import { computed, type ComputedRef } from 'vue';

import type { SessionMeOut } from '../../../frontend/sdk-types';

export type Access = 'allowed' | 'approval' | 'no';

/** The access to `permission` of the person signed in; it follows the session as it changes. */
export function useAccess(permission: string): ComputedRef<Access> {
  const session = useSession();
  return computed(() => {
    if (session.can(permission)) return 'allowed';
    return approvable(session.me.value).includes(permission) ? 'approval' : 'no';
  });
}

/** The permissions a manager may approve for the person: the Hub's part of the session, which the shell's type lacks. */
function approvable(me: SessionMe | undefined): readonly string[] {
  return (me as SessionMeOut | undefined)?.approvable ?? [];
}
