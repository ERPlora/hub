// The till's manager approval (BASE-F84; the old hub's HUB_SHELL-F51; Square's and Toast's manager override). What the
// cashier's role does not allow and the app names in `apps.py` `approvals` goes through `withApproval`: the hub asks,
// «An approval is needed» lets a manager approve it with their PIN on this very device, and the command is repeated
// once. Where an ordinary door comes first (a discount within the maximum, an empty check), `throughManager` tries it
// and, refused with the code of the manager's action, takes the manager's door: directly for whoever holds the
// permission, through the approval for anybody else.
import { ApiError } from '@erplora/ui/sdk';

import { withApproval } from '../../../../base/frontend/lib/approval';

export { withApproval };

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
