import { describe, expect, it } from 'vitest';

import { filledSeats, MAX_SEATS, seatSpots } from './floor-seats';

const shapes = ['square', 'round', 'rectangle'] as const;

describe('seatSpots', () => {
  it.each([1, 2, 3, 4, 6, 8])('draws a seat for each of %i places on every shape', (capacity) => {
    for (const shape of shapes) {
      const spots = seatSpots(capacity, shape, 1);
      expect(spots).toHaveLength(capacity);
      expect(new Set(spots.map((spot) => `${spot.x}:${spot.y}`)).size).toBe(capacity);
      for (const spot of spots) {
        expect(spot.x).toBeGreaterThanOrEqual(-12);
        expect(spot.x).toBeLessThanOrEqual(112);
        expect(spot.y).toBeGreaterThanOrEqual(-12);
        expect(spot.y).toBeLessThanOrEqual(112);
      }
    }
  });

  it('places four seats at the four sides of a square table', () => {
    expect(seatSpots(4, 'square', 1)).toEqual([
      { x: 50, y: -10, rotation: 0 },
      { x: 110, y: 50, rotation: 90 },
      { x: 50, y: 110, rotation: 0 },
      { x: -10, y: 50, rotation: 90 },
    ]);
  });

  it('distributes seats around a round table', () => {
    const spots = seatSpots(4, 'round', 1);
    expect(spots[0]).toMatchObject({ x: 50, y: -8 });
    expect(spots[1].x).toBeCloseTo(108);
    expect(spots[1].y).toBeCloseTo(50);
    expect(spots[2].y).toBeCloseTo(108);
    expect(spots[3].x).toBeCloseTo(-8);
  });

  it('uses the width-to-height ratio to spread rectangular seats', () => {
    const wide = seatSpots(8, 'rectangle', 1.8);
    const square = seatSpots(8, 'square', 1);
    expect(wide.filter((spot) => spot.y === -10 || spot.y === 110).length).toBeGreaterThan(
      square.filter((spot) => spot.y === -10 || spot.y === 110).length,
    );
  });

  it('caps large capacities at twelve seats and clamps invalid input', () => {
    expect(MAX_SEATS).toBe(12);
    expect(seatSpots(13, 'rectangle', 1)).toHaveLength(12);
    expect(seatSpots(100, 'round', 1)).toHaveLength(12);
    expect(seatSpots(0, 'square', 1)).toHaveLength(1);
    expect(seatSpots(4.8, 'square', 1)).toHaveLength(4);
  });
});

describe('filledSeats', () => {
  it('fills the seated guests, including more guests than capacity', () => {
    expect(filledSeats(4, 3)).toBe(3);
    expect(filledSeats(4, 8)).toBe(4);
    expect(filledSeats(4, null)).toBe(0);
  });

  it('fills a proportional share when capacity has more than twelve places', () => {
    expect(filledSeats(24, 6)).toBe(3);
    expect(filledSeats(24, 23)).toBe(12);
    expect(filledSeats(100, 1)).toBe(1);
  });
});
