import { describe, expect, it, vi } from 'vitest';
import { ref } from 'vue';

import { useSavedSwitch } from './saved-switch';

describe('useSavedSwitch', () => {
  it('saves what the person chose, once, and says nothing failed', async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const toggle = useSavedSwitch(ref(false), save);
    await toggle.change(true);
    expect(save.mock.calls).toEqual([[true]]);
    expect(toggle.failed.value).toBe(false);
    expect(toggle.repaint.value).toBe(0);
  });

  it('choosing what is already saved saves nothing', async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const toggle = useSavedSwitch(() => true, save);
    await toggle.change(true);
    expect(save).not.toHaveBeenCalled();
  });

  it('a change that cannot be saved says so and paints the switch again on the saved value', async () => {
    const save = vi.fn().mockRejectedValue(new Error('offline'));
    const toggle = useSavedSwitch(ref(false), save);
    await toggle.change(true);
    expect(toggle.failed.value).toBe(true);
    expect(toggle.repaint.value).toBe(1);
  });

  it('the next change forgets the failure of the one before', async () => {
    const save = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined);
    const toggle = useSavedSwitch(ref(false), save);
    await toggle.change(true);
    await toggle.change(true);
    expect(save).toHaveBeenCalledTimes(2);
    expect(toggle.failed.value).toBe(false);
    expect(toggle.repaint.value).toBe(1);
  });
});
