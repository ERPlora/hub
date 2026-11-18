import type { FloorBox } from '@erplora/ui/components';

import type { Size } from './floor';
import type { TableOut } from '../operations';

const MIN_SPREAD = 1.7;
const MAX_SPREAD = 2.2;
const MAX_BOX = 1.3;
/** A table grows this much less than the gaps around it: a row keeps room for its labels under it. */
const BOX_GAP = 0.5;
const RECTANGLE_RATIO = 1.25;
const RECTANGLE_HEIGHT = 0.68;

export interface FloorFit {
  spread: number;
  box: number;
  plane: Size;
}

function rounded(value: number): number {
  return Math.round(value * 1000) / 1000;
}

export function fitPlan(content: Size, stage: Size): FloorFit {
  if (content.w <= 0 || content.h <= 0 || stage.w <= 0 || stage.h <= 0) {
    return { spread: 1, box: 1, plane: { ...content } };
  }
  const available = Math.min(stage.w / content.w, stage.h / content.h);
  const spread = Math.min(MAX_SPREAD, Math.max(MIN_SPREAD, available));
  const plane = { w: rounded(content.w * spread), h: rounded(content.h * spread) };
  return { spread, box: Math.min(MAX_BOX, spread - BOX_GAP), plane };
}

type Shaped = Pick<TableOut, 'shape' | 'width' | 'height'>;

/** A rectangle whose box is nearly square is painted flatter, so that it reads as a rectangle. */
function heightShare(table: Shaped): number {
  return table.shape === 'rectangle' && table.width / table.height < RECTANGLE_RATIO ? RECTANGLE_HEIGHT : 1;
}

export function paintedRatio(table: Shaped): number {
  return table.width / (table.height * heightShare(table));
}

/** Where a table is painted: its box spread over the plan, the table centred in it at its own scale. */
export function paintBox(table: TableOut, fit: FloorFit): FloorBox {
  const width = table.width * fit.box;
  const height = table.height * fit.box * heightShare(table);
  return {
    x: rounded(table.position_x * fit.spread + (table.width * fit.spread - width) / 2),
    y: rounded(table.position_y * fit.spread + (table.height * fit.spread - height) / 2),
    width: rounded(width),
    height: rounded(height),
    slot: rounded(table.width * fit.spread),
  };
}
