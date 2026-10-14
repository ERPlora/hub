// The closed lists of the staff app as the person reads them: every status, leave type and request
// status the server knows, each with the tone of its pill. A cell and the picker next to it read the
// same list, so they can never name one value two ways (the old module's staff#37).
import { describe, expect, it } from 'vitest';

import {
  LEAVE_TYPES,
  MEMBER_STATUSES,
  memberStatusTone,
  REQUEST_STATUSES,
  requestStatusTone,
  WEEKDAYS,
} from './enums';

describe('the staff enums', () => {
  it('list the values of schemas.py, in the order the pickers offer them', () => {
    expect(MEMBER_STATUSES).toEqual(['active', 'on_leave', 'inactive']);
    expect(LEAVE_TYPES).toEqual(['vacation', 'sick', 'personal', 'training', 'other']);
    expect(REQUEST_STATUSES).toEqual(['pending', 'approved', 'rejected', 'cancelled']);
    expect(WEEKDAYS).toEqual([0, 1, 2, 3, 4, 5, 6]);
  });

  it('paint an active person green, on leave amber and inactive grey', () => {
    expect(MEMBER_STATUSES.map(memberStatusTone)).toEqual(['success', 'warning', 'neutral']);
  });

  it('paint a pending request amber, approved green, rejected red and cancelled grey', () => {
    expect(REQUEST_STATUSES.map(requestStatusTone)).toEqual(['warning', 'success', 'danger', 'neutral']);
  });
});
