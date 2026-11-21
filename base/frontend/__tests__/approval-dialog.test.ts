// The apps' helper of a manager's approval (BASE-F84). `modalControllerStub` ends the dialog without painting it, so a
// test has no use for the real ApprovalDialog; importing it made Vite transform its whole graph inside the budget of
// whichever test reached the approval first, past Vitest's 5 s on a loaded machine (hub#558). This asserts what was
// opened, not how long it took: a ceiling in milliseconds would fail under load, which is the very bug.
import { ApiError } from '@erplora/ui/sdk';
import { modalController } from '@ionic/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { IonModalStub } from '../../../packages/ui/src/components/FormModal/__tests__/ionModalStub';
import { withApproval } from '../lib/approval';
import { APPROVED_BY_MANAGER, approvalDialog, asksApproval, ionicWithApprovalDialog } from './approval-dialog';

vi.mock('@ionic/vue', async (importOriginal) => (await import('./approval-dialog')).ionicWithApprovalDialog(importOriginal));

afterEach(() => {
  vi.restoreAllMocks();
  approvalDialog.reset();
});

/** A stand-in for Ionic Vue: only what the factory reads or keeps. */
function fakeIonic() {
  const dismiss = vi.fn();
  const ionic = { IonModal: { name: 'IonModal' }, IonButton: { name: 'IonButton' }, modalController: { create: vi.fn(), dismiss } };
  return { ionic, importOriginal: async () => ionic as unknown as typeof import('@ionic/vue'), dismiss };
}

describe('ionicWithApprovalDialog', () => {
  it('ends the approval dialog as the test says, with the inline IonModal as the test double and the rest of Ionic Vue', async () => {
    const { ionic, importOriginal, dismiss } = fakeIonic();
    const question = { operation: 'sale.order.void', label: 'Void the sale', fingerprint: 'f'.repeat(64) };

    const mocked = await ionicWithApprovalDialog(importOriginal);
    const dialog = await mocked.modalController.create({ component: 'approval-dialog', componentProps: { question } });

    expect(await dialog.onDidDismiss()).toEqual(APPROVED_BY_MANAGER);
    expect(approvalDialog.questions).toEqual([question]);
    expect(mocked.modalController.dismiss).toBe(dismiss);
    expect(mocked.IonModal).toBe(IonModalStub);
    expect(mocked.IonButton).toBe(ionic.IonButton);
  });
});

describe('approval-dialog', () => {
  it('a test that reaches the approval opens a stand-in, never the real dialog (hub#558)', async () => {
    const create = vi.spyOn(modalController, 'create');
    const question = asksApproval('sale.order.add_open_line', 'Sell at an open price').error;
    const run = vi.fn(async () => {
      if (run.mock.calls.length === 1) {
        throw new ApiError(403, question.code, question.message, undefined, { approval: question.approval });
      }
      return 'done';
    });

    await expect(withApproval(run)).resolves.toBe('done');

    expect(create.mock.calls.map(([options]) => options.component)).toEqual([{ name: 'ApprovalDialogStandIn' }]);
  });
});
