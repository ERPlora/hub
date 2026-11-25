// Shared steps of the specs where somebody needs a manager's approval (BASE-F84): «An approval is needed» and the owner
// approving with their PIN on the other person's own device. The owner's PIN exists only while a file runs, after the
// other person has entered (a PIN in hub `a` turns every browser's way in into the PIN pad: base-access.spec.ts), and it
// goes with the approvals it recorded, before and after. Both are told by their session, not by their email (a hub
// database kept from a stack whose SaaS was created again holds an older account with each email): the PIN and the
// approvals of every account of those emails go.
import { type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { A, api, EMPLOYEE, OWNER, psql, usernamesOf } from './helpers';

const OWNER_PIN = '2468';

/** Somebody signed in on a browser of their own. */
export interface Side {
  context: BrowserContext;
  page: Page;
}

/** No PIN of the owner's left behind, in any of their accounts: the business's way in stays erplora.com's. */
export function forgetThePin(): void {
  psql(`UPDATE base_credential SET pin_hash = '', pin_set_at = NULL WHERE username IN (${usernamesOf(OWNER.email)})`);
}

/** Nor any approval the employee asked for, in any of their accounts: those of an action of `app`. */
export function forgetThePinAndTheApprovals(app: string): void {
  forgetThePin();
  psql(`DELETE FROM base_approval WHERE requested_by IN (${usernamesOf(EMPLOYEE.email)}) AND operation LIKE '${app}.%'`);
}

/** Nor those of `operation` alone, since the file started (`''`: it did not). */
export function forgetThePinAndTheApprovalsSince(started: string, operation: string): void {
  forgetThePin();
  if (!started) return;
  psql(
    `DELETE FROM base_approval WHERE requested_by IN (${usernamesOf(EMPLOYEE.email)}) AND operation = '${operation}' AND created_at >= '${started}'`,
  );
}

/** The owner chooses a PIN («My profile»): who may approve, on the other person's device. */
export async function ownerChoosesPin(owner: BrowserContext, pin = OWNER_PIN): Promise<void> {
  const chosen = await api<{ set: boolean }>(owner, A, 'POST', '/me/pin', { pin });
  expect(chosen.status, JSON.stringify(chosen.data)).toBe(200);
}

/** «An approval is needed», over the screen that asked. */
export const approvalDialog = (page: Page): Locator => page.locator('ion-modal').filter({ has: page.getByTestId('approval-action') });

/** The owner approves on the other person's device: their face (when there is a choice) and their PIN. */
export async function ownerApproves(page: Page): Promise<void> {
  const dialog = approvalDialog(page);
  const faces = dialog.getByTestId('pin-face');
  if (await faces.count()) await faces.first().click();
  for (const digit of OWNER_PIN) await dialog.getByTestId(`pinpad-key-${digit}`).click();
}
