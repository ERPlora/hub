// flow: e2e-overflow — FIX of the e2e harness (FIX-HUB-E2E-HORIZONTAL-SCROLL-CHECK-BLIND-TO-ION-CONTENT)
// Every «no horizontal scroll» check of the e2e goes through `horizontalOverflow(page)` (helpers.ts), which reads the
// document and every `ion-content` on screen. A spec that measures the document by hand (`documentElement.scrollWidth`
// against the window) is blind to a screen cut inside `ion-content`: Ionic pins the `body`, so the document never grows
// (60 files of the e2e did, and a 1600 px block on a page at 390 passed). No ratchet: no file but helpers.ts measures it.
// Nor through a name given to the root (`const root = document.documentElement; root.scrollWidth`), nor one `ion-content`
// by hand (its `getScrollElement()`, `.inner-scroll` or `part="scroll"` and their `scrollWidth`): that copy left out the
// menu and the sheets (seen by the reviewer of hub#393). Its vertical scroll (`scrollTop`, `scrollHeight`) stays free.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));

/** The file of the one measure. */
const HELPERS = 'helpers.ts';

/** The ways of reading how wide the document is: its root's, its scrolling element's or its body's `scrollWidth`, also
 *  closed in a parenthesis or through `as` (`(document.scrollingElement ?? document.documentElement).scrollWidth`). */
const DOCUMENT_WIDTH =
  /\b(?:documentElement|scrollingElement|document\s*\.\s*body)\s*!?(?:\s*as\s+[^);]+)?\s*\)?\s*!?\s*\??\.\s*scrollWidth\b/;

/** An `ion-content`'s scroll box read right there: `(await content.getScrollElement()).scrollWidth`, its `then()`, `….scrollWidth`
 *  of its `.inner-scroll` or its `part="scroll"`. */
