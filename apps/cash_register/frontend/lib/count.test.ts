// The total of a count as it is typed: each face value scaled once with the currency's decimals and then
// added as whole minor units (0,05 € × 3 = 15, never 0.15000000000000002). Blank, «abc» or «-2» pieces
// count as none — the same the server adds up.
import { describe, expect, it } from 'vitest';

import { countTotal, pieces } from './count';

describe('count', () => {
  it('reads a box as whole pieces', () => {
    expect([pieces('3'), pieces(''), pieces('abc'), pieces('-2'), pieces('2.7'), pieces(4)]).toEqual([3, 0, 0, 0, 2, 4]);
  });

  it('adds the drawer up in minor units of its currency', () => {
    expect(countTotal({ '50': '2', '0.05': '3' }, 2)).toBe(10015);
    expect(countTotal({ '1000': '5', '1': '3' }, 0)).toBe(5003);
    expect(countTotal({ '0.25': 2, '0.005': 3 }, 3)).toBe(515);
    expect(countTotal({}, 2)).toBe(0);
  });
});
