// «Cancel Receipt T-000123?» (PRINTING-F14): it will not be printed and stays in the queue; an optional
// reason; «Yes, cancel» cancels it and says so; «Back» leaves it; a refusal is said in the server's words.
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountPrinting, words } from '../__tests__/mount-printing';
import type { JobOut } from '../operations';
import CancelJobModal from './CancelJobModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const JOB = { id: 'j1', kind: 'document', document_type: 'receipt', reference: 'T-000123', status: 'failed' } as JobOut;

async function setup() {
  const m = await mountPrinting(CancelJobModal, { props: { open: true, job: JOB } });
  return m;
}

describe('CancelJobModal', () => {
  it('names the job and says what cancelling does', async () => {
    const s = await setup();
    expect(s.inDoc('printing-cancel-job')?.getAttribute('aria-label')).toBe('Cancel Receipt T-000123?');
    expect(words(s.inDoc('printing-cancel-job-body')!)).toBe('It will not be printed, and it stays in the queue with who cancelled it and why.');
  });

  it('cancels it with its reason and says so', async () => {
    const s = await setup();
    await ionValue(s.inDoc('printing-cancel-job-reason'), ' customer left ', 'ionInput');
    s.answer(200, { ...JOB, status: 'cancelled' });
    await click(s.inDoc('printing-cancel-job-submit'));
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/printing/jobs/cancel', query: {}, body: { job_id: 'j1', reason: 'customer left' } },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Job cancelled. It will not be printed.');
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('says the server’s refusal', async () => {
    const s = await setup();
    const message = 'A job that is printing or has printed is not cancelled; this one is printed.';
    s.answer(409, { error: { code: 'printing.job_not_cancellable', message } });
    await click(s.inDoc('printing-cancel-job-submit'));
    expect(words(s.inDoc('printing-cancel-job-error')!)).toContain(message);
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });
});
