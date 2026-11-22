// What the e2e of Staff share: how a spec picks a member in a staff `Combo`, the staff record of an account, and how
// it takes away the people, schedules, time off and roles it made.
import { type BrowserContext, expect, type Page } from '@playwright/test';

import { A, api, hubUserIdOf, psql } from './helpers';

/**
 * The staff record linked to the account `email`, made as `firstName` if it has none: one live record per account, so
 * one left by another spec is reused. The account must exist: sign it in first.
 */
export async function recordOf(context: BrowserContext, email: string, firstName: string): Promise<{ id: string; full_name: string }> {
  const user = hubUserIdOf(email);
  expect(user, `${email} has signed in once`).not.toBe('');
  const existing = await api<{ rows: { id: string; full_name: string }[] }>(context, A, 'GET', `/staff/members?user_id=${user}`);
  expect(existing.status).toBe(200);
  if (existing.data.rows[0]) return existing.data.rows[0];
  const made = await api<{ id: string; full_name: string }>(context, A, 'POST', '/staff/members', { first_name: firstName, last_name: Date.now().toString(36), user_id: user });
  expect(made.status, JSON.stringify(made.data)).toBe(201);
  return made.data;
}

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
