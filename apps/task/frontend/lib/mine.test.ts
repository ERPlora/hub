// «My tasks» lists only OPEN tasks, so the one just completed would vanish on the next result and the
// next card slide into its slot (tasks#45). It stays where it was, shown as done, until the person
// leaves the tab (Things, Apple Reminders, Asana): the fresh rows keep the server's order and each kept
// task goes back right after the card that preceded it. A kept task the server lists again is painted
// from the server, once.
import { describe, expect, it } from 'vitest';

import { keepCompletedInPlace } from './mine';

const row = (id: string, status = 'todo') => ({ id, status });

describe('keepCompletedInPlace', () => {
  it('keeps the completed card where it was', () => {
    const before = [row('a'), row('b'), row('c')];
    const kept = new Map([['b', row('b', 'done')]]);
    expect(keepCompletedInPlace(before, [row('a'), row('c')], kept)).toEqual([row('a'), row('b', 'done'), row('c')]);
  });

  it('keeps the first and the last card in their slots too', () => {
    const before = [row('a'), row('b'), row('c')];
    const kept = new Map([
      ['a', row('a', 'done')],
      ['c', row('c', 'done')],
    ]);
    expect(keepCompletedInPlace(before, [row('b')], kept)).toEqual([row('a', 'done'), row('b'), row('c', 'done')]);
  });

  it('keeps two neighbours completed one after the other in order', () => {
    const before = [row('a'), row('b'), row('c'), row('d')];
    const kept = new Map([
      ['b', row('b', 'done')],
      ['c', row('c', 'done')],
    ]);
    expect(keepCompletedInPlace(before, [row('a'), row('d')], kept).map((r) => r.id)).toEqual(['a', 'b', 'c', 'd']);
  });

  it('paints a reopened task from the server, once', () => {
    const before = [row('a'), row('b', 'done')];
    const kept = new Map([['b', row('b', 'done')]]);
    expect(keepCompletedInPlace(before, [row('a'), row('b', 'todo')], kept)).toEqual([row('a'), row('b', 'todo')]);
  });

  it('keeps nothing when nothing was completed', () => {
    expect(keepCompletedInPlace([row('a')], [row('b')], new Map())).toEqual([row('b')]);
  });
});
