import { afterEach, describe, expect, it, vi } from 'vitest';

import { click, mountTable, settle } from '../__tests__/mount-table';
import { NOW, occupied, SETTINGS, tableRow } from '../__tests__/tables';
import type { TableOut } from '../operations';
import FloorCanvas from './FloorCanvas.vue';

const ONE = tableRow({ id: 't1', number: '1', position_x: 16, position_y: 16 });
const TWO = tableRow({ id: 't2', number: '2', position_x: 300, position_y: 200, width: 120 });

let observers: (() => void)[] = [];
class FakeObserver {
  constructor(callback: () => void) {
    observers.push(callback);
  }
  observe() {}
  disconnect() {}
}

afterEach(() => {
  vi.unstubAllGlobals();
  observers = [];
});

async function canvas(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountTable(FloorCanvas, {
    props: { tables: [ONE, TWO], now: NOW, timeZone: 'Europe/Madrid', settings: SETTINGS, editable: false, ...props },
    locale,
  });
  const tile = (id: string) => m.wrapper.find(`[data-testid="table-floor-tile-${id}"]`).element as HTMLElement;
  const plane = () => m.wrapper.find('[data-testid="table-floor-plane"]').element as HTMLElement;
  const stage = () => m.wrapper.find('[data-testid="table-floor-stage"]').element as HTMLElement;
  const pointer = async (el: Element, type: string, x: number, y: number, more: PointerEventInit = {}) => {
    el.dispatchEvent(new PointerEvent(type, { bubbles: true, clientX: x, clientY: y, pointerId: 1, ...more }));
    await settle();
  };
  const key = async (el: Element, keyName: string, shiftKey = false) => {
    el.dispatchEvent(new KeyboardEvent('keydown', { key: keyName, shiftKey, bubbles: true }));
    await settle();
  };
  /** Gives the stage a measured box, as the browser does once the page has its size; the plane, as edited, is
   *  as large as it is painted and never smaller than the stage. */
  const measure = async (w: number, h: number) => {
    Object.defineProperty(stage(), 'clientWidth', { configurable: true, value: w });
    Object.defineProperty(stage(), 'clientHeight', { configurable: true, value: h });
    Object.defineProperty(plane(), 'clientWidth', { configurable: true, get: () => Math.max(parseFloat(plane().style.width), w) });
    Object.defineProperty(plane(), 'clientHeight', { configurable: true, get: () => Math.max(parseFloat(plane().style.height), h) });
    for (const resized of observers) resized();
    await settle();
  };
  const drag = async (id: string, dx: number, dy: number) => {
    await pointer(tile(id), 'pointerdown', 400, 300);
    await pointer(tile(id), 'pointermove', 400 + dx, 300 + dy);
    await pointer(tile(id), 'pointerup', 400 + dx, 300 + dy);
  };
  /** A click that a pointer made (a keyboard's click, Enter or Space on a button, has `detail` 0). */
  const tap = async (el: Element) => {
    el.dispatchEvent(new MouseEvent('click', { bubbles: true, detail: 1 }));
    await settle();
  };
  const button = (id: string) => tile(id).querySelector('button')!;
  const selected = () => (m.wrapper.emitted('select') ?? []).map(([table]) => (table as TableOut).id);
  const moves = () => (m.wrapper.emitted('move') ?? []).map(([move]) => move as { table: TableOut; x: number; y: number });
  return { ...m, tile, button, plane, stage, pointer, key, measure, drag, click, tap, selected, moves };
}

/** The ten tables a new zone gets: five to a row, 88 px apart, 16 px from the edge. */
const ZONE = Array.from({ length: 10 }, (_, index) =>
  tableRow({ id: `z${index}`, number: String(index + 1), position_x: 16 + (index % 5) * 88, position_y: 16 + Math.floor(index / 5) * 88 }),
);
const ROW = Array.from({ length: 6 }, (_, index) => tableRow({ id: `r${index}`, number: String(index + 1), position_x: 16 + index * 88, position_y: 16 }));

