// `useLeaveGuard(dirty)`: leaving the editor with unsaved changes asks first (WORKBOOK FLOW-F14:
// «← vuelve a la lista; si hay cambios sin guardar, pregunta antes»); with nothing unsaved it leaves.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { mountFlow } from '../__tests__/mount-flow';
import { useLeaveGuard } from './useLeaveGuard';

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
afterEach(() => mocks.confirm.mockReset());

async function setup(dirty: boolean) {
  const state = ref(dirty);
  const exposed: { mayLeave?: () => Promise<boolean> } = {};
  await mountFlow(
    defineComponent({
      setup() {
        exposed.mayLeave = useLeaveGuard(state).mayLeave;
        return () => h('p');
      },
    }),
  );
  return { state, mayLeave: exposed.mayLeave! };
}

describe('useLeaveGuard', () => {
  it('leaves at once with nothing unsaved', async () => {
    const s = await setup(false);
    expect(await s.mayLeave()).toBe(true);
    expect(mocks.confirm).not.toHaveBeenCalled();
  });

  it('asks first with unsaved changes, and stays when the answer is no', async () => {
    const s = await setup(true);
    mocks.confirm.mockResolvedValue(false);
    expect(await s.mayLeave()).toBe(false);
    expect(mocks.confirm).toHaveBeenCalledWith({
      title: 'Leave without saving?',
      message: 'The changes you made will be lost.',
      tone: 'warning',
      confirmLabel: 'Leave',
      cancelLabel: 'Stay',
    });
    mocks.confirm.mockResolvedValue(true);
    expect(await s.mayLeave()).toBe(true);
  });
});
