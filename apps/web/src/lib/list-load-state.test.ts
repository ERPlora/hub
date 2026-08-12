import { describe, expect, it } from 'vitest';

import { listDisplay, type ListLoadState } from './list-load-state';

// «You have no apps» is a FACT about the hub, and the screen was saying it whenever it simply did
// not know yet (hub#770).
//
// Two ways it lied. On a cold load, «My apps» and the panel painted their empty state for the ~3
// seconds before the runtime answered — a hub with twelve apps installed telling its owner it had
// none, right where the action offered is «install your first one». And a failed request was
// flattened to an empty list, so a revoked session (a second device signing in on the Free plan
// displaces the first) read as «somebody uninstalled everything» while the till one tab over was
// still selling.
//
// The rule this encodes: DATA WINS. A list that already has rows keeps showing them while it
// reloads and after a failure — a spinner in place of what the user was reading is a second lie —
// and «empty» is said only when a request came back and said so.

describe('listDisplay', () => {
  const cases: [ListLoadState, number, string][] = [
    ['loading', 0, 'loading'],
    ['error', 0, 'error'],
    ['ready', 0, 'empty'],
  ];

  it.each(cases)('with nothing to show yet, %s says %s', (state, count, expected) => {
    expect(listDisplay(state, count)).toBe(expected);
  });

  it('keeps the rows it already has while it reloads — no flash of nothing', () => {
    expect(listDisplay('loading', 12)).toBe('items');
  });

  it('keeps the rows it already has when the reload FAILS', () => {
    // The last known-good list is still the best answer available, and it is certainly better than
    // «you have no apps». The failure is surfaced elsewhere (a banner, a retry), not by wiping the
    // screen the person was using.
    expect(listDisplay('error', 12)).toBe('items');
  });

  it('says empty only when a request actually came back empty', () => {
    expect(listDisplay('ready', 0)).toBe('empty');
    expect(listDisplay('ready', 3)).toBe('items');
  });
});
