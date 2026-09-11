/**
 * hub#1733 — a settings row must not let its VALUE strangle its LABEL.
 *
 * An `ion-item` lays its slots out in the shadow DOM, and the box that holds the label is sized by
 * what is LEFT once the `slot="end"` control has taken its natural width. A long value therefore
 * eats the row: on `banco-pre` at 390px the «Zona horaria» value («Automática · Europe/Madrid,
 * 23:01», 182px) left the label 70px, so its 12 characters stacked into a 125px-tall column while
 * the «País» row right above it read normally.
 *
 * The only lever that changes that split is a CAP on the value: a floor on `ion-label` is an
 * ILLUSION — the label is not the flex item, so `min-width` there only makes the label paint OVER
 * the select (measured: label 89→249, select 159→341, a 90px overlap).
 *
 * The numbers below were measured in the browser on `banco-pre`, `/settings` (tab «General»), on
 * 2026-09-10. They are what makes this guard real rather than decorative: the same formula has to
 * reproduce the BROKEN widths with no cap and the FIXED widths with the cap that lives in
 * `polish.css`.
 */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const polishCss = (): string => readFileSync(new URL('./polish.css', import.meta.url), 'utf8');

/** One row as the browser measured it: the box it lays out in and what its value wants to take. */
type BenchRow = {
  /** The `h2` of the row, as a person reads it. */
  row: string;
  /** Space the item gives to label + value together, in px. */
  contentBox: number;
  /** Natural (max-content) width of the `slot="end"` control, in px. */
  valueWants: number;
  /** Width the `h2` needs to sit on ONE line, in px. */
  labelOneLine: number;
  /** The element sitting in `slot="end"` — it decides whether the rule reaches this row at all. */
  endTag: string;
};

/** `/settings` → «General» at 390x844 (the viewport the issue reports). */
const BENCH_390: BenchRow[] = [
  { row: 'País', contentBox: 252, valueWants: 75, labelOneLine: 29, endTag: 'ion-select' },
  { row: 'Zona horaria', contentBox: 252, valueWants: 182, labelOneLine: 89, endTag: 'ion-select' },
  { row: 'Moneda', contentBox: 252, valueWants: 99, labelOneLine: 57, endTag: 'ion-select' },
  { row: 'Idioma del negocio', contentBox: 252, valueWants: 79, labelOneLine: 132, endTag: 'ion-select' },
  {
    row: 'Acceso a recursos locales y de red',
    contentBox: 232,
    valueWants: 177,
    labelOneLine: 243,
    endTag: 'ion-note',
  },
];

/**
 * The same «Zona horaria» row on the wider viewports, where it already read fine. 600 and 768 are
 * the first two real devices past the width where `50vw - 6rem` clears the whole value (556px): a
 * small Android tablet and an iPad in portrait. They are here because a cap that scales too slowly
 * (`40vw` was tried as a mutant) leaves tablet and desktop alone yet still truncates the value on
 * exactly those two — and only a viewport between 556 and 695 can tell.
 */
const TIMEZONE_ON_WIDE = [
  { viewport: 600, contentBox: 462, valueWants: 182 },
  { viewport: 768, contentBox: 630, valueWants: 182 },
  { viewport: 952, contentBox: 814, valueWants: 182 },
  { viewport: 1440, contentBox: 1062, valueWants: 182 },
];

const ROOT_FONT_PX = 16;

/**
 * The cap as it is DECLARED in `polish.css` — read, never remembered, so moving the numbers in the
 * stylesheet moves this guard with them.
 */
const readValueCap = (): { selectors: string[]; declaration: string } => {
  // Comments carry no braces, so they would otherwise be swallowed into the selector list.
  const css = polishCss().replace(/\/\*[\s\S]*?\*\//g, '');
  const rule = /([^{}]*\[slot="end"\][^{}]*)\{([^}]*max-width[^}]*)\}/.exec(css);
  if (!rule) throw new Error('no rule caps the value of a settings row in polish.css');
  const declaration = /max-width:\s*([^;]+);/.exec(rule[2]);
  if (!declaration) throw new Error('the settings-row rule declares no max-width');
  return {
    selectors: rule[1]
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
    declaration: declaration[1].trim(),
  };
};

/**
 * Resolves `max(<n>rem, calc(<n>vw - <n>rem))` for a viewport. Deliberately narrow: it parses the
 * shape the stylesheet actually declares, so a cap written some other way fails loudly here instead
 * of being silently approximated.
 */
