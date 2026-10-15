// The plan of a zone (WORKBOOK «Plano de sala»; TABLE-F03, F09): the tables at their real size on a plan
// as large as the farthest one. In «Service» a tap (or Enter) picks a table; in «Edit plan» a table is
// dragged to its place — the gesture is the table's: a press that does not travel is a tap — or moved
// with the arrows (8 px, 32 with Shift), and it never leaves the plan. The new place shows at once and
// stays until the server has it; a refused move goes back.
import { describe, expect, it } from 'vitest';

import { click, mountTable, settle } from '../__tests__/mount-table';
import { NOW, occupied, tableRow } from '../__tests__/tables';
import type { TableOut } from '../operations';
import FloorCanvas from './FloorCanvas.vue';

const ONE = tableRow({ id: 't1', number: '1', position_x: 16, position_y: 16 });
const TWO = tableRow({ id: 't2', number: '2', position_x: 300, position_y: 200, width: 120 });

async function canvas(props: Record<string, unknown> = {}) {
  const m = await mountTable(FloorCanvas, {
    props: { tables: [ONE, TWO], now: NOW, timeZone: 'Europe/Madrid', editable: false, ...props },
  });
  const tile = (id: string) => m.wrapper.find(`[data-testid="table-floor-tile-${id}"]`).element as HTMLElement;
  const plane = () => m.wrapper.find('[data-testid="table-floor-plane"]').element as HTMLElement;
  const pointer = async (el: Element, type: string, x: number, y: number) => {
    el.dispatchEvent(new PointerEvent(type, { bubbles: true, clientX: x, clientY: y, pointerId: 1 }));
    await settle();
  };
  const key = async (el: Element, keyName: string, shiftKey = false) => {
    el.dispatchEvent(new KeyboardEvent('keydown', { key: keyName, shiftKey, bubbles: true }));
    await settle();
  };
  const selected = () => (m.wrapper.emitted('select') ?? []).map(([table]) => (table as TableOut).id);
  const moves = () => (m.wrapper.emitted('move') ?? []).map(([move]) => move as { table: TableOut; x: number; y: number });
  return { ...m, tile, plane, pointer, key, click, selected, moves };
}

describe('FloorCanvas', () => {
  it('lays every table at its box on a plan as large as the farthest one', async () => {
    const c = await canvas();
    expect([c.tile('t2').style.left, c.tile('t2').style.top]).toEqual(['300px', '200px']);
    expect([c.plane().style.width, c.plane().style.height]).toEqual([`${300 + 120 + 10}px`, `${200 + 72 + 10}px`]);
  });

  it('in Service a tap or Enter picks a table, and nothing is dragged', async () => {
    const c = await canvas();
    await c.pointer(c.tile('t1'), 'pointerdown', 20, 20);
    await c.pointer(c.tile('t1'), 'pointermove', 120, 120);
    await c.pointer(c.tile('t1'), 'pointerup', 120, 120);
    expect(c.selected()).toEqual([]);
    await c.click(c.tile('t1'));
    await c.key(c.tile('t2'), 'Enter');
    await c.key(c.tile('t2'), 'ArrowRight');
    expect(c.selected()).toEqual(['t1', 't2']);
    expect(c.moves()).toEqual([]);
    expect(c.tile('t1').style.left).toBe('16px');
  });

  it('in Edit plan a table is dragged to its place, shows there at once and says so', async () => {
    const c = await canvas({ editable: true });
    await c.pointer(c.tile('t1'), 'pointerdown', 20, 20);
    await c.pointer(c.tile('t1'), 'pointermove', 70, 60);
    expect(c.tile('t1').classList.contains('table-tile--dragging')).toBe(true);
    await c.pointer(c.tile('t1'), 'pointerup', 70, 60);
    expect(c.moves().map((m) => [m.table.id, m.x, m.y])).toEqual([['t1', 66, 56]]);
    expect([c.tile('t1').style.left, c.tile('t1').style.top]).toEqual(['66px', '56px']);
    expect(c.selected()).toEqual([]);
  });

  it('a press that does not travel is a tap, even in Edit plan (and its click is not a second one)', async () => {
    const c = await canvas({ editable: true });
    await c.pointer(c.tile('t2'), 'pointerdown', 310, 210);
    await c.pointer(c.tile('t2'), 'pointermove', 312, 211);
    await c.pointer(c.tile('t2'), 'pointerup', 312, 211);
    await c.click(c.tile('t2'));
    expect(c.selected()).toEqual(['t2']);
    expect(c.moves()).toEqual([]);
  });

  it('a table never leaves the plan', async () => {
    const c = await canvas({ editable: true });
    await c.pointer(c.tile('t1'), 'pointerdown', 20, 20);
    await c.pointer(c.tile('t1'), 'pointermove', -500, -500);
    await c.pointer(c.tile('t1'), 'pointerup', -500, -500);
    expect(c.moves().map((m) => [m.x, m.y])).toEqual([[0, 0]]);
  });

  it('the arrows move a focused table 8 px, 32 with Shift', async () => {
    const c = await canvas({ editable: true });
    await c.key(c.tile('t2'), 'ArrowLeft');
    await c.key(c.tile('t2'), 'ArrowUp', true);
    expect(c.moves().map((m) => [m.table.id, m.x, m.y])).toEqual([
      ['t2', 292, 200],
      ['t2', 292, 168],
    ]);
  });

  it('keeps the new place until the server has it, and a refused move goes back', async () => {
    const c = await canvas({ editable: true });
    await c.key(c.tile('t1'), 'ArrowRight');
    expect(c.tile('t1').style.left).toBe('24px');
    (c.wrapper.vm as unknown as { revert(id: string): void }).revert('t1');
    await settle();
    expect(c.tile('t1').style.left).toBe('16px');
    await c.key(c.tile('t1'), 'ArrowRight');
    await c.wrapper.setProps({ tables: [{ ...ONE, position_x: 24 }, TWO] });
    expect(c.tile('t1').style.left).toBe('24px');
  });

  it('while picking a destination only the tables that may be picked answer', async () => {
    const c = await canvas({ pick: (table: TableOut) => table.status === 'available', tables: [ONE, occupied({ id: 't3', number: '3' })] });
    expect(c.tile('t3').getAttribute('aria-disabled')).toBe('true');
    await c.click(c.tile('t3'));
    await c.key(c.tile('t3'), 'Enter');
    await c.click(c.tile('t1'));
    expect(c.selected()).toEqual(['t1']);
  });
});
