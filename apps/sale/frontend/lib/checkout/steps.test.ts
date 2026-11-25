import { describe, expect, it } from 'vitest';

import { allAdded, NOTHING_ADDED, stepBlock, withAdded } from './steps';

const TIP = { amount: 120, label: 'Tip', issue: '' };

describe('allAdded', () => {
  it('adds up what the steps add and names only those that add something', () => {
    expect(allAdded([TIP, NOTHING_ADDED, { amount: 30, label: 'Round up', issue: '' }])).toEqual({
      amount: 150,
      label: 'Tip, Round up',
      issue: '',
    });
  });

  it('is nothing with no step, and keeps the first issue a step has', () => {
    expect(allAdded([])).toEqual(NOTHING_ADDED);
    expect(allAdded([TIP, { amount: 0, label: 'Tip', issue: 'Write a valid amount.' }]).issue).toBe('Write a valid amount.');
  });
});

describe('withAdded', () => {
  it('puts what is added, with its name, on the one payment of the charge', () => {
    expect(withAdded([{ method_id: 'm-card' }], TIP)).toEqual([{ method_id: 'm-card', extra: 120, extra_label: 'Tip' }]);
    expect(withAdded([{ method_id: 'm-cash', tendered: 5000 }], TIP)).toEqual([
      { method_id: 'm-cash', tendered: 5000, extra: 120, extra_label: 'Tip' },
    ]);
  });

  it('leaves the payments as they are when nothing is added, none is paid or the charge is split', () => {
    const one = [{ method_id: 'm-card' }];
    expect(withAdded(one, NOTHING_ADDED)).toBe(one);
    expect(withAdded([], TIP)).toEqual([]);
    const legs = [
      { method_id: 'm-card', amount: 100 },
      { method_id: 'm-cash', amount: 200 },
    ];
    expect(withAdded(legs, TIP)).toBe(legs);
  });
});

describe('stepBlock', () => {
  it('stops the charge with the words of a step that cannot be charged as it stands', () => {
    expect(stepBlock({ ...TIP, issue: 'Write a valid amount.' })).toEqual({ kind: 'step', message: 'Write a valid amount.' });
    expect(stepBlock(TIP)).toBeNull();
  });
});
