import type { TableShape } from '../operations';

export const MAX_SEATS = 12;

export interface SeatSpot {
  x: number;
  y: number;
  rotation: number;
}

function countFor(capacity: number): number {
  return Math.min(MAX_SEATS, Math.max(1, Math.floor(capacity)));
}

function roundSpots(count: number): SeatSpot[] {
  return Array.from({ length: count }, (_, index) => {
    const angle = -Math.PI / 2 + (index * Math.PI * 2) / count;
    return {
      x: Math.round((50 + Math.cos(angle) * 58) * 10) / 10,
      y: Math.round((50 + Math.sin(angle) * 58) * 10) / 10,
      rotation: Math.round((angle * 180) / Math.PI) + 90,
    };
  });
}

function sideSpots(side: number, count: number): SeatSpot[] {
  return Array.from({ length: count }, (_, index) => {
    const at = ((index + 1) / (count + 1)) * 100;
    if (side === 0) return { x: at, y: -10, rotation: 0 };
    if (side === 1) return { x: 110, y: at, rotation: 90 };
    if (side === 2) return { x: 100 - at, y: 110, rotation: 0 };
    return { x: -10, y: 100 - at, rotation: 90 };
  });
}

function sideCounts(count: number, ratio: number): number[] {
  const counts = [1, 1, 1, 1];
  const weights = [Math.max(0.1, ratio), 1, Math.max(0.1, ratio), 1];
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  for (let index = 0; index < count - 4; index += 1) {
    const desired = weights.map((weight) => (weight * count) / total);
    const next = desired
      .map((value, side) => ({ side, need: value - counts[side] }))
      .sort((a, b) => b.need - a.need)[0].side;
    counts[next] += 1;
  }
  return counts;
}

function angularSpots(count: number, ratio: number): SeatSpot[] {
  if (count < 4) {
    const four = sideCounts(4, ratio).flatMap((sideCount, side) => sideSpots(side, sideCount));
    if (count === 1) return [four[0]];
    if (count === 2) return [four[1], four[3]];
    return [four[0], four[1], four[3]];
  }
  return sideCounts(count, ratio).flatMap((sideCount, side) => sideSpots(side, sideCount));
}

export function seatSpots(capacity: number, shape: TableShape, ratio: number): SeatSpot[] {
  const count = countFor(capacity);
  return shape === 'round' ? roundSpots(count) : angularSpots(count, ratio);
}

export function filledSeats(capacity: number, guests: number | null): number {
  const seats = countFor(capacity);
  if (!guests || guests <= 0) return 0;
  const filled = Math.max(1, Math.round((guests / Math.max(1, capacity)) * seats));
  return Math.min(seats, filled);
}
