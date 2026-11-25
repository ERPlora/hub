// Figures in two columns, label over value: the session's summary in its detail and the figures of the close window.
import { describe, expect, it } from 'vitest';

import { mountCash, words } from '../__tests__/mount-cash-register';
import FigureList from './FigureList.vue';

const ITEMS = [
  { key: 'expected', label: 'Expected', value: '€100.00' },
  { key: 'tip-0', label: 'Tips in cash', value: '€5.00' },
];

describe('FigureList', () => {
  it('paints each figure in its order, label over value, each with its own hook', async () => {
    const m = await mountCash(FigureList, { props: { items: ITEMS, testid: 'figures' } });
    expect(m.find('figures').element.tagName).toBe('DL');
    expect(m.find('figures').findAll('dt').map((term) => term.text())).toEqual(['Expected', 'Tips in cash']);
    expect(words(m.find('figures-tip-0').element)).toBe('Tips in cash €5.00');
    expect(m.find('figures-expected').find('dd').text()).toBe('€100.00');
  });
});
