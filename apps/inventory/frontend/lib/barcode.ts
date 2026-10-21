// INVENTORY-F25: the SKU as a Code 128 (JsBarcode encodes it; its object renderer hands back the modules, so
// the bars are drawn by Vue and no SVG or HTML string reaches the page).
import JsBarcode from 'jsbarcode';

export interface Bar {
  /** Where the bar starts, in modules from the left edge of the code. */
  x: number;
  /** How many modules wide it is. */
  width: number;
}

export interface Barcode {
  /** The width of the whole code, in modules (without quiet zone). */
  modules: number;
  bars: Bar[];
}

/** The Code 128 of `text` as bars, or `null` when Code 128 cannot carry it (empty, or outside ASCII). */
export function code128(text: string): Barcode | null {
  const target: { encodings?: { data: string }[] } = {};
  let valid = true;
  try {
    JsBarcode(target, text, {
      format: 'CODE128',
      valid: (ok: boolean) => {
        valid = ok;
      },
    });
  } catch {
    return null;
  }
  if (!valid || !target.encodings) return null;
  const modules = target.encodings.map((encoding) => encoding.data).join('');
  const bars: Bar[] = [];
  for (let x = 0; x < modules.length; x += 1) {
    if (modules[x] !== '1') continue;
    const last = bars.at(-1);
    if (last && last.x + last.width === x) last.width += 1;
    else bars.push({ x, width: 1 });
  }
  return { modules: modules.length, bars };
}
