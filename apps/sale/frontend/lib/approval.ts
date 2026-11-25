// The till's manager approval (BASE-F84; Square's and Toast's manager override). What the
// cashier's role does not allow and the app names in `apps.py` `approvals` goes through `withApproval`: the hub asks,
// «An approval is needed» lets a manager approve it with their PIN on this very device, and the command is repeated
// once. Where an ordinary door comes first (a discount within the maximum, an empty check), `throughManager` tries it
// and, refused with the code of the manager's action, takes the manager's door: directly for whoever holds the
// permission, through the approval for anybody else. `mayBegin` tells it before an action begins.
import { ApiError } from '@erplora/ui/sdk';
import { toastError, toastInfo } from '@erplora/ui/shell';

import { withApproval } from '../../../../base/frontend/lib/approval';
import type { Access } from '../../../../base/frontend/lib/use-access';

export { withApproval };

/** Whether an action begins for whoever asks for it, said first: what their role says no to does not, and what it
 *  leaves to a manager begins knowing that one will have to approve it. */
export function mayBegin(access: Access, words: { no: string; approval: string }): boolean {
  if (access === 'no') {
    toastError(words.no);
    return false;
  }
  // At the top edge: the window that opens has its button at the bottom one.
  if (access === 'approval') toastInfo(words.approval, { position: 'top' });
  return true;
}

export async function throughManager<T>(
  ordinary: () => Promise<T>,
  manager: () => Promise<T>,
  { code, may }: { code: string; may: boolean },
): Promise<T> {
  try {
    return await ordinary();
  } catch (error) {
    if (!(error instanceof ApiError) || error.code !== code) throw error;
    return may ? manager() : withApproval(manager);
  }
}
