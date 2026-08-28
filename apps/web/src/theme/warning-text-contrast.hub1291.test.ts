// hub#1291 — review follow-up on hub#1290: `ion-note`/`ion-text` text painted `color="warning"`
// renders in Ionic's raw `--ion-color-warning` (#ffc409, ~1.6:1 on white) or its `-shade`
// (~2.1:1). Both fail WCAG AA's 4.5:1 floor for normal text. hub#1290 fixed the pattern in
// Settings → Permissions (`SettingsPage.vue`): the note text reads `color="medium"`
// (`--ion-color-medium: #6b7280` in this shell's theme, ~4.83:1) and the warning accent stays on
// the ICON alone — the convention iOS/Android permission screens, Shopify and Square all share.
//
// This is the guard hub#1290's own PR asked for and did not ship: a SOURCE test that catches the
// SAME shape of bug the next time someone reaches for `color="warning"` on readable text instead
// of an icon. Same style of guard as `ionic-fill-needs-md.test.ts` (hub#760) — a styling bug that
// raises no runtime error needs something that looks at the source for you.
//
// Two shapes of the same defect turned up when this ticket was triaged against real
// `ExportPanel.vue` / `ImportPanel.vue` / `AssistantDrawer.vue` / `BlueprintHeroCard.vue`:
//
//   1. The attribute form — `<ion-note color="warning">…text…</ion-note>` (ExportPanel's
//      `fiscal-note`, pre-fix). CHECK 1 below.
//   2. The scoped-CSS form — a `<p class="some-class">…text…</p>` whose OWN scoped `<style>`
//      paints `color: var(--ion-color-warning…)` on that class (ExportPanel/ImportPanel's
//      `.admin-note`, AssistantDrawer's `.chat-grounding-line`, BlueprintHeroCard's
//      `.hero-blocked` — none of these use the `color="warning"` attribute at all, so a guard
//      that only matched CHECK 1 would have stayed green while three of the four files kept
//      failing WCAG AA). CHECK 2 below.
//
// An icon is exempt from both checks: the accent belongs there, not on the sentence next to it.
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = fileURLToPath(new URL('..', import.meta.url));

/** Vue's own icon-rendering elements: a color set here IS the intended accent, never a defect. */
const ICON_TAGS = new Set(['HubIcon', 'ion-icon', 'svg']);

function vueFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...vueFiles(full));
    else if (entry.name.endsWith('.vue')) out.push(full);
  }
  return out;
}

