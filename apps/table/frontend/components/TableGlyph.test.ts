import { describe, expect, it } from 'vitest';

import { mountTable } from '../__tests__/mount-table';
import { occupied, tableRow } from '../__tests__/tables';
import TableGlyph from './TableGlyph.vue';

async function glyph(props: Record<string, unknown> = {}) {
  const m = await mountTable(TableGlyph, { props: { table: tableRow(), tone: 'normal', progress: 0, ...props } });
  return { ...m, el: m.wrapper.element as HTMLElement, seats: () => m.wrapper.findAll('[data-part="seat"]') };
}

describe('TableGlyph', () => {
  it('is decorative and draws seats for the table capacity', async () => {
    const g = await glyph();
    expect(g.el.getAttribute('aria-hidden')).toBe('true');
    expect(g.seats()).toHaveLength(4);
    expect(g.seats().some((seat) => seat.classes().includes('table-glyph__seat--filled'))).toBe(false);
    expect(g.wrapper.find('.table-glyph__arc').exists()).toBe(false);
  });

  it('fills seats from seated guests, proportionally above twelve places', async () => {
    const small = await glyph({ table: occupied() });
    expect(small.seats().filter((seat) => seat.classes().includes('table-glyph__seat--filled'))).toHaveLength(3);
    const large = await glyph({ table: occupied({ capacity: 24, guests: 6 }) });
    expect(large.seats()).toHaveLength(12);
    expect(large.seats().filter((seat) => seat.classes().includes('table-glyph__seat--filled'))).toHaveLength(3);
  });

  it('draws a circular arc for a round occupied table', async () => {
    const g = await glyph({ table: occupied({ shape: 'round' }), tone: 'warning', progress: 68 });
    const arc = g.wrapper.find('.table-glyph__arc');
    expect(arc.attributes('data-tone')).toBe('warning');
    expect(arc.find('circle.table-glyph__arc-value').attributes('stroke-dasharray')).toBe('68 32');
    expect(arc.find('circle.table-glyph__arc-value').attributes('pathLength')).toBe('100');
    expect(arc.find('circle.table-glyph__arc-value').attributes('vector-effect')).toBe('non-scaling-stroke');
  });

  it('draws a rectangular arc and supports the miniature variant', async () => {
    const g = await glyph({ table: occupied({ shape: 'rectangle' }), variant: 'mini', progress: 25 });
    expect(g.el.classList.contains('table-glyph--mini')).toBe(true);
    expect(g.wrapper.find('rect.table-glyph__arc-value').attributes('stroke-dasharray')).toBe('25 75');
    expect(g.wrapper.find('rect.table-glyph__arc-value').attributes('vector-effect')).toBe('non-scaling-stroke');
  });
});
