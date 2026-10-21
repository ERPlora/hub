// INVENTORY-F25: the SKU as a Code 128, as bars a scanner reads (the plate of the product sheet and the
// label printed from the browser). The encoding is JsBarcode's; this module only turns its modules into bars.
import { describe, expect, it } from 'vitest';

import { code128 } from './barcode';

describe('code128', () => {
  it('turns each run of black modules into one bar, with the quiet zone left to the caller', () => {
    // «A»: start B, «A», checksum and stop (46 modules).
    const a = code128('A');
    expect(a?.modules).toBe(46);
    expect(a?.bars.slice(0, 3)).toEqual([
      { x: 0, width: 2 },
      { x: 3, width: 1 },
      { x: 6, width: 1 },
    ]);
    // The stop pattern ends in two black modules at the very end.
    expect(a?.bars.at(-1)).toEqual({ x: 44, width: 2 });
  });

  it('reads a SKU with letters, digits and a hyphen', () => {
    const sku = code128('SHA-250');
    expect(sku?.modules).toBe(112);
    const black = sku!.bars.reduce((sum, bar) => sum + bar.width, 0);
    // Code 128 is half black: every symbol of 11 modules has 3 bars and 3 spaces.
    expect(black).toBeGreaterThan(40);
    expect(black).toBeLessThan(70);
  });

  it('is null for what Code 128 cannot carry, never a wrong code', () => {
    expect(code128('')).toBeNull();
    expect(code128('Ñandú')).toBeNull();
  });
});
