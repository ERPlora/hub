// Test helper of the till's manager approval (BASE-F84): base's `withApproval` opens «An approval is needed» with
// `@ionic/vue`'s modalController; a test that reaches it mocks `@ionic/vue` with `modalControllerStub` (imported from
// this file in the mock factory, as FormModal's `ionModalStub` is) and says here how the dialog ends: a manager
// approves (`approvalDialog.answer = APPROVED_BY_MANAGER`, the default) or somebody presses «Cancel». The questions it
// was opened with are kept, in order. The dialog is imported when first needed: `approvalSettled()` waits for it. Not
// `mount-sale`: it loads `@ionic/vue`, which the mock factory that imports this file is building.
import { vi } from 'vitest';

import { flush } from '../../../../packages/ui/src/sdk/__tests__/live-harness';

/** What the hub answers a cashier for an action a manager may approve (`base.approvals.ApprovalRequired`). */
export function asksApproval(operation: string, label: string) {
  return {
    error: {
      code: 'requires_elevation',
      message: 'This needs a manager’s approval.',
      approval: { operation, label, fingerprint: 'f'.repeat(64) },
    },
  };
}

export const APPROVED_BY_MANAGER = { role: 'approved', data: 'elev_pass' };
export const CANCELLED = { role: 'cancel', data: null };

export const approvalDialog = {
  answer: APPROVED_BY_MANAGER as { role: string; data: unknown },
  questions: [] as { operation: string; label: string; fingerprint: string }[],
  reset(): void {
    this.answer = APPROVED_BY_MANAGER;
    this.questions = [];
  },
};

/** `modalController` whose dialogs are base's ApprovalDialog: it keeps the question and ends as `answer` says. */
export function modalControllerStub<T extends object>(real: T): T {
  return {
    ...real,
    create: async ({ componentProps }: { componentProps?: { question?: (typeof approvalDialog.questions)[number] } }) => {
      if (componentProps?.question) approvalDialog.questions.push(componentProps.question);
      return { present: async () => undefined, onDidDismiss: async () => approvalDialog.answer };
    },
  };
}

/** Lets the dialog's lazy import land, the approval end and the repeated command answer. */
export async function approvalSettled(): Promise<void> {
  for (let round = 0; round < 2; round++) {
    await vi.dynamicImportSettled();
    await flush();
    await flush();
  }
}
