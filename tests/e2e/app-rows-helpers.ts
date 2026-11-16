// What a spec does when it writes `a`'s rows of `base_appactivation` by hand (an app put off as a business that never
// turned it on, the rows put back after): it keeps a copy of the rows to put back, and, since the Hub keeps the apps off
// of a business in its cache for a minute (`base.activation`), it makes the Hub read them now.
import { type BrowserContext, expect, test } from '@playwright/test';

import { A, api, psql } from './helpers';

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

/** A copy of `a`'s rows of the apps in the table `copy`: `keep` takes it, `putBack` writes the rows back from it, and it
 *  is dropped after the spec's last test. */
export function appRowsCopy(copy: string): { keep: () => void; putBack: () => void } {
  test.afterAll(() => {
    psql(`drop table if exists ${copy}`);
  });
  return {
    keep: () => {
      psql(`drop table if exists ${copy}; create table ${copy} as select * from base_appactivation where host = 'a'`);
    },
    putBack: () => {
      psql(`delete from base_appactivation where host = 'a'; insert into base_appactivation select * from ${copy}`);
    },
  };
}
