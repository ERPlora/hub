// What the e2e of Attendance share: clocking in from the clock screen.
import { expect, type Locator } from '@playwright/test';

/** «Clock in» on the clock screen `view`: it says when, the status says since when and the day's timer runs. */
export async function clockIn(view: Locator): Promise<void> {
  await view.locator('[data-testid=attendance-clock-in]').click();
  await expect(view.locator('[data-testid=attendance-clock-message]')).toContainText('Clocked in at');
  await expect(view.locator('[data-testid=attendance-clock-status]')).toContainText('Clocked in since');
  await expect(view.locator('[data-testid=attendance-clock-timer]')).toBeVisible();
}
