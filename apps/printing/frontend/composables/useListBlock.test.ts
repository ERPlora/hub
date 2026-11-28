// `useListBlock(list, loadError)`: what a live list of Printing says when it cannot be read — the whole page blocked
// (the app off, or no permission to see it) or, for any other failure, the table's own error with «Retry».
import type { UseLive } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';
import { shallowRef } from 'vue';

import { useListBlock } from './useListBlock';

function list(status: 'loading' | 'live' | 'error', code?: string): UseLive<unknown> {
  return {
    data: shallowRef(undefined),
    status: shallowRef(status),
    error: shallowRef(code ? ({ code } as UseLive<unknown>['error']['value']) : null),
    refresh: () => undefined,
  };
}

describe('useListBlock', () => {
  it('blocks the page when the app is off or the person may not see it, and the table says nothing then', () => {
    for (const code of ['app_inactive', 'permission_denied']) {
      const { blocked, tableError } = useListBlock(list('error', code), () => 'Could not load.');
      expect([blocked.value, tableError.value]).toEqual([code, undefined]);
    }
  });

  it('any other failure is the table’s error, and a list that reads is neither', () => {
    const failed = useListBlock(list('error', 'internal_error'), () => 'Could not load the devices.');
    expect([failed.blocked.value, failed.tableError.value]).toEqual([null, 'Could not load the devices.']);
    const fine = useListBlock(list('live'), () => 'Could not load the devices.');
    expect([fine.blocked.value, fine.tableError.value]).toEqual([null, undefined]);
  });
});
