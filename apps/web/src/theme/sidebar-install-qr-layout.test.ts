// hub#1715 — the sidebar QR must paint CENTRED under its own caption, and must give way to its
// icon on the rail.
//
// Why this guard exists, and why it is worth a file. `ok-qr` is a block-level custom element: left
// to itself the host stretches to the whole panel and `margin-inline: auto` has nothing left to
// centre, so the code paints flush LEFT under a centred title. Caught with a real browser at
// 360/768/1440 while reviewing this very change — the symbol stayed square and perfectly
// scannable, which is exactly what makes it easy to ship by accident: nothing breaks, it just
// looks broken, and no unit test in a DOM without layout can see it.
//
// This asserts the DECLARATIONS rather than the geometry, because vitest's DOM does not lay
// anything out. That is a real limit: it proves the rule is still written, not that the pixels
// landed. The pixels were measured in a browser (gaps 74px/74px at 240px, symbol 132×132 square)
// and the numbers are in the PR. What this file buys is that nobody deletes the rule six months
// from now and finds out from a customer.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const css = readFileSync(new URL('./polish.css', import.meta.url), 'utf8');

/** The single declaration block for `selector`, so a match cannot come from a neighbouring rule. */
function ruleFor(selector: string): string {
  const start = css.indexOf(`${selector} {`);
  expect(start, `no rule for "${selector}" in polish.css`).toBeGreaterThan(-1);
  return css.slice(start, css.indexOf('}', start) + 1);
}

describe('the sidebar QR sits centred and collapses to an icon on the rail (hub#1715)', () => {
  it('shrinks the ok-qr host to its symbol so it can be centred', () => {
    const rule = ruleFor('.sidebar-install-qr-code');
    // Without an intrinsic width the block-level host fills the panel and the code hugs the left
    // edge under a centred caption.
    expect(rule, 'ok-qr is block-level: without a shrink-to-fit width it cannot be centred').toMatch(
      /width:\s*fit-content/,
    );
    expect(rule, 'a shrink-to-fit host still needs auto margins to actually centre').toMatch(
      /margin-inline:\s*auto/,
    );
  });

  it('never caps the code with a max-width (hub#1605)', () => {
    // The code is sized by its own `size` attribute. A `max-width` here would both trip the shell
    // guard and silently shrink the symbol below the size a phone camera resolves.
    expect(ruleFor('.sidebar-install-qr-code')).not.toMatch(/(?<![-\w])max-width:/);
    expect(ruleFor('.sidebar-install-qr')).not.toMatch(/(?<![-\w])max-width:/);
  });

  it('swaps the code for its icon on the collapsed rail', () => {
    // ~68px of rail cannot hold a readable code, and a code nobody can scan is worse than an icon
    // that opens the panel which can show one. Done in CSS because the block itself carries no
    // condition — see the guard in SidebarInstallQr.test.ts.
    expect(css).toMatch(/ion-split-pane\.rail \.sidebar-install-qr-full \{[^}]*display:\s*none/);
    expect(css).toMatch(/ion-split-pane\.rail \.sidebar-install-qr-rail \{[^}]*display:\s*inline-flex/);
    // …and off the rail it is the icon that stays out of the way, not the code.
    expect(ruleFor('.sidebar-install-qr-rail')).toMatch(/display:\s*none/);
  });
});
