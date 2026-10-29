// Tasks for an employee (`hub_employee`: their own tasks; WORKBOOK «Quién puede qué»), crossing the
// real Staff app: the employee's account hangs a staff record. They see only their tasks (assigned to
// them or created by them), «My tasks» lists the open ones, and the one completed from its card stays
// in its slot as Done; they cannot reach a colleague's task (404), delete (403) or manage projects
// (403, no «+»). The owner is the positive control: they see every task. The employee signs in first:
// on a new database their account is born with that first sign-in.
// flow: TASK-F02 TASK-F03 TASK-F06 TASK-F11 TASK-F12
import { expect, test } from '@playwright/test';

import { A, api, capture, EMPLOYEE, shown, untilStill } from './helpers';
import { cleanUp, named, post, recordOf, rowAction, rowOf, signedIn, TAG } from './task-helpers';

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

type Envelope = { error?: { code: string } };

test('an employee works their own tasks and nobody else’s', async ({ browser }) => {
  const stamp = Date.now().toString(36);
  const employee = await signedIn(browser, '/task/tasks', EMPLOYEE);
  const owner = await signedIn(browser, '/task/tasks');
  try {
    const mine = await recordOf(owner.context, EMPLOYEE.email, 'Emma');
    const colleague = await post<{ id: string }>(owner.context, '/staff/members', { first_name: `${TAG} Ana`, last_name: `Colleague${stamp}` });
    const ownTitle = named('Restock shampoo');
    const otherTitle = named('Ana only');
    const own = await post<{ id: string }>(owner.context, '/task/tasks', { title: ownTitle, assigned_to_id: mine.id, due_date: '2020-01-01' });
    const second = await post<{ id: string }>(owner.context, '/task/tasks', { title: named('Mine too'), assigned_to_id: mine.id });
    const other = await post<{ id: string }>(owner.context, '/task/tasks', { title: otherTitle, assigned_to_id: colleague.id });

    // Positive control: the owner sees all three.
    await expect(rowOf(owner.page, 'task-tasks', otherTitle)).toBeVisible();
    await expect(rowOf(owner.page, 'task-tasks', ownTitle)).toBeVisible();

    const page = employee.page;
    // The record was linked after the first sign-in: the page picks it up on the next visit.
    await page.goto(`${A}/task/tasks`);
    await expect(rowOf(page, 'task-tasks', ownTitle)).toBeVisible();
    await expect(rowOf(page, 'task-tasks', otherTitle)).toHaveCount(0);
    await untilStill(page);
    await capture(page, 'task-employee-all');

    // «My tasks»: the open ones assigned to me; the one I complete stays in its slot, as Done.
    await shown(page).locator('[data-testid=task-view-mine]').click();
    await expect(rowOf(page, 'task-mine', ownTitle)).toBeVisible();
    await rowAction(page, 'task-mine', own.id, 'complete');
    await expect(page.locator('ion-toast')).toContainText('Task completed');
    await expect(rowOf(page, 'task-mine', ownTitle)).toContainText('Done');
    await expect(rowOf(page, 'task-mine', ownTitle)).toBeVisible();
    // The notice is still sliding in: the capture waits until nothing moves.
    await untilStill(page);
    await capture(page, 'task-employee-mine');
    // Leaving the tab lets it go.
    await shown(page).locator('[data-testid=task-view-all]').click();
    await shown(page).locator('[data-testid=task-view-mine]').click();
    await expect(rowOf(page, 'task-mine', ownTitle)).toHaveCount(0);
    expect(second.id).toBeTruthy();

    // The API agrees: a colleague's task does not exist for me; deleting and projects are not mine.
    const refused: ReadonlyArray<readonly [string, unknown, number, string]> = [
      ['/task/tasks/complete', { id: other.id }, 404, 'not_found'],
      ['/task/tasks/delete', { id: own.id }, 403, 'permission_denied'],
      ['/task/projects', { code: `e2e-${stamp}`, name: 'By employee' }, 403, 'permission_denied'],
    ];
    for (const [path, body, status, code] of refused) {
      const res = await api<Envelope>(employee.context, A, 'POST', path, body);
      expect(res.status, path).toBe(status);
      expect(res.data.error?.code, path).toBe(code);
    }

    // Projects: read, no «+».
    await page.goto(`${A}/task/projects`);
    await shown(page).locator('[data-testid=task-projects-empty], [data-testid=task-projects-row]').first().waitFor({ state: 'visible' });
    await expect(shown(page).locator('[data-testid=task-projects-add]')).toHaveCount(0);
  } finally {
    await employee.context.close();
    await owner.context.close();
  }
});