/** Strips tags/comments, keeping only what a reader would actually see (text + `{{ }}`). */
function visibleText(html: string): string {
  return html
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/** CHECK 1 — `<ion-note>`/`<ion-text>` opened with a STATIC `color="warning"`. */
const NOTE_OR_TEXT = /<(ion-note|ion-text)\b([^>]*)>([\s\S]*?)<\/\1>/g;

function staticWarningNotesWithText(source: string): string[] {
  const offenders: string[] = [];
  for (const m of source.matchAll(NOTE_OR_TEXT)) {
    const [, tag, attrs, inner] = m;
    if (!/\bcolor="warning"/.test(attrs)) continue;
    const text = visibleText(inner);
    if (text.length > 0) {
      offenders.push(`<${tag} color="warning">${text.slice(0, 70)}</${tag}>`);
    }
  }
  return offenders;
}

/** CHECK 2 — a scoped-style class that paints warning color onto a non-icon element's text. */
function scopedWarningTextClasses(source: string): string[] {
  const styleMatch = source.match(/<style\b[^>]*\bscoped\b[^>]*>([\s\S]*?)<\/style>/);
  if (!styleMatch) return [];
  const css = styleMatch[1];

  // One rule = one selector list + its declaration block. `.a, .b { … }` is split per selector so
  // each class is checked against its own usage in the template.
  const classesWithWarningColor = new Set<string>();
  for (const rule of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const [, selectorList, body] = rule;
    // `color:` only — never `border-color`/`background`: the accent block around
    // `.chat-grounding` (border + tinted background) is not the text-contrast bug this guards.
    if (!/(?<![-\w])color:\s*var\(--ion-color-warning/.test(body)) continue;
    for (const sel of selectorList.split(',')) {
      const cls = sel.trim().match(/^\.([a-zA-Z0-9_-]+)$/);
      if (cls) classesWithWarningColor.add(cls[1]);
    }
  }
  if (classesWithWarningColor.size === 0) return [];

  const offenders: string[] = [];
  // Any tag carrying one of those classes, elsewhere in the template.
  const TAG_WITH_CLASS = /<([a-zA-Z][\w-]*)\b([^>]*\bclass="[^"]*"[^>]*)>/g;
  for (const m of source.matchAll(TAG_WITH_CLASS)) {
    const [tagOpen, tag, attrs] = m;
    const classAttr = attrs.match(/\bclass="([^"]*)"/)?.[1] ?? '';
    const hitClass = classAttr.split(/\s+/).find((c) => classesWithWarningColor.has(c));
    if (!hitClass || ICON_TAGS.has(tag)) continue;
    if (/\/\s*>$/.test(tagOpen)) continue; // self-closing: nothing it could wrap.

    const closeIdx = source.indexOf(`</${tag}>`, m.index! + tagOpen.length);
    if (closeIdx === -1) continue;
    const inner = source.slice(m.index! + tagOpen.length, closeIdx);
    // An icon-only wrapper (e.g. a future `<p class="x"><HubIcon /></p>`) is still exempt: strip
    // the icon element(s) before judging whether anything readable is left.
    const withoutIcons = inner.replace(/<(?:HubIcon|ion-icon)\b[^>]*\/?>(?:[\s\S]*?<\/(?:HubIcon|ion-icon)>)?/g, '');
    const text = visibleText(withoutIcons);
    if (text.length > 0) {
      offenders.push(`<${tag} class="${hitClass}">${text.slice(0, 70)}</${tag}> — .${hitClass} { color: var(--ion-color-warning…) }`);
    }
  }
  return offenders;
}

describe('readable text never paints in the raw warning color (hub#1291)', () => {
  it('Ionic warning yellow really does fail WCAG AA on white — the premise of this guard', () => {
    // #ffc409 vs #ffffff, WCAG relative-luminance contrast ratio.
    function luminance([r, g, b]: [number, number, number]): number {
      const chan = (c: number) => (c /= 255) <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
      return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b);
    }
    function contrast(a: [number, number, number], b: [number, number, number]): number {
      const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x);
      return (l1 + 0.05) / (l2 + 0.05);
    }
    const warning: [number, number, number] = [0xff, 0xc4, 0x09];
    const white: [number, number, number] = [0xff, 0xff, 0xff];
    expect(contrast(warning, white), 'if Ionic ever recolors --ion-color-warning this guard may be obsolete').toBeLessThan(4.5);
  });

  it('no `<ion-note>`/`<ion-text color="warning">` wraps readable text — the fail names the file', () => {
    const offenders: string[] = [];
    for (const file of vueFiles(SRC)) {
      for (const hit of staticWarningNotesWithText(readFileSync(file, 'utf8'))) {
        offenders.push(`  ${relative(SRC, file)}: ${hit}`);
      }
    }
    expect(
      offenders,
      ['color="warning" is ~1.6:1 on white — under WCAG AA; use color="medium" and keep the accent on the icon:', ...offenders].join('\n'),
    ).toEqual([]);
  });

  it('no scoped style paints warning-yellow text on a non-icon element — the fail names the file', () => {
    const offenders: string[] = [];
    for (const file of vueFiles(SRC)) {
      for (const hit of scopedWarningTextClasses(readFileSync(file, 'utf8'))) {
        offenders.push(`  ${relative(SRC, file)}: ${hit}`);
      }
    }
    expect(
      offenders,
      ['scoped `color: var(--ion-color-warning…)` on readable text is under WCAG AA — recolor the text `medium` and move the accent to an icon class:', ...offenders].join('\n'),
    ).toEqual([]);
  });

  it('the scan actually reaches components — otherwise it would pass on an empty set', () => {
    const total = vueFiles(SRC).length;
    expect(total, 'no .vue files found: the scan root moved and this guard stopped guarding').toBeGreaterThan(30);
  });
});
