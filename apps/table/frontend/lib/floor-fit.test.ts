import { describe, expect, it } from 'vitest';

import { tableRow } from '../__tests__/tables';
import { fitPlan, paintBox, paintedRatio } from './floor-fit';

const CONTENT = { w: 450, h: 186 };

describe('fitPlan', () => {
  it('uses one at a zero-sized stage so an unhydrated screen remains measurable', () => {
    expect(fitPlan(CONTENT, { w: 0, h: 0 })).toEqual({ spread: 1, box: 1, plane: CONTENT });
  });

  it('spreads positions to fit the stage and caps table growth at 1.3', () => {
    const fit = fitPlan(CONTENT, { w: 1100, h: 600 });
    expect(fit.spread).toBe(2.2);
    expect(fit.box).toBe(1.3);
    expect(fit.plane).toEqual({ w: 990, h: 409.2 });
  });

  it('keeps a legible minimum spread and lets a smaller stage scroll', () => {
    const fit = fitPlan(CONTENT, { w: 300, h: 150 });
    expect(fit.spread).toBe(1.7);
    expect(fit.plane.w).toBe(765);
    expect(fit.plane.h).toBe(316.2);
  });

  it('shrinks the tables with a tight spread, so a row keeps room for its labels before the seats of the next', () => {
    expect(fitPlan(CONTENT, { w: 1100, h: 600 }).box).toBe(1.3);
    expect(fitPlan(CONTENT, { w: 810, h: 600 }).box).toBe(1.3);
    expect(fitPlan(CONTENT, { w: 770, h: 600 }).box).toBeCloseTo(1.211);
    expect(fitPlan(CONTENT, { w: 300, h: 150 }).box).toBeCloseTo(1.2);
  });

  it('fits the default ten-table zone of a portrait tablet without scrolling', () => {
    const fit = fitPlan(CONTENT, { w: 770, h: 700 });
    expect(fit.plane.w).toBeLessThanOrEqual(770);
  });

  it('keeps an empty plan at one', () => {
    expect(fitPlan({ w: 0, h: 0 }, { w: 800, h: 600 })).toEqual({ spread: 1, box: 1, plane: { w: 0, h: 0 } });
  });
});

describe('paintBox', () => {
  const fit = { spread: 2, box: 1.3, plane: { w: 900, h: 500 } };

  it('scales positions by spread and centres the smaller table box', () => {
    expect(paintBox(tableRow({ position_x: 100, position_y: 50, width: 72, height: 72 }), fit)).toEqual({
      x: 225.2,
      y: 125.2,
      width: 93.6,
      height: 93.6,
    });
  });

  it('paints a nearly square rectangle at 68 percent height, centred in its box', () => {
    const painted = paintBox(tableRow({ shape: 'rectangle', position_x: 0, position_y: 0, width: 72, height: 72 }), fit);
    expect(painted.width).toBe(93.6);
    expect(painted.height).toBeCloseTo(63.648);
    expect(painted.x).toBe(25.2);
    expect(painted.y).toBeCloseTo(40.176);
  });

  it('leaves a genuinely wide rectangle at its full height', () => {
    const painted = paintBox(tableRow({ shape: 'rectangle', width: 144, height: 72 }), fit);
    expect(painted.height).toBe(93.6);
  });

  it('keeps the default ten-table grid clear of tables, seats and labels', () => {
    const fit = fitPlan(CONTENT, { w: 700, h: 500 });
    const boxes = Array.from({ length: 10 }, (_, index) =>
      paintBox(tableRow({ position_x: 16 + (index % 5) * 88, position_y: 16 + Math.floor(index / 5) * 88 }), fit),
    );
    const envelopes = boxes.map((box) => ({
      left: box.x - 14,
      right: box.x + box.width + 14,
      top: box.y - 14,
      bottom: box.y + box.height + 48,
    }));
    for (const [index, a] of envelopes.entries()) {
      for (const b of envelopes.slice(index + 1)) {
        const overlaps = a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
        expect(overlaps).toBe(false);
      }
    }
  });
});

describe('paintedRatio', () => {
  it('is the width over the height of the table as painted, for its seats to go round it', () => {
    expect(paintedRatio(tableRow())).toBe(1);
    expect(paintedRatio(tableRow({ shape: 'rectangle' }))).toBeCloseTo(1 / 0.68);
    expect(paintedRatio(tableRow({ shape: 'rectangle', width: 144, height: 72 }))).toBe(2);
  });
});
