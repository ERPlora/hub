// The apps' helper of a manager's approval (BASE-F84). `modalControllerStub` ends the dialog without painting it, so a
// test has no use for the real ApprovalDialog; importing it made Vite transform its whole graph inside the budget of
// whichever test reached the approval first, past Vitest's 5 s on a loaded machine (hub#558). This asserts what was
// opened, not how long it took: a ceiling in milliseconds would fail under load, which is the very bug.
import { ApiError } from '@erplora/ui/sdk';
import { modalController } from '@ionic/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { withApproval } from '../lib/approval';
import { asksApproval } from './approval-dialog';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { modalControllerStub } = await import('./approval-dialog');
  const ionic = await importOriginal<typeof import('@ionic/vue')>();
  return { ...ionic, modalController: modalControllerStub(ionic.modalController) };
});

afterEach(() => {
  vi.restoreAllMocks();
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
