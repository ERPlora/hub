// Regression test for ERPlora/hub#2414 — a footer tab never splits a word across two lines.
//
// A module's footer tabs let their label wrap BETWEEN words («Lista de / espera») and only had the
// 116px floor to hold it: at 375px «Disponibilidad» got 87px in `md` and came out «Disponibilida» /
// «d»; in `ios` it fitted with under a pixel to spare, so Android's larger system text split it
// too. The floor a wrapping label needs is its longest word plus the tab's own padding — this pins
// that arithmetic. Where the engine really breaks the line is pinned in a real browser by
// `tests/e2e/TabbarWholeWords.spec.ts` (happy-dom lays nothing out).
import { describe, it, expect } from 'vitest';
import { wholeWordTabWidth, type TabLabelNeed } from './tabbar-peek';

/** Reservations' «Disponibilidad» at 375px in `md`, measured on the bench: 14px, 16px of padding a side. */
const DISPONIBILIDAD_MD: TabLabelNeed = { wraps: true, wordWidth: 95.3, chromeWidth: 32 };
/** «Lista de espera»: its longest word is short, whatever the whole label measures. */
const LISTA_DE_ESPERA_MD: TabLabelNeed = { wraps: true, wordWidth: 46.1, chromeWidth: 32 };

describe('wholeWordTabWidth — the tab a wrapping label needs to keep its words whole', () => {
  it('is the widest word plus the padding around it, rounded up to a whole pixel', () => {
    expect(wholeWordTabWidth([LISTA_DE_ESPERA_MD, DISPONIBILIDAD_MD], 375)).toBe(128);
  });

  it("leaves out labels that never wrap: those end in an ellipsis, the platforms' own fallback", () => {
    // The shell's own strips (Settings, Staff, System) keep Ionic's single-line label; a width
    // taken from their WHOLE label would widen every tab of those screens for a cut Ionic already
    // handles. Only a label that can break a line can break a word.
    const oneLine: TabLabelNeed = { wraps: false, wordWidth: 140, chromeWidth: 26 };
    expect(wholeWordTabWidth([oneLine, LISTA_DE_ESPERA_MD], 375)).toBe(79);
    expect(wholeWordTabWidth([oneLine], 375)).toBeNull();
  });

  it('says nothing without labels to measure (a strip still hydrating, or icon-only tabs)', () => {
    expect(wholeWordTabWidth([], 375)).toBeNull();
    expect(wholeWordTabWidth([{ wraps: true, wordWidth: 0, chromeWidth: 32 }], 375)).toBeNull();
  });

  it('never asks for a tab wider than the strip itself', () => {
    // A word longer than the phone is wide cannot be helped by the tab; a tab wider than the strip
    // would only hide it behind its own scroll.
    const huge: TabLabelNeed = { wraps: true, wordWidth: 400, chromeWidth: 32 };
    expect(wholeWordTabWidth([huge], 375)).toBe(375);
  });
});