const SCROLL_BOX_WIDTH =
  /(?:getScrollElement\(\)|inner-scroll|part~?=["']?scroll)[^;\n]*?(?:\)|=>\s*\w+)\s*!?\s*\??\.\s*scrollWidth\b/;

/** The document's root by any of its names (`document.documentElement`, `.scrollingElement`, `.body`). */
const ROOT = String.raw`(?:(?:window|globalThis)\s*\.\s*)?document\s*\.\s*(?:documentElement|scrollingElement|body)\s*!?`;

/** A name given to the root (`const root = document.documentElement`, `?? document.body`, `as HTMLElement`). */
const ROOT_NAME = new RegExp(
  String.raw`\b(?:const|let|var)\s+(\w+)(?:\s*:[^=]+)?\s*=\s*\(?\s*${ROOT}(?:\s*(?:\?\?|\|\|)\s*${ROOT})*\s*(?:as\s+[^;,)]+)?\)?\s*(?:[;,)]|$)`,
);

/** The names a destructuring of `document` gives to the root (`const { body, documentElement: html } = document`). */
const ROOT_DESTRUCTURED = /\b(?:const|let|var)\s*\{([^}]*)\}\s*=\s*document\s*[;\n]/;

/** A name given to an `ion-content`'s scroll box: from its `getScrollElement()`, its `.inner-scroll` or its `part="scroll"`. */
const SCROLL_BOX_NAME = /\b(?:const|let|var)\s+(\w+)(?:\s*:[^=]+)?\s*=[^;\n]*(?:getScrollElement\(|inner-scroll|part~?=["']?scroll)/;

/** A `scrollWidth` taken out by destructuring (`const { scrollWidth } = …`, also nested), and what it is taken from. */
const WIDTH_DESTRUCTURED = /\{[^{}]*\bscrollWidth\b[^{}]*\}[\s}]*=\s*(?:await\s+)?\(?\s*([^;\n]*)/;

/** What that destructuring measures by hand: the root (or `document`, destructured down to it) or a scroll box. */
const MEASURED_BOX = new RegExp(String.raw`^(?:${ROOT}|document\s*$)|getScrollElement\(|inner-scroll|part~?=["']?scroll`);

/** The names `source` gives to the document's root or to an `ion-content`'s scroll box. */
function boxNames(source: string): string[] {
  const names = new Set<string>();
  for (const line of source.split('\n')) {
    const named = line.match(ROOT_NAME) ?? line.match(SCROLL_BOX_NAME);
    if (named) names.add(named[1]);
    for (const entry of line.match(ROOT_DESTRUCTURED)?.[1].split(',') ?? []) {
      const [key, alias] = entry.split(':').map((part) => part.trim());
      if (/^(?:documentElement|scrollingElement|body)$/.test(key)) names.add(alias || key);
    }
  }
  return [...names];
}

/**
 * `file:line` of each line of `source` (the file `name`) that measures by hand how wide the document or one `ion-content`
 * is: its `scrollWidth`, read directly or through a name given to it. A vertical read (`scrollTop`, `scrollHeight`) is
 * no such measure.
 */
function documentMeasures(name: string, source: string): string[] {
  const names = boxNames(source);
  const named = names.length ? new RegExp(String.raw`\b(?:${names.join('|')})\s*!?\s*\??\.\s*scrollWidth\b`) : null;
  const namedBox = names.length ? new RegExp(String.raw`^(?:${names.join('|')})\b`) : null;
  const destructured = (line: string) => {
    const from = line.match(WIDTH_DESTRUCTURED)?.[1];
    return from !== undefined && (MEASURED_BOX.test(from) || !!namedBox?.test(from));
  };
  return source
    .split('\n')
    .flatMap((line, index) =>
      DOCUMENT_WIDTH.test(line) || SCROLL_BOX_WIDTH.test(line) || named?.test(line) || destructured(line)
        ? [`${name}:${index + 1}`]
        : [],
    );
}

/** The files of the e2e (the specs and their helpers, not Vitest's own tests) that measure the document by hand. */
function handMeasures(): string[] {
  return readdirSync(E2E_DIR)
    .filter((name) => name.endsWith('.ts') && !name.endsWith('.test.ts') && name !== HELPERS)
    .sort()
    .flatMap((name) => documentMeasures(name, readFileSync(join(E2E_DIR, name), 'utf8')));
}

describe('the e2e checks for a horizontal scroll go through horizontalOverflow() of helpers.ts', () => {
  it('no file of tests/e2e but helpers.ts measures the document by hand: the check is horizontalOverflow(page)', () => {
    expect(handMeasures()).toEqual([]);
  });

  it('helpers.ts has the one measure, and it reads the document and the scroll box of every ion-content', () => {
    const helpers = readFileSync(join(E2E_DIR, HELPERS), 'utf8');
    expect(helpers).toContain('export async function horizontalOverflow(page: Page): Promise<number>');
    expect(helpers).toContain('const boxes: Element[] = [document.documentElement];');
    expect(helpers).toContain("for (const content of document.querySelectorAll('ion-content'))");
    expect(helpers).toContain(`content.shadowRoot?.querySelector('[part~="scroll"]')`);
  });

  it('the count reads every way of measuring the document by hand, and the helper or an element’s own width as none', () => {
    const lines = [
      'page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)',
      'page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)',
      '      documentScrollWidth: document.documentElement.scrollWidth,',
      'return document.scrollingElement!.scrollWidth - innerWidth;',
      'return document.body.scrollWidth > innerWidth;',
    ];
    expect(lines.map((line) => documentMeasures('x.ts', line))).toEqual(lines.map(() => ['x.ts:1']));
    expect(documentMeasures('x.ts', 'expect.poll(() => horizontalOverflow(page)).toBeLessThanOrEqual(0);')).toEqual([]);
    expect(documentMeasures('x.ts', 'label.scrollWidth > label.clientWidth + 1')).toEqual([]);
    expect(documentMeasures('x.ts', 'const body = el.querySelector(".drawer-body"); body.scrollWidth > body.clientWidth')).toEqual([]);
  });

  it('the count reads the document measured through a name given to its root', () => {
    const root = ['page.evaluate(() => {', '  const root = document.documentElement;', '  return root.scrollWidth - window.innerWidth;', '});'];
    expect(documentMeasures('a.ts', root.join('\n'))).toEqual(['a.ts:3']);
    const either = ['const root = document.scrollingElement ?? document.documentElement;', 'return root!.scrollWidth > innerWidth;'];
    expect(documentMeasures('a.ts', either.join('\n'))).toEqual(['a.ts:2']);
    const destructured = ['const { body, documentElement: html } = document;', 'return [body.scrollWidth, html.scrollWidth];'];
    expect(documentMeasures('a.ts', destructured.join('\n'))).toEqual(['a.ts:2']);
  });

  it('the count reads one ion-content measured by hand: its getScrollElement(), its .inner-scroll or its part="scroll"', () => {
    const copy = [
      'return page.evaluate(async () => {',
      "  const content = document.querySelector('ion-router-outlet > .ion-page:not(.ion-page-hidden) ion-content') as",
      '    | (HTMLElement & { getScrollElement?: () => Promise<HTMLElement> })',
      '    | null;',
      '  const inner = content?.getScrollElement ? await content.getScrollElement() : null;',
      '  return inner ? inner.scrollWidth - window.innerWidth : 0;',
      '});',
    ];
    expect(documentMeasures('b.ts', copy.join('\n'))).toEqual(['b.ts:6']);
    expect(documentMeasures('b.ts', 'return (await content.getScrollElement()).scrollWidth > innerWidth;')).toEqual(['b.ts:1']);
    const shadow = [
      "const scroll = shown.querySelector('ion-content')?.shadowRoot?.querySelector<HTMLElement>('.inner-scroll');",
      'if (scroll && scroll.scrollWidth > scroll.clientWidth + 1) found.push(scroll);',
    ];
    expect(documentMeasures('b.ts', shadow.join('\n'))).toEqual(['b.ts:2']);
    expect(documentMeasures('b.ts', `return content.shadowRoot?.querySelector('[part~="scroll"]')?.scrollWidth ?? 0;`)).toEqual(['b.ts:1']);
  });

  it('the count reads the root or a scroll box measured through `??` or `as` in line, a then() or a destructured scrollWidth', () => {
    const inline = [
      'return (document.scrollingElement ?? document.documentElement).scrollWidth - innerWidth;',
      'return (document.scrollingElement as HTMLElement | null)?.scrollWidth ?? 0;',
      'return content.getScrollElement().then((element) => element.scrollWidth - innerWidth);',
      'const { scrollWidth, clientWidth } = document.documentElement;',
      'const { scrollWidth } = await content.getScrollElement();',
      'const { documentElement: { scrollWidth } } = document;',
    ];
    expect(inline.map((line) => documentMeasures('d.ts', line))).toEqual(inline.map(() => ['d.ts:1']));
    const named = ['const root = window.document.documentElement;', 'const { scrollWidth } = root;', 'return root.scrollWidth;'];
    expect(documentMeasures('d.ts', named.join('\n'))).toEqual(['d.ts:2', 'd.ts:3']);
    expect(documentMeasures('d.ts', "const { scrollWidth, clientWidth } = document.querySelector('ion-title')!;")).toEqual([]);
  });

  it('the count leaves alone the vertical scroll of an ion-content and an element that is only put in the body', () => {
    const vertical = [
      "const content = document.querySelector('ion-content') as HTMLElement & { getScrollElement(): Promise<HTMLElement> };",
      'return (await content.getScrollElement()).scrollTop;',
      'const scroller = await (content as HTMLElement & { getScrollElement(): Promise<HTMLElement> }).getScrollElement();',
      'pageScrolls: scroller.scrollHeight > scroller.clientHeight + 1,',
      "const scroll = shown.querySelector('ion-content')?.shadowRoot?.querySelector<HTMLElement>('.inner-scroll');",
      'const end = scroll.getBoundingClientRect().bottom - parseFloat(getComputedStyle(scroll).paddingBottom);',
      `const box = element.shadowRoot?.querySelector('[part~="scroll"]')?.clientWidth ?? element.clientWidth;`,
    ];
    expect(documentMeasures('c.ts', vertical.join('\n'))).toEqual([]);
    const child = ['const element = document.body.appendChild(document.createElement(tag));', 'return element.scrollWidth;'];
    expect(documentMeasures('c.ts', child.join('\n'))).toEqual([]);
  });
});
