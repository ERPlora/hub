// @vitest-environment happy-dom
// hub#1715 — the half nobody would notice was broken: is the thing on screen a QR AT ALL?
//
// `ok-qr` lives in OutfitKit and ships with no tests of its own, so nothing upstream proves it
// emits a readable symbol. That is the nastiest failure mode this feature has: a broken generator
// paints a crisp, convincing black-and-white rectangle, every other test in the repo stays green,
// and the first person to find out is standing at a counter with their phone out.
//
// The symbol this renders WAS decoded for real, once, with Apple's CoreImage `CIDetector` — the
// same engine behind the iPhone camera — and it returned the URL exactly. Two negative controls
// (finder pattern wiped, 40 data modules flipped) were both REFUSED by that detector, so the pass
// was not a decoder that says yes to anything. Evidence is in the PR; it cannot live here because
// CI runners have no Swift.
//
// What stays behind is the structural half, and it is the load-bearing part: the three finder
// patterns are what a camera locks onto before it decodes a single bit. Wipe one and no decoder in
// the world finds a code — which is exactly what that CIDetector run demonstrated.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import '@erplora/outfitkit/ok-qr';
import { installQrUrl } from '../lib/install-qr';

/** The canonical 7×7 finder pattern, straight out of the QR standard. */
const FINDER = ['1111111', '1000001', '1011101', '1011101', '1011101', '1000001', '1111111'];

/** Quiet zone `ok-qr` leaves on each side (its `margin` default, the standard minimum). */
const MARGIN = 4;

const componentSource = (): string =>
  readFileSync(join(process.cwd(), 'src', 'components', 'SidebarInstallQr.vue'), 'utf8');

/**
 * Renders the symbol with the SAME inputs the sidebar uses — read out of the component rather than
 * repeated here, so that dropping the size or changing the correction level cannot quietly leave
 * this suite testing a symbol the product no longer paints.
 */
async function renderSidebarSymbol() {
  const source = componentSource();
  const size = source.match(/<ok-qr[^>]*\ssize="(\d+)"/)?.[1];
  const ec = source.match(/<ok-qr[^>]*\sec="([LMQH])"/)?.[1];
  expect(size, 'the sidebar QR must declare its size').toBeDefined();
  expect(ec, 'the sidebar QR must declare its error correction level').toBeDefined();

  const el = document.createElement('ok-qr') as HTMLElement & { updateComplete?: Promise<unknown> };
  el.setAttribute('value', installQrUrl({ host: 'banco-pre.pre.erplora.com', origin: 'https://banco-pre.pre.erplora.com' }));
  el.setAttribute('size', size!);
  el.setAttribute('ec', ec!);
  document.body.appendChild(el);
  await el.updateComplete;

  const svg = el.shadowRoot?.innerHTML ?? '';
  const side = Number(svg.match(/viewBox="0 0 (\d+) /)?.[1] ?? 0);
  const dark = new Set([...svg.matchAll(/M(\d+) (\d+)h1v1h-1z/g)].map((m) => `${m[1]},${m[2]}`));
  return { svg, side, dark, modules: side - MARGIN * 2 };
}

describe('the sidebar paints a symbol a camera can resolve', () => {
  it('is a grid of a real QR version, with its quiet zone around it', async () => {
    const { side, dark, modules } = await renderSidebarSymbol();

    // An empty render is the failure this exists for: it looks like «no QR yet», not like a bug.
    expect(dark.size).toBeGreaterThan(0);
    expect(side).toBeGreaterThan(0);

    // Every QR version is 21 + 4·(version−1) modules a side, versions 1 to 40.
    expect(modules).toBeGreaterThanOrEqual(21);
    expect(modules).toBeLessThanOrEqual(177);
    expect((modules - 21) % 4).toBe(0);
  });

  it('carries all three finder patterns, exactly', async () => {
    const { dark, modules } = await renderSidebarSymbol();

    // Top-left, top-right, bottom-left: the three corners a decoder triangulates the grid from.
    const origins: Array<[number, number]> = [
      [0, 0],
      [modules - 7, 0],
      [0, modules - 7],
    ];

    const wrong: string[] = [];
    for (const [ox, oy] of origins) {
      for (let row = 0; row < 7; row++) {
        for (let col = 0; col < 7; col++) {
          const isDark = dark.has(`${MARGIN + ox + col},${MARGIN + oy + row}`);
          if (isDark !== (FINDER[row][col] === '1')) wrong.push(`finder@(${ox},${oy}) cell (${col},${row})`);
        }
      }
    }
    // Named one per line: when this fails, the message IS the diagnosis.
    expect(wrong.join('\n')).toBe('');
  });

  it('labels the symbol with what it encoded, so the value survives to the SVG', async () => {
    const { svg } = await renderSidebarSymbol();
    expect(svg).toContain('https://banco-pre.pre.erplora.com/');
  });
});
