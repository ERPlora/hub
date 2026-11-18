// What the e2e of Staff share: how a spec picks a member in a staff `Combo`, and how it takes away the people,
// schedules, time off and roles it made.
import { expect, type Page } from '@playwright/test';

import { psql } from './helpers';

/** Picks, in a staff `Combo`, the option that names `name`, searching the server by `text`. */
export async function pickMember(page: Page, field: string, text: string, name: string): Promise<void> {
  const input = page.locator(`[data-testid=${field}] input`);
  await input.click();
  await input.fill(text);
  await page.locator(`[data-testid^=${field}-option-]`, { hasText: name }).first().click();
  // Choosing closes the list: nothing of it is left over the next field.
  await expect(page.locator(`[data-testid^=${field}-option-]`)).toHaveCount(0);
}

/** Deletes the people whose first name starts with `tag` (with their schedules and time off) and the roles named so. */
export function staffCleanUp(tag: string): void {
  const members = `select id from staff_member where first_name like '${tag}%'`;
  psql(
    [
      `delete from staff_timeoff where member_id in (${members})`,
      `delete from staff_scheduleday where schedule_id in (select id from staff_schedule where member_id in (${members}))`,
      `delete from staff_schedule where member_id in (${members})`,
      `delete from staff_member where first_name like '${tag}%'`,
      `delete from staff_role where name like '${tag}%'`,
    ].join('; '),
  );
}