const capAt = (viewportPx: number): number => {
  const { declaration } = readValueCap();
  const parts = /^max\(\s*([\d.]+)rem\s*,\s*calc\(\s*([\d.]+)vw\s*-\s*([\d.]+)rem\s*\)\s*\)$/.exec(
    declaration,
  );
  if (!parts) throw new Error(`unsupported cap shape: ${declaration}`);
  const [, floorRem, vw, gutterRem] = parts;
  return Math.max(
    Number(floorRem) * ROOT_FONT_PX,
    (Number(vw) / 100) * viewportPx - Number(gutterRem) * ROOT_FONT_PX,
  );
};

/** The cap only reaches a row whose end slot the stylesheet actually names. */
const capForRow = (endTag: string, viewportPx: number): number =>
  readValueCap().selectors.some((s) => s.includes(`${endTag}[slot="end"]`))
    ? capAt(viewportPx)
    : Number.POSITIVE_INFINITY;

/** What the label is left with once the value has taken what it is allowed to take. */
const labelWidth = (row: { contentBox: number; valueWants: number }, cap: number): number =>
  row.contentBox - Math.min(row.valueWants, cap);

const timezone390 = BENCH_390.find((r) => r.row === 'Zona horaria')!;

describe('a settings row shares its width between label and value', () => {
  it('hub#1733: the cap is read from polish.css, not remembered', () => {
    const { selectors, declaration } = readValueCap();
    expect(selectors.length).toBeGreaterThan(0);
    expect(declaration).not.toBe('');
    // The shape has to be resolvable, or every measurement below would be a guess.
    expect(capAt(390)).toBeGreaterThan(0);
  });

  it('hub#1733: the model reproduces BOTH widths the browser measured on the bench', () => {
    // Without a cap this is the bug the issue reports, to the pixel.
    expect(labelWidth(timezone390, Number.POSITIVE_INFINITY)).toBe(70);
    // With the cap that ships, this is what the browser showed after the fix.
    expect(labelWidth(timezone390, capAt(390))).toBe(140);
  });

  it('hub#1733: no value takes more room than the label it belongs to', () => {
    for (const row of BENCH_390) {
      const cap = capForRow(row.endTag, 390);
      const label = labelWidth(row, cap);
      const value = Math.min(row.valueWants, cap);
      expect(label, `«${row.row}»: label ${label}px vs value ${value}px`).toBeGreaterThanOrEqual(
        value,
      );
    }
  });

  it('hub#1733: «Zona horaria» fits on one line at 390, like «País» right above it', () => {
    expect(labelWidth(timezone390, capForRow(timezone390.endTag, 390))).toBeGreaterThanOrEqual(
      timezone390.labelOneLine,
    );
  });

  it('hub#1733: the cap stays INERT on the rows and viewports that already read fine', () => {
    // At 390 the healthy rows never reach the cap, so nothing about them changes.
    for (const row of BENCH_390.filter((r) => r.valueWants <= 100)) {
      expect(Math.min(row.valueWants, capAt(390)), `«${row.row}» must not be capped`).toBe(
        row.valueWants,
      );
    }
    // On tablet and desktop the row is wide, so the full value keeps showing — capping there would
    // truncate «Automática · Europe/Madrid, 23:01» for no reason.
    for (const { viewport, valueWants } of TIMEZONE_ON_WIDE) {
      expect(Math.min(valueWants, capAt(viewport)), `capped at ${viewport}px`).toBe(valueWants);
    }
  });

  it('hub#1733: the cap covers only values that can truncate, never a control', () => {
    const { selectors } = readValueCap();
    // A blanket `[slot="end"]` cap was measured on the bench and REGRESSED the «Dígitos del PIN»
    // row: its `ion-segment` went 288px → 112px and its own content overflowed (scrollWidth >
    // clientWidth). A select and a note truncate or wrap; a segment cannot.
    for (const selector of selectors) {
      expect(selector, `«${selector}» caps every end slot, segments included`).toMatch(
        /ion-(select|note)\[slot="end"\]/,
      );
    }
  });

  it('hub#1733: the detector catches the positive — an unbounded value strangles the row', () => {
    const noCap = Number.POSITIVE_INFINITY;
    const label = labelWidth(timezone390, noCap);
    expect(label).toBeLessThan(timezone390.valueWants);
    expect(label).toBeLessThan(timezone390.labelOneLine);
  });
});
