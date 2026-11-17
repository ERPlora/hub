import type { Size } from './floor';
import type { TableOut } from '../operations';

const MIN_SPREAD = 1.8;
const MAX_SPREAD = 2.2;
const MAX_BOX = 1.3;
const RECTANGLE_RATIO = 1.25;
const RECTANGLE_HEIGHT = 0.68;

export interface FloorFit {
  spread: number;
  box: number;
  plane: Size;
}

export interface PaintedBox {
  x: number;
  y: number;
  width: number;
  height: number;
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
  return { spread, box: Math.min(MAX_BOX, spread), plane };
}

export function paintBox(table: TableOut, fit: FloorFit): PaintedBox {
  const width = table.width * fit.box;
  const narrow = table.shape === 'rectangle' && table.width / table.height < RECTANGLE_RATIO;
  const height = table.height * fit.box * (narrow ? RECTANGLE_HEIGHT : 1);
  return {
    x: rounded(table.position_x * fit.spread + (table.width * fit.spread - width) / 2),
    y: rounded(table.position_y * fit.spread + (table.height * fit.spread - height) / 2),
    width: rounded(width),
    height: rounded(height),
  };
}
