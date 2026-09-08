// The «Your plan» badge must not be drawn on top of the card above it — hub#1652.
//
// Marking the current tier (hub#1652) turned on `ok-pricing-card`'s floating badge, and that badge
// is deliberately drawn OUTSIDE its own card: `.badge { position: absolute; top: -0.8rem }`. The
// card is `height: 100%` of its `ion-col`, and Ionic's grid gutter is 5px, so the badge sticks out
// above the column box by roughly 8px more than the gutter absorbs.
//
// That only matters because this grid WRAPS: the tiers are `size="12" size-md="6" size-lg="3"`, so
// on a phone every tier is its own row and on a tablet there are two rows. The moment the tier you
// are on is not in the first row, its badge lands over the card above it. Reserving the room is the
// job of whoever stacks the cards — the card cannot know it is being tiled.
//
// The guard is anchored at BOTH ends on purpose, so it stays honest in either direction:
//   · the overhang is read from the OutfitKit bundle this app actually ships, not hardcoded here —
//     if the badge ever floats higher, this test goes red instead of silently under-reserving;
//   · the reserve is read from the panel's own scoped style — if it is removed, this test goes red.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

const require_ = createRequire(import.meta.url);

/** The `ok-pricing-card` that ends up in the browser, resolved through its public export. */
const pricingCard = readFileSync(
  require_.resolve('@erplora/outfitkit/ok-pricing-card'),
  'utf8',
);
const panel = readFileSync(new URL('./ModulePlanPanel.vue', import.meta.url), 'utf8');

/** `<style scoped>` of the panel — the rules the grid is laid out with. */
const panelStyle = panel.slice(panel.indexOf('<style'), panel.lastIndexOf('</style>'));

/** How far a rule's property sticks out, in rem. `null` when the rule or property is not there. */
function remValue(css: string, selector: string, property: string): number | null {
  const start = css.indexOf(selector);
  if (start < 0) return null;
  const block = css.slice(start, css.indexOf('}', start));
  const match = new RegExp(`${property}\\s*:\\s*(-?[\\d.]+)rem`).exec(block);
  return match ? Number(match[1]) : null;
}

describe('the «Your plan» badge has room above its card (hub#1652)', () => {
  it('floats above the card it belongs to, which is why the room is needed', () => {
    const top = remValue(pricingCard, '.badge {', 'top');
    expect(top, 'no `.badge` rule with a rem `top` in the shipped ok-pricing-card').not.toBeNull();
    // Negative `top` = drawn outside the card. If this ever turns positive the badge is contained
    // and the reserve below is no longer load-bearing — which is a decision, not a silent pass.
    expect(top).toBeLessThan(0);
  });

  it('the tier columns reserve at least the overhang, so a wrapped row is not overlapped', () => {
    const overhang = Math.abs(remValue(pricingCard, '.badge {', 'top') ?? 0);
    const reserved = remValue(panelStyle, '.tier-col', 'padding-top');

    expect(reserved, 'the tier columns of ModulePlanPanel reserve no room for the badge').not.toBeNull();
    expect(reserved).toBeGreaterThanOrEqual(overhang);
  });

  it('every tier column carries the class that reserves the room, not just the marked one', () => {
    // The badge moves with the plan you are on, so the reserve cannot be conditional: if only the
    // current card reserved room, the rows would jump height as your plan changes.
    const col = /<ion-col[^>]*v-for="tier in tiers"[^>]*>/.exec(panel)?.[0] ?? '';
    expect(col, 'the tier `ion-col` is not where this test thinks it is').not.toBe('');
    expect(col).toContain('tier-col');
  });
});
