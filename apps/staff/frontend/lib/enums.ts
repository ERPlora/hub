// The closed lists of the staff app (schemas.py) as the screens offer them, each value with the tone
// of its pill. Labels are i18n keys built from the value (`staff.memberStatus.<value>`…), so a cell
// and the picker next to it read the same catalogue and never name one value two ways.
import type { StatusPillTone } from '@erplora/ui/components';

import type { LeaveType, MemberStatus, TimeOffStatus } from '../operations';

/** What a person can SET (terminated is only reached by «Terminate»), in the order of the pickers. */
export const MEMBER_STATUSES: readonly MemberStatus[] = Object.freeze(['active', 'on_leave', 'inactive']);
export const LEAVE_TYPES: readonly LeaveType[] = Object.freeze(['vacation', 'sick', 'personal', 'training', 'other']);
export const REQUEST_STATUSES: readonly TimeOffStatus[] = Object.freeze(['pending', 'approved', 'rejected', 'cancelled']);
/** Monday = 0 … Sunday = 6, as the server counts them. */
export const WEEKDAYS: readonly number[] = Object.freeze([0, 1, 2, 3, 4, 5, 6]);

const MEMBER_TONES: Readonly<Record<MemberStatus, StatusPillTone>> = {
  active: 'success',
  on_leave: 'warning',
  inactive: 'neutral',
};

const REQUEST_TONES: Readonly<Record<TimeOffStatus, StatusPillTone>> = {
  pending: 'warning',
  approved: 'success',
  rejected: 'danger',
  cancelled: 'neutral',
};

export function memberStatusTone(status: MemberStatus): StatusPillTone {
  return MEMBER_TONES[status] ?? 'neutral';
}

export function requestStatusTone(status: TimeOffStatus): StatusPillTone {
  return REQUEST_TONES[status] ?? 'neutral';
}
