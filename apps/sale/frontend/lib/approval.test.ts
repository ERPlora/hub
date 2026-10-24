// The till's manager approval (BASE-F84): the ordinary door first; when it is refused with the code of a manager's
// action, the manager's door — directly for whoever holds the permission, through «An approval is needed» for anybody
// else. Any other refusal, and a manager's door that is refused too, reach the screen untouched.
import { ApiError } from '@erplora/ui/sdk';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { withApproval } from '../../../../base/frontend/lib/approval';
import { throughManager } from './approval';

vi.mock('../../../../base/frontend/lib/approval', () => ({ withApproval: vi.fn() }));
// The approval itself (the dialog, the repeat with the pass) is base's: here a manager always approves.
beforeEach(() => {
  vi.mocked(withApproval).mockReset().mockImplementation((run) => run());
});

const OVER = new ApiError(409, 'sale.discount_over_limit', 'Above the maximum.');

describe('throughManager', () => {
  it('what the ordinary door lets through is left alone', async () => {
    const manager = vi.fn();
    await expect(throughManager(async () => 'done', manager, { code: OVER.code, may: false })).resolves.toBe('done');
    expect(manager).not.toHaveBeenCalled();
    expect(withApproval).not.toHaveBeenCalled();
  });

  it('whoever holds the permission goes through the manager’s door with no question', async () => {
    const manager = vi.fn(async () => 'approved');
    const done = await throughManager(() => Promise.reject(OVER), manager, { code: OVER.code, may: true });
    expect(done).toBe('approved');
    expect(manager).toHaveBeenCalledTimes(1);
    expect(withApproval).not.toHaveBeenCalled();
  });

  it('anybody else goes through it with a manager’s approval', async () => {
    const manager = vi.fn(async () => 'approved');
    const done = await throughManager(() => Promise.reject(OVER), manager, { code: OVER.code, may: false });
    expect(done).toBe('approved');
    expect(withApproval).toHaveBeenCalledWith(manager);
  });

  it('a refusal of another kind is the screen’s, and no manager is asked', async () => {
    const other = new ApiError(409, 'sale.discounts_not_allowed', 'No discounts here.');
    const manager = vi.fn();
    await expect(throughManager(() => Promise.reject(other), manager, { code: OVER.code, may: false })).rejects.toBe(other);
    await expect(throughManager(() => Promise.reject(new Error('offline')), manager, { code: OVER.code, may: false })).rejects.toThrow(
      'offline',
    );
    expect(manager).not.toHaveBeenCalled();
    expect(withApproval).not.toHaveBeenCalled();
  });
});
