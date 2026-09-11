// ERPlora/hub#1765 — **the «0» key of the login pinpad was cut off by the bottom of the card**.
//
// Measured on the PRE bench (`banco-pre.a.erplora.com/login`, 390×844, root font 16px, 2026-09-10),
// reading real boxes off the live page:
//
// | box                        | top | bottom | height |
// |----------------------------|-----|--------|--------|
// | `ion-card` (clips)         | 196 | **728**| 532    |
// | `.step-form` (`height:26rem`)| 291 | 707  | 416    |
// | `.step-form` content needed |  -  |   -    | **483**|
// | the «0» key                | 673 | **740**| 67     |
//
// The PIN step stacks three children — the badge hint (48), the avatar + name (68) and the pinpad
// (342), plus two 12px gaps = **483px** — inside a box frozen at `height: 26rem` (416px). With
// `justify-content: center` the 67px that do not fit spill out of BOTH ends, and `ion-card` is
// `overflow: hidden`, so the last row of keys (←, 0, ⌫) ended **12px past the card's bottom edge**
// and got sliced.
//
// The rule this file keeps: **inside a container that clips, a fixed height can only ever cut
// content off.** The card reserves a floor (`min-height`) so the short steps still measure the
// same and no tab jumps — and the tall one grows instead of losing a key. The single exception is
// the step that scrolls INSIDE (`.user-scroll`, `flex: 1`), which needs a bounded box or its list
// would grow without end; it says so with its own class, and that class is only ever on that step.
//
// A source test on purpose. Nothing throws when a button is clipped — the pixels simply stop — so
// it needs something that looks at it, or the next height tweak brings the same silent cut back
// (same reasoning as `font-family-promise.hub1166.test.ts`).
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

// Read from the vitest root (`apps/web`): under happy-dom `import.meta.url` is not a `file:` URL.
const source = readFileSync(`${process.cwd()}/src/views/LoginPage.vue`, 'utf8');

/** The declaration block of one CSS rule, by its exact selector. */
function ruleBody(selector: string): string {
  const match = source.match(
    new RegExp(`(^|\\n)\\s*${selector.replace(/[.\-]/g, '\\$&')}\\s*\\{([^}]*)\\}`),
  );
  if (!match) throw new Error(`no hay ninguna regla \`${selector}\` en LoginPage.vue`);
  return match[2];
}

/** Every `height` this block sets, ignoring `min-height` / `max-height` / `line-height`. */
function fixedHeights(body: string): string[] {
  return [...body.matchAll(/(^|[;{\s])height\s*:\s*([^;]+)/g)].map((m) => m[2].trim());
}

describe('hub#1765 — the pinpad keeps all twelve keys inside the card', () => {
  it('reserves the step height as a FLOOR, so the tall step grows instead of losing a key', () => {
    const body = ruleBody('.step-form');

    expect(
      fixedHeights(body),
      'un alto FIJO dentro de `ion-card` (overflow: hidden) solo puede recortar: el paso del PIN ' +
        'mide 483px y la reserva eran 416px, así que el botón «0» quedaba 12px fuera de la tarjeta',
    ).toEqual([]);
    expect(body, 'la reserva sigue existiendo, como suelo').toMatch(/min-height\s*:/);
  });

  it('bounds only the step that scrolls inside, and only while it is on screen', () => {
    // The user picker is the one step that MUST stay bounded: `.user-scroll` is `flex: 1` with its
    // own `overflow-y: auto`, so without a ceiling the list grows down the page instead of
    // scrolling. It carries its own class...
    expect(fixedHeights(ruleBody('.step-form--scrolls'))).not.toEqual([]);
    // ...and that class is bound to the picker (no user chosen yet), never to the step that holds
    // the pinpad. Binding it wider would put the fixed height straight back under the keys.
    expect(source).toMatch(/'step-form--scrolls'\s*:\s*!pinUser/);
  });

  it('keeps the pinpad out of any other box that could clip it', () => {
    // The wrapper only centres (hub#264). A height here would cut the keys just as well, one level
    // further in and harder to see.
    expect(fixedHeights(ruleBody('.pinpad-wrap'))).toEqual([]);
  });
});
