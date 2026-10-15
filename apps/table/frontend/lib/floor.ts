// The floor plan's geometry and rules, apart from the screen (WORKBOOK «Plano de sala»).
// - Tables keep their real size: the plan is as large as its farthest table (it scrolls sideways on a
//   phone and grows down), and a dragged table never leaves it (tables#131 of the old module).
// - A status is never the colour alone (tables#64): colour, written word and an icon of its own.
// - A transfer picks a free or reserved table in service; a merge an occupied one (its own table only
//   when it holds another check: the two halves of a split join back).
import type { StatusPillTone } from '@erplora/ui/components';

import type { HoldShownOut, TableOut, TableStatus } from '../operations';

/** The side of a table box in plan pixels (`models.BOX`). */
export const BOX = 72;
/** What a tile paints past its box (border and padding): the plan holds the painted tile whole. */
export const TILE_CHROME = 10;
/** Below this many pixels of pointer travel a press is a tap (edit), above it a drag (move). */
export const DRAG_THRESHOLD = 5;
/** An arrow key moves a focused table this far; with Shift, four times as far (tables#16). */
export const KEY_STEP = 8;

export interface Size {
  w: number;
  h: number;
}

type Box = Pick<TableOut, 'position_x' | 'position_y' | 'width' | 'height'>;

/** The plan reaches the far edge of its farthest table and the bottom of its lowest one; while a
 *  table is dragged it never shrinks below `floor` (the plan would shrink under the finger). */
export function planeSize(tables: readonly Box[], floor?: Size): Size {
  let w = floor?.w ?? 0;
  let h = floor?.h ?? 0;
  for (const table of tables) {
    w = Math.max(w, table.position_x + table.width + TILE_CHROME);
    h = Math.max(h, table.position_y + table.height + TILE_CHROME);
  }
  return { w: Math.ceil(w), h: Math.ceil(h) };
}

/** A position inside `plane` for a table of `box`: it never leaves the plan, painted whole. */
export function clampPosition(x: number, y: number, box: Size, plane: Size): { x: number; y: number } {
  const maxX = Math.max(0, plane.w - box.w - TILE_CHROME);
  const maxY = Math.max(0, plane.h - box.h - TILE_CHROME);
  return { x: Math.round(Math.min(maxX, Math.max(0, x))), y: Math.round(Math.min(maxY, Math.max(0, y))) };
}

const ARROWS: Record<string, [number, number]> = {
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
};

/** How far an arrow key moves a focused table; `null` for any other key. */
export function keyDelta(key: string, shift: boolean): [number, number] | null {
  const direction = ARROWS[key];
  if (!direction) return null;
  const step = shift ? KEY_STEP * 4 : KEY_STEP;
  return [direction[0] * step, direction[1] * step];
}

export const STATUS_ICON: Readonly<Record<TableStatus, string>> = Object.freeze({
  available: 'ion:checkmark-circle-outline',
  occupied: 'ion:people-outline',
  reserved: 'ion:time-outline',
  blocked: 'ion:ban-outline',
});

export const STATUS_TONE: Readonly<Record<TableStatus, StatusPillTone>> = Object.freeze({
  available: 'success',
  occupied: 'danger',
  reserved: 'warning',
  blocked: 'neutral',
});

/** The theme colour of each status, painted on a tile's border and its written status. */
export const STATUS_COLOR: Readonly<Record<TableStatus, string>> = Object.freeze({
  available: 'var(--ion-color-success, #2f9e44)',
  occupied: 'var(--ion-color-danger, #d9480f)',
  reserved: 'var(--ion-color-warning, #f08c00)',
  blocked: 'var(--ion-color-medium, #868e96)',
});

/** Whose reservation a table paints: its name, or «Deleted customer» once her data was erased (F31). */
export function holdName(hold: HoldShownOut | null | undefined, erased: string): string {
  if (!hold) return '';
  return hold.label || (hold.erased ? erased : '');
}

export type PickMode = 'transfer' | 'merge';

/** Whether a transfer or a merge started at `source` may pick `table` as its destination. */
export function targetable(mode: PickMode, source: TableOut, table: TableOut): boolean {
  if (!table.in_service) return false;
  if (mode === 'transfer') return table.id !== source.id && (table.status === 'available' || table.status === 'reserved');
  if (table.status !== 'occupied') return false;
  return table.id !== source.id || table.checks.length > 1;
}

/** The status a table paints right now: the server's, except a reservation that entered its window
 *  (`leadMinutes` before it starts) or ended since the server read it — that happens with no event of
 *  anybody, so the plan repaints it by the clock (F25, F29). Occupied and blocked never change by time. */
export function paintedStatus(table: TableOut, now: Date, leadMinutes: number): TableStatus {
  if (table.status === 'occupied' || table.status === 'blocked' || !table.hold) return table.status;
  const from = Date.parse(table.hold.held_from) - leadMinutes * 60_000;
  const until = Date.parse(table.hold.held_until);
  const at = now.getTime();
  return from <= at && at < until ? 'reserved' : 'available';
}
