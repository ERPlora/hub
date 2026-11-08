// What a spec does after it writes `a`'s rows of `base_appactivation` by hand (an app put off as a business that never
// turned it on, the rows put back after): the Hub keeps the apps off of a business in its cache for a minute
// (`base.activation`), so the spec makes it read them now. Shared piece (hub#997, hub#837): `base-apps-born-off.spec.ts`
// still keeps its own copy and moves here once hub#1003, which rewrites its imports, is in.
import { type BrowserContext, expect } from '@playwright/test';

import { A, api } from './helpers';

/** Tasks turned `first` and then `then` in `a` through Apps (`/api/apps/<enable|disable>`): a change the Hub forgets
 * its cache of the apps off for, at its COMMIT, leaving the rest as it was (Tasks needs only Staff). */
export async function bounceTasks(
  context: BrowserContext,
  first: 'enable' | 'disable',
  then: 'enable' | 'disable',
): Promise<void> {
  for (const action of [first, then]) {
    const answer = await api(context, A, 'POST', `/apps/${action}`, { app: 'task' });
    expect(answer.status, `Tasks: ${action} ${JSON.stringify(answer.data)}`).toBe(200);
  }
}