describe('FloorCanvas', () => {
  it('lays every table at its box on a plan as large as the farthest one while the stage is unmeasured', async () => {
    const c = await canvas();
    expect([c.tile('t2').style.left, c.tile('t2').style.top]).toEqual(['300px', '200px']);
    expect([c.plane().style.width, c.plane().style.height]).toEqual([`${300 + 120 + 10}px`, `${200 + 72 + 10}px`]);
  });

  it('spreads the tables to fit a measured stage and grows each table less than the gaps between them', async () => {
    vi.stubGlobal('ResizeObserver', FakeObserver);
    const c = await canvas();
    await c.measure(1000, 700);
    expect([c.plane().style.width, c.plane().style.height]).toEqual(['946px', '620.4px']);
    expect([c.tile('t1').style.left, c.tile('t1').style.width]).toEqual(['67.6px', '93.6px']);
    expect(c.tile('t1').dataset.x).toBe('16');
  });

  it('paints each table in the app’s language, at its place on the plan and with the width its label may take', async () => {
    const c = await canvas({ tables: [ONE, occupied({ id: 't3', number: '3', position_x: 120 })] });
    expect(c.button('t1').getAttribute('aria-label')).toBe('Table 1 · Dining room · 4 pax · Available');
    expect(c.tile('t3').querySelector('[data-part="status"]')?.textContent?.trim()).toBe('Occupied · 3/4 pax');
    expect([c.tile('t3').dataset.x, c.tile('t3').dataset.y, c.tile('t3').dataset.timer]).toEqual(['120', '16', 'normal']);
    expect(c.tile('t1').style.getPropertyValue('--tile-slot')).toBe('72px');
    const es = await canvas({}, 'es');
    expect(es.button('t2').getAttribute('aria-label')).toBe('Mesa 2 · Dining room · 4 pax · Disponible');
  });

  it('greys out a table out of service only while the plan is edited, and lets every table be grabbed then', async () => {
    const idle = tableRow({ id: 't9', number: '9', is_active: false, in_service: false });
    const c = await canvas({ tables: [ONE, idle] });
    expect(c.tile('t9').querySelector('[data-part="inactive"]')).toBeNull();
    expect(c.tile('t1').classList.contains('table-tile--editing')).toBe(false);
    await c.wrapper.setProps({ editable: true });
    expect(c.tile('t9').querySelector('[data-part="inactive"]')?.textContent).toBe('Inactive');
    expect(c.tile('t9').classList.contains('table-tile--inactive')).toBe(true);
    expect(c.tile('t1').classList.contains('table-tile--inactive')).toBe(false);
    expect(c.tile('t1').classList.contains('table-tile--editing')).toBe(true);
  });

  it('is a focusable region named for the arrows, with a grid only while the plan is edited', async () => {
    const c = await canvas();
    expect([c.stage().getAttribute('role'), c.stage().getAttribute('tabindex')]).toEqual(['region', '0']);
    expect(c.stage().getAttribute('aria-label')).toBe('Floor plan. Use the arrow keys to scroll it.');
    expect(c.plane().classList.contains('table-canvas__plane--grid')).toBe(false);
    await c.wrapper.setProps({ editable: true });
    expect(c.plane().classList.contains('table-canvas__plane--grid')).toBe(true);
    const es = await canvas({}, 'es');
    expect(es.stage().getAttribute('aria-label')).toBe('Plano de mesas. Usa las flechas para desplazarlo.');
  });

  it('fades each edge with tables behind it', async () => {
    const c = await canvas();
    const box = c.stage();
    Object.defineProperty(box, 'clientWidth', { configurable: true, value: 300 });
    Object.defineProperty(box, 'scrollWidth', { configurable: true, value: 700 });
    Object.defineProperty(box, 'clientHeight', { configurable: true, value: 200 });
    Object.defineProperty(box, 'scrollHeight', { configurable: true, value: 500 });
    Object.defineProperty(box, 'scrollTop', { configurable: true, writable: true, value: 100 });
    box.dispatchEvent(new Event('scroll'));
    await settle();
    const root = c.wrapper.find('[data-testid="table-floor-canvas"]').classes();
    expect(root).toEqual(expect.arrayContaining(['table-canvas--more-right', 'table-canvas--more-top', 'table-canvas--more-bottom']));
    expect(root).not.toContain('table-canvas--more-left');
    expect(c.wrapper.findAll('.table-canvas__fade')).toHaveLength(4);
  });

  it('in Service a tap or the keyboard picks a table once, and nothing is dragged', async () => {
    const c = await canvas();
    await c.pointer(c.tile('t1'), 'pointerdown', 20, 20);
    await c.pointer(c.tile('t1'), 'pointermove', 120, 120);
    await c.pointer(c.tile('t1'), 'pointerup', 120, 120);
    expect(c.selected()).toEqual([]);
    await c.tap(c.button('t1'));
    // Enter on a focused table is its button's own click: the key itself picks nothing more.
    await c.key(c.button('t2'), 'Enter');
    await c.click(c.button('t2'));
    await c.key(c.button('t2'), 'ArrowRight');
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

  it('a drag on a spread plan moves the table by the screen distance over the spread, and one drag goes a cell past the farthest table at most', async () => {
    vi.stubGlobal('ResizeObserver', FakeObserver);
    const c = await canvas({ editable: true });
    await c.measure(1000, 700);
    const left = c.tile('t2').style.left;
    await c.pointer(c.tile('t1'), 'pointerdown', 100, 100);
    await c.pointer(c.tile('t1'), 'pointermove', 300, 144);
    expect(c.tile('t2').style.left).toBe(left);
    await c.pointer(c.tile('t1'), 'pointerup', 300, 144);
    // The 700 px of the stage hold the plan and a cell of room below it: 282 + 88 plan units. The plan grows
    // while the table goes into its room, but that drag goes no farther.
    await c.pointer(c.tile('t1'), 'pointerdown', 100, 100);
    await c.pointer(c.tile('t1'), 'pointermove', 2100, 100);
    await c.pointer(c.tile('t1'), 'pointermove', 2500, 100);
    await c.pointer(c.tile('t1'), 'pointerup', 2500, 100);
    await c.drag('t1', 2000, 0);
    expect(c.moves().map((m) => [m.x, m.y])).toEqual([
      [122, 39],
      [447, 39],
      [535, 39],
    ]);
    expect(c.tile('t2').style.left).toBe(left);
    expect(parseFloat(c.plane().style.width)).toBeGreaterThan(1000);
  });

  it('in Edit plan the farthest column is dragged past itself, into the room the plan keeps on the right', async () => {
    vi.stubGlobal('ResizeObserver', FakeObserver);
    const c = await canvas({ editable: true, tables: ZONE });
    await c.measure(770, 700);
    await c.drag('z4', 100, 0);
    expect(c.moves().map((m) => [m.table.id, m.x, m.y])).toEqual([['z4', 427, 16]]);
  });

  it('in Edit plan the right arrow moves the farthest column past itself too', async () => {
    vi.stubGlobal('ResizeObserver', FakeObserver);
    const c = await canvas({ editable: true, tables: ZONE });
    await c.measure(770, 700);
    await c.key(c.tile('z4'), 'ArrowRight');
    expect(c.moves().map((m) => [m.table.id, m.x, m.y])).toEqual([['z4', 376, 16]]);
  });

  it('in Edit plan the lowest row goes below itself on a stage the plan fills from top to bottom', async () => {
    vi.stubGlobal('ResizeObserver', FakeObserver);
    const c = await canvas({ editable: true, tables: ZONE });
    await c.measure(1000, 320);
    await c.drag('z9', 0, 100);
    await c.key(c.tile('z5'), 'ArrowDown');
    expect(c.moves().map((m) => [m.table.id, m.x, m.y])).toEqual([
      ['z9', 368, 163],
      ['z5', 16, 112],
    ]);
  });

  it('in Edit plan a drop keeps the scale: the farthest table dropped inward stays under the pointer and the others do not move', async () => {
    vi.stubGlobal('ResizeObserver', FakeObserver);
    const c = await canvas({ editable: true, tables: ROW });
    await c.measure(1000, 700);
    const others = () => ['r0', 'r4'].map((id) => [c.tile(id).style.left, c.tile(id).style.top]);
    const before = others();
    const from = parseFloat(c.tile('r5').style.left);
    await c.drag('r5', -300, 0);
    expect(others()).toEqual(before);
    expect(Math.abs(parseFloat(c.tile('r5').style.left) - (from - 300))).toBeLessThan(1);
    expect(c.moves().map((m) => [m.x, m.y])).toEqual([[280, 16]]);
  });

  it('in Edit plan the plan fits again for other tables (another zone, one added or removed) or the other mode, never for a move', async () => {
    vi.stubGlobal('ResizeObserver', FakeObserver);
    const c = await canvas({ editable: true, tables: ROW });
    await c.measure(1000, 700);
    const width = () => c.plane().style.width;
    expect(width()).toBe('1064.2px');
    await c.wrapper.setProps({ tables: [...ROW.slice(0, 5), { ...ROW[5], position_x: 280 }] });
    expect(width()).toBe('914.6px');
    await c.wrapper.setProps({ tables: ROW.slice(0, 5) });
    expect(width()).toBe('1000px');
    await c.wrapper.setProps({ tables: ROW });
    expect(width()).toBe('1064.2px');
    await c.wrapper.setProps({ editable: false });
    expect(width()).toBe('1000px');
  });

  it('a press that does not travel is a tap, even in Edit plan (and its click is not a second one)', async () => {
    const c = await canvas({ editable: true });
    await c.pointer(c.tile('t2'), 'pointerdown', 310, 210);
    await c.pointer(c.tile('t2'), 'pointermove', 312, 211);
    await c.pointer(c.tile('t2'), 'pointerup', 312, 211);
    await c.tap(c.button('t2'));
    expect(c.selected()).toEqual(['t2']);
    expect(c.moves()).toEqual([]);
  });

  it('in Edit plan Enter or Space on a focused table opens it too', async () => {
    const c = await canvas({ editable: true });
    await c.click(c.button('t1'));
    expect(c.selected()).toEqual(['t1']);
  });

  it('a table never leaves the plan', async () => {
    const c = await canvas({ editable: true });
    await c.pointer(c.tile('t1'), 'pointerdown', 20, 20);
    await c.pointer(c.tile('t1'), 'pointermove', -500, -500);
    await c.pointer(c.tile('t1'), 'pointerup', -500, -500);
    expect(c.moves().map((m) => [m.x, m.y])).toEqual([[0, 0]]);
  });

  it('the arrows move a focused table 8 px, 32 with Shift, and do not scroll the stage', async () => {
    const c = await canvas({ editable: true });
    await c.key(c.tile('t2'), 'ArrowLeft');
    await c.key(c.tile('t2'), 'ArrowUp', true);
    expect(c.moves().map((m) => [m.table.id, m.x, m.y])).toEqual([
      ['t2', 292, 200],
      ['t2', 292, 168],
    ]);
    expect([c.stage().scrollLeft, c.stage().scrollTop]).toEqual([0, 0]);
  });

  it('the arrows scroll the focused stage, and a mouse drags its background', async () => {
    const c = await canvas();
    await c.key(c.stage(), 'ArrowRight');
    expect(c.stage().scrollLeft).toBe(48);
    await c.pointer(c.plane(), 'pointerdown', 200, 200, { pointerType: 'mouse', button: 0 });
    await c.pointer(c.stage(), 'pointermove', 180, 170, { pointerType: 'mouse' });
    await c.pointer(c.stage(), 'pointerup', 180, 170, { pointerType: 'mouse' });
    expect([c.stage().scrollLeft, c.stage().scrollTop]).toEqual([68, 30]);
    expect(c.selected()).toEqual([]);
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
    expect(c.button('t3').getAttribute('aria-disabled')).toBe('true');
    await c.tap(c.button('t3'));
    await c.click(c.button('t3'));
    await c.tap(c.button('t1'));
    expect(c.selected()).toEqual(['t1']);
  });
});
